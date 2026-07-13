"""E4 x E6 — saturation curve + two-tower scaling slopes (crossover extrapolation).

Fixed eval set: 400 seeded EXPLORATION users, held out of every graph. Graph
ladder adds OOD exploration users (disjoint from eval) onto the frozen biased
train membership — the deployment reality ("crawl more, retrain"):
  G0 = train-1,133   G1 = train + half increment   G2 = train + full increment

Models per step: EASE(l100, fair list), userknn25 (both on pvalue), and the
two-tower pair (T1 shallow / T2 deep — see p6_twotower.py for the
PRE-REGISTERED predictions P1-P3).

Metrics per step:
  ndcg          graded NDCG@20 (metric A protocol)
  cold_recall   recall@20 restricted to holdout items with graph support < 3
                (feature towers can rank them; co-play models mostly cannot)
Outputs: ladder.csv + summary.json (slopes per model + crossover extrapolation
or the measured absence of one). Answers "how much more crawling would make a
two-tower meaningful" with slopes instead of guesses.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.ease_recheck import ease_reclist  # noqa: E402
from pipeline.orchestration.p6_common import (  # noqa: E402
    K, P4_DIR, P6_DIR, assert_firewall, build_relevance, graded_profile,
    load_artifacts, load_panels, split_profile_holdout)
from pipeline.orchestration.p6_twotower import TwoTower, load_tag_features  # noqa: E402
from pipeline.orchestration.preference_sweep import graded_ndcg  # noqa: E402
from pipeline.orchestration.ranker_gauntlet import EaseRanker, UserKNN  # noqa: E402

log = get_logger("orchestration.p6_e4")
OUT = P6_DIR / "e4_scaling"
EVAL_N, EVAL_SEED = 400, 888


def cold_recall(holdout: dict, rec: list[int], support: dict[int, int],
                k: int = K, thr: int = 3) -> float:
    cold = {a for a in holdout if support.get(a, 0) < thr}
    if not cold:
        return np.nan
    return len(cold & set(rec[:k])) / len(cold)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inter, gs, us, pool = load_artifacts()
    panels = load_panels()
    rel = build_relevance(inter, pool)
    counts = rel.groupby("steamid").size()
    explo = [int(u) for u in panels["exploration"] if u in counts.index]

    rng = np.random.default_rng(EVAL_SEED)
    eval_users = sorted(int(u) for u in rng.choice(explo, size=EVAL_N, replace=False))
    assert_firewall(eval_users, panels)
    inc_pool = sorted(set(explo) - set(eval_users))
    rng2 = np.random.default_rng(EVAL_SEED + 1)
    inc = list(rng2.permutation(inc_pool))
    panels_p4 = json.loads((P4_DIR / "panels.json").read_text())
    train = sorted(panels_p4["train"])
    ladder = {
        "G0_train": train,
        "G1_half": sorted(set(train) | set(int(u) for u in inc[: len(inc) // 2])),
        "G2_full": sorted(set(train) | set(int(u) for u in inc)),
    }

    splits = split_profile_holdout(rel, eval_users, seed=42)
    uu = sorted(splits)
    scores = bs.compute("pvalue_lognorm_eb", inter, gs, us)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            scores[scores["s"] > 0][["steamid", "appid", "s"]].values}
    feats, _ = load_tag_features(pool)

    rows = []
    for gname, graph in ladder.items():
        assert not (set(graph) & set(uu)), "graph/eval overlap"
        gset = set(graph)
        d = scores[(scores["s"] > 0) & scores["appid"].isin(pool)
                   & scores["steamid"].isin(gset)]
        support = d.groupby("appid").size().to_dict()

        models = {}
        ez = EaseRanker(scores, graph, pool, lam=100.0)
        models["ease_l100"] = lambda p, k, e, _m=ez: ease_reclist(_m, p, k, e)
        kn = UserKNN(scores, graph, pool, topk_users=25)
        models["userknn25"] = lambda p, k, e, _m=kn: _m.recommend(p, k, e)
        for label, deep in (("tt_shallow", False), ("tt_deep", True)):
            t0 = time.time()
            tt = TwoTower(scores, graph, pool, feats, deep=deep)
            models[label] = lambda p, k, e, _m=tt: _m.recommend(p, k, e)
            log.info("%s fit on %s: %.0fs", label, gname, time.time() - t0)

        for mname, fn in models.items():
            nd, cr = [], []
            for u in uu:
                sp = splits[u]
                prof = graded_profile(u, sp["profile"], smap,
                                      rel_fallback=sp["profile"])
                rec = fn(prof, K, set(sp["profile"]))
                nd.append(graded_ndcg(sp["holdout"], rec, K))
                cr.append(cold_recall(sp["holdout"], rec, support))
            rows.append({"graph": gname, "n_graph": len(graph), "model": mname,
                         "ndcg": round(float(np.mean(nd)), 4),
                         "cold_recall": round(float(np.nanmean(cr)), 4),
                         "n_cold_users": int(np.isfinite(cr).sum())})
            log.info("%s / %s: ndcg=%.4f cold=%.4f", gname, mname,
                     rows[-1]["ndcg"], rows[-1]["cold_recall"])

    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "ladder.csv", index=False)

    # slopes in log(graph-size) space + crossover extrapolation vs EASE
    summary = {"eval_n": len(uu), "predictions": "see p6_twotower.py header"}
    piv = tab.pivot(index="n_graph", columns="model", values="ndcg").sort_index()
    x = np.log(piv.index.values.astype(float))
    slopes = {m: float(np.polyfit(x, piv[m].values, 1)[0]) for m in piv.columns}
    summary["ndcg_by_graph"] = json.loads(piv.to_json())
    summary["slope_per_log_user"] = {m: round(s, 4) for m, s in slopes.items()}
    cross = {}
    e_s, e_v = slopes["ease_l100"], float(piv["ease_l100"].iloc[-1])
    xl = float(x[-1])
    for m in ("tt_shallow", "tt_deep"):
        m_s, m_v = slopes[m], float(piv[m].iloc[-1])
        if m_s <= e_s or m_v >= e_v:
            cross[m] = ("already >= EASE" if m_v >= e_v
                        else "no crossover (slope <= EASE)")
        else:
            xc = xl + (e_v - m_v) / (m_s - e_s)
            cross[m] = f"extrapolated crossover ~ {int(np.exp(xc)):,} graph users"
    summary["crossover_vs_ease"] = cross
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(tab.to_string(index=False))
    print(json.dumps({k: summary[k] for k in
                      ("slope_per_log_user", "crossover_vs_ease")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
