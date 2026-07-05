"""Fresh-panel validation — snowball wave-2 users as quasi-OOD early signal.

New users accrued since the frozen panels (not reviewers — friends-of-friends
discovered by the crawler) have a DIFFERENT cohort bias than the 1,669 the
whole P4 exploration ranked on. Evaluating the leader configs on them, with
the graph FIXED to the frozen train panel, is a true zero-exposure
generalization check — an early preview of P6 (OOD re-experiment), not a
replacement for it (still snowball-linked, so bias overlaps partially).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.evaluation.stats import bootstrap_ci  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    P4, RP3B, GradedCF, build_relevance, get_panels, graded_ndcg,
    load_artifacts, snips_recall, split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import UserKNN  # noqa: E402

log = get_logger("orchestration.fresh_panel")

CONFIGS = [
    ("S0_pvalue_knnpd03", {"name": "pvalue_lognorm_eb", "params": {}}, ("knn", 0.3)),
    ("S1_pvalue_userknn", {"name": "pvalue_lognorm_eb", "params": {}}, ("knn", 0.0)),
    ("S2_pctl_userknn", {"name": "pctl_game", "params": {}}, ("knn", 0.0)),
    ("S3_capblend_rp3b", {"name": "per_user_cap",
                          "params": {"base": "blend", "lam": 0.4, "alpha": 0.3}},
     ("rp3b", None)),
    ("S4_capblend_condcos", {"name": "per_user_cap",
                             "params": {"base": "blend", "lam": 0.4, "alpha": 0.3}},
     ("condcos", None)),
    ("null_random_support", {"name": "random_support", "params": {}}, ("knn", 0.0)),
]
K = 20


def main() -> int:
    inter, game_stats, user_stats, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    frozen = set(panels["train"]) | set(panels["dev"]) | set(panels["private"])
    counts = rel.groupby("steamid").size()
    fresh = sorted(u for u in counts[counts >= 12].index if int(u) not in frozen)
    log.info("fresh users (zero-exposure, >=12 items): %d", len(fresh))
    if len(fresh) < 30:
        print(f"TOO FEW fresh users ({len(fresh)}) — skip")
        return 0
    splits = split_profile_holdout(rel, fresh, seed=42)

    n_users_total = inter["steamid"].nunique()
    prop = (inter.groupby("appid").size() / n_users_total).to_dict()

    rows = []
    for name, spec, (rkind, beta) in CONFIGS:
        scores = bs.compute(spec["name"], inter, game_stats, user_stats, **spec["params"])
        smap = {(int(u), int(a)): float(s) for u, a, s in
                scores[scores["s"] > 0][["steamid", "appid", "s"]].values}
        if rkind == "knn":
            model = UserKNN(scores, panels["train"], pool, topk_users=25,
                            pop_beta=beta or 0.0)
            S = amap = None
        elif rkind == "rp3b":
            model = RP3B(scores, panels["train"], pool, beta=0.6)
            S = amap = None
        else:
            model = GradedCF(scores, panels["train"], pool)
            need = sorted({a for u in splits for a in splits[u]["profile"]})
            S, amap = model.sim_columns(need)
        ndcgs, snipss = [], []
        for u, sp in splits.items():
            prof = {a: smap.get((u, a), 0.0) for a in sp["profile"]}
            prof = {a: w for a, w in prof.items() if w > 0} or dict(sp["profile"])
            excl = set(sp["profile"])
            rec = (model.recommend(prof, S, amap, K, excl) if S is not None
                   else model.recommend(prof, K, excl))
            ndcgs.append(graded_ndcg(sp["holdout"], rec, k=K))
            snipss.append(snips_recall(sp["holdout"], rec, K, prop))
        ci = bootstrap_ci(np.array(ndcgs))
        rows.append({"config": name, "ndcg": round(ci["mean"], 4),
                     "ci": f"[{ci['lo']:.3f},{ci['hi']:.3f}]",
                     "snips": round(float(np.mean(snipss)), 4), "n": len(ndcgs)})
        log.info("%s: ndcg=%.4f", name, ci["mean"])
    lb = pd.DataFrame(rows)
    out = P4 / "fresh_panel"
    out.mkdir(exist_ok=True)
    lb.to_csv(out / "leaderboard.csv", index=False)
    print(lb.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
