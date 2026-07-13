"""9-2 — absolute-rubric judge payload builder (JUDGE_ABS_PREREG.md).

Builds BLINDED per-user cases: taste profile (top-8 engagement cards) + a
single shuffled 30-item candidate list mixing three arms (ease/pop/rand,
top-10 each, all non-owned, in-pool). The judge rates EVERY item High/Medium/
Low ("would this user be interested?") — arm membership is stored only in the
separate unblind map. Aggregation happens in --aggregate mode after the judge
writes verdicts.json.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.evaluation.stats import bootstrap_ci  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.ease_recheck import ease_reclist  # noqa: E402
from pipeline.orchestration.p6_common import (  # noqa: E402
    P4_DIR, P6_DIR, assert_firewall, build_relevance, graded_profile,
    load_artifacts, load_panels, pop_ranker, split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import EaseRanker  # noqa: E402

log = get_logger("orchestration.p6_judge_abs")
OUT = P6_DIR / "judge_abs"
N_USERS, TOPK, SEED = 20, 10, 20260715


def build() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inter, gs, us, pool = load_artifacts()
    panels = load_panels()
    rel = build_relevance(inter, pool)
    counts = rel.groupby("steamid").size()
    explo = [int(u) for u in panels["exploration"] if u in counts.index]
    rng = np.random.default_rng(SEED)
    users = sorted(int(u) for u in rng.choice(explo, size=N_USERS, replace=False))
    assert_firewall(users, panels)

    panels_p4 = json.loads((P4_DIR / "panels.json").read_text())
    graph = sorted(set(panels_p4["train"])
                   | (set(explo) - set(users)))  # deployment-like, users held out
    scores = bs.compute("pvalue_lognorm_eb", inter, gs, us)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            scores[scores["s"] > 0][["steamid", "appid", "s"]].values}
    ez = EaseRanker(scores, graph, pool, lam=100.0)
    pop_fn = pop_ranker(inter, pool, graph)

    prof_all = {int(u): dict(zip(g["appid"].astype(int), g["rel"].astype(float)))
                for u, g in rel[rel["steamid"].isin(users)].groupby("steamid")}

    con = sqlite3.connect(f"file:{REPO_ROOT / 'data_collection' / 'steam.db'}?mode=ro",
                          uri=True)
    meta = {int(r[0]): (r[1], r[2], r[3]) for r in con.execute(
        "SELECT appid, name, genres_json, short_description FROM games "
        "WHERE name IS NOT NULL")}
    con.close()

    def card(a: int) -> dict:
        m = meta.get(int(a))
        if not m:
            return {"appid": int(a), "name": f"(unknown {a})"}
        raw = json.loads(m[1] or "[]") if m[1] else []
        genres = ", ".join(g.get("description", str(g)) if isinstance(g, dict)
                           else str(g) for g in raw[:4])
        return {"appid": int(a), "name": m[0], "genres": genres,
                "desc": (m[2] or "")[:160]}

    pool_arr = np.array(sorted(pool & set(meta)))
    own_cnt = inter[inter["appid"].isin(pool)].groupby("appid").size()

    cases, unblind = [], {}
    for i, u in enumerate(users):
        pa = prof_all[u]
        excl = set(pa)
        prof = graded_profile(u, pa, smap, rel_fallback=pa)
        arms = {
            "ease": ease_reclist(ez, prof, TOPK, excl),
            "pop": pop_fn(dict(pa), TOPK, excl),
        }
        cand = [int(a) for a in pool_arr if int(a) not in excl
                and int(a) not in set(arms["ease"]) | set(arms["pop"])]
        arms["rand"] = [int(a) for a in
                        rng.choice(cand, size=TOPK, replace=False)]
        mixed = [(a, arm) for arm, lst in arms.items() for a in lst]
        rng.shuffle(mixed)
        taste = sorted(pa.items(), key=lambda x: -x[1])[:8]
        cases.append({
            "case": f"case{i}",
            "user_taste": [card(a) | {"engagement": round(r, 2)} for a, r in taste],
            "candidates": [card(a) | {"slot": t} for t, (a, _) in enumerate(mixed)],
        })
        unblind[f"case{i}"] = {"steamid": u,
                               "slots": {str(t): {"appid": int(a), "arm": arm}
                                         for t, (a, arm) in enumerate(mixed)},
                               "popularity": {str(int(a)): int(own_cnt.get(a, 0))
                                              for a, _ in mixed}}
    (OUT / "payload.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "unblind.json").write_text(json.dumps(unblind, indent=1), encoding="utf-8")
    print(f"built {len(cases)} blinded cases (30 items each) -> {OUT}")
    return 0


def aggregate() -> int:
    verdicts = json.loads((OUT / "verdicts.json").read_text(encoding="utf-8"))
    unblind = json.loads((OUT / "unblind.json").read_text(encoding="utf-8"))
    per_arm: dict[str, dict[str, list[float]]] = {a: {"strict": [], "lenient": []}
                                                  for a in ("ease", "pop", "rand")}
    pop_by_rating: dict[str, list[int]] = {"High": [], "Medium": [], "Low": []}
    for case, ratings in verdicts.items():
        ub = unblind[case]
        arm_vals = {a: [] for a in ("ease", "pop", "rand")}
        for slot, rating in ratings.items():
            info = ub["slots"].get(str(slot))
            if not info or rating not in ("High", "Medium", "Low"):
                continue
            arm_vals[info["arm"]].append(rating)
            pop_by_rating[rating].append(ub["popularity"].get(str(info["appid"]), 0))
        for a, vals in arm_vals.items():
            if vals:
                per_arm[a]["strict"].append(
                    sum(v == "High" for v in vals) / len(vals))
                per_arm[a]["lenient"].append(
                    sum(v in ("High", "Medium") for v in vals) / len(vals))
    summary = {}
    for a, m in per_arm.items():
        cs = bootstrap_ci(np.array(m["strict"]))
        cl = bootstrap_ci(np.array(m["lenient"]))
        summary[a] = {"precision_strict": round(cs["mean"], 3),
                      "strict_ci": f"[{cs['lo']:.3f},{cs['hi']:.3f}]",
                      "precision_lenient": round(cl["mean"], 3),
                      "lenient_ci": f"[{cl['lo']:.3f},{cl['hi']:.3f}]",
                      "n_users": cs["n"]}
    summary["familiarity_bias_check"] = {
        r: int(np.median(v)) if v else None for r, v in pop_by_rating.items()}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()
    sys.exit(aggregate() if args.aggregate else build())
