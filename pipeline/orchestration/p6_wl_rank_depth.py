"""Flipped absolute metric — how DEEP must the ranking go to hit wishlist targets?

Instead of hits@20, measures rank depth (exploration pool, descriptive):
  per-TARGET view (T-free): the rank of each future-wishlist item in the full
      EASE/POP ranking — median/p75/p90 + share within top 20/50/100/500.
      Pooling per target removes the per-user target-count (T) dependence.
  per-USER view (T kept): K needed to cover 50% / 100% of that user's targets
      (median across users, reported next to T). Full coverage is dominated by
      the single worst-ranked target — reported with that caveat, not instead
      of it. Targets outside the model's rankable index count as unrankable
      and are imputed at pool-size rank (honest floor).
Two target sets: A5 registered (most recent <=10) and ALL dated non-owned adds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.p6_common import (  # noqa: E402
    P4_DIR, P6_DIR, assert_firewall, build_relevance, build_wl_targets,
    graded_profile, load_artifacts, load_panels, load_wishlist_snapshot)
from pipeline.orchestration.p6_e5_challengers import ease_scores_vec  # noqa: E402
from pipeline.orchestration.ranker_gauntlet import EaseRanker  # noqa: E402

log = get_logger("orchestration.p6_wl_rank")
OUT = P6_DIR / "wl_rank_depth"
EVAL_N, EVAL_SEED = 400, 888


K_GRID = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
COVERAGE_LEVELS = (25, 50, 75, 90)


def depth_stats(ranks_by_user: dict[int, list[float]], pool_n: int) -> dict:
    all_r = np.array([r for v in ranks_by_user.values() for r in v])
    per_user_k100 = [float(max(v)) for v in ranks_by_user.values() if v]
    # per-user K needed to reach each coverage level (distribution, not max)
    per_user_kq = {q: [float(np.percentile(v, q)) for v in ranks_by_user.values() if v]
                   for q in COVERAGE_LEVELS}
    return {
        "n_targets": int(len(all_r)),
        "n_unrankable": int((all_r >= pool_n).sum()),
        "per_target_rank": {
            "median": int(np.median(all_r)), "p75": int(np.percentile(all_r, 75)),
            "p90": int(np.percentile(all_r, 90)),
        },
        # pooled CDF: share of ALL targets found within depth K
        "coverage_curve_pct": {str(k): round(float((all_r <= k).mean()) * 100, 1)
                               for k in K_GRID},
        # per-user K@coverage distributions (median [p25, p75] across users)
        "per_user_K": {
            **{f"K_for_{q}pct": {
                "median": int(np.median(per_user_kq[q])),
                "p25": int(np.percentile(per_user_kq[q], 25)),
                "p75": int(np.percentile(per_user_kq[q], 75))}
               for q in COVERAGE_LEVELS},
            "K_for_100pct": {
                "median": int(np.median(per_user_k100)),
                "p25": int(np.percentile(per_user_k100, 25)),
                "p75": int(np.percentile(per_user_k100, 75)),
                "note": "worst-target dominated; shown for completeness"},
        },
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inter, gs, us, pool = load_artifacts()
    panels = load_panels()
    rel = build_relevance(inter, pool)
    counts = rel.groupby("steamid").size()
    explo = [int(u) for u in panels["exploration"] if u in counts.index]
    rng = np.random.default_rng(EVAL_SEED)
    users = sorted(int(u) for u in rng.choice(explo, size=EVAL_N, replace=False))
    assert_firewall(users, panels)
    inc = sorted(set(explo) - set(users))
    panels_p4 = json.loads((P4_DIR / "panels.json").read_text())
    graph = sorted(set(panels_p4["train"]) | set(inc))

    scores = bs.compute("pvalue_lognorm_eb", inter, gs, us)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            scores[scores["s"] > 0][["steamid", "appid", "s"]].values}
    ez = EaseRanker(scores, graph, pool, lam=100.0)
    pool_n = len(pool)

    wl = load_wishlist_snapshot()
    owned_pairs = set(zip(inter["steamid"].astype(int), inter["appid"].astype(int)))
    tgt_a5 = build_wl_targets(users, pool, owned_pairs, wl)
    tgt_all = build_wl_targets(users, pool, owned_pairs, wl, max_t=10 ** 9)
    prof_all = {int(u): dict(zip(g["appid"].astype(int), g["rel"].astype(float)))
                for u, g in rel[rel["steamid"].isin(tgt_all)].groupby("steamid")}

    # POP order over graph users (ownership counts)
    d = inter[inter["appid"].isin(pool) & inter["steamid"].isin(set(graph))]
    pop_order = [int(a) for a in d.groupby("appid").size()
                 .sort_values(ascending=False).index]
    pop_rank_full = {a: r + 1 for r, a in enumerate(pop_order)}

    results = {}
    for label, tgt in (("A5_top10", tgt_a5), ("all_targets", tgt_all)):
        ease_ranks: dict[int, list[float]] = {}
        pop_ranks: dict[int, list[float]] = {}
        tsizes = []
        for u, ts in tgt.items():
            pa = prof_all.get(u, {})
            if not pa:
                continue
            prof = graded_profile(u, pa, smap, rel_fallback=pa)
            v = ease_scores_vec(ez, prof)
            if v is None:
                continue
            excl = set(int(a) for a in pa)
            order = [int(ez.items[j]) for j in np.argsort(-v)
                     if int(ez.items[j]) not in excl]
            rank_of = {a: r + 1 for r, a in enumerate(order)}
            ease_ranks[u] = [float(rank_of.get(a, pool_n)) for a in ts]
            pop_seq = [a for a in pop_order if a not in excl]
            pop_of = {a: r + 1 for r, a in enumerate(pop_seq)}
            pop_ranks[u] = [float(pop_of.get(a, pool_n)) for a in ts]
            tsizes.append(len(ts))
        results[label] = {
            "n_users": len(ease_ranks),
            "targets_per_user_T": {"mean": round(float(np.mean(tsizes)), 2),
                                   "median": float(np.median(tsizes)),
                                   "max": int(np.max(tsizes))},
            "ease": depth_stats(ease_ranks, pool_n),
            "pop": depth_stats(pop_ranks, pool_n),
        }
        log.info("%s: users=%d ease median target rank=%d", label,
                 len(ease_ranks), results[label]["ease"]["per_target_rank"]["median"])

    (OUT / "summary.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
