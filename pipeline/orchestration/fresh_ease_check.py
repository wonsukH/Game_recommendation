"""Confirm the corrected ranker winner (EASE l100, fair) on the FRESH zero-exposure
panel — same robustness bar knnpd03 was held to (T29). Fresh users = accrued,
never in train/dev/private, so the CF graph (frozen train) never saw them.
ease_l100(fair) vs userknn/knnpd03/condcos on graded-NDCG, paired bootstrap
ease-vs-userknn. Read-only; fresh panel (not private, not tuning dev)."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    build_relevance, get_panels, graded_ndcg, load_artifacts,
    split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import EaseRanker, UserKNN, VariantCF  # noqa: E402
from pipeline.orchestration.ease_recheck import ease_reclist  # noqa: E402

log = get_logger("orchestration.fresh_ease")
rng = np.random.default_rng(5)


def pboot(diff, n=5000):
    diff = np.asarray([d for d in diff if np.isfinite(d)], float)
    b = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(n)]
    return float(diff.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main() -> int:
    inter, gs, us, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    frozen = set(panels["train"]) | set(panels["dev"]) | set(panels["private"])
    cnt = rel.groupby("steamid").size()
    fresh = sorted(u for u in cnt[cnt >= 12].index if int(u) not in frozen)
    log.info("fresh zero-exposure users (>=12 items): %d", len(fresh))
    splits = split_profile_holdout(rel, fresh, seed=42)
    uu = sorted(splits)

    sc = bs.compute("pvalue_lognorm_eb", inter, gs, us)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            sc[sc["s"] > 0][["steamid", "appid", "s"]].values}
    knn = UserKNN(sc, panels["train"], pool, topk_users=25)
    knn_pd = UserKNN(sc, panels["train"], pool, topk_users=25, pop_beta=0.3)
    cc = VariantCF(sc, panels["train"], pool, kind="condcos")
    ez = EaseRanker(sc, panels["train"], pool, lam=100.0)
    need = sorted({a for u in splits for a in splits[u]["profile"]})
    ccS, ccA = cc.sim_columns(need)

    def profw(u, sp):
        p = {a: smap.get((u, a), 0.0) for a in sp["profile"]}
        return {a: w for a, w in p.items() if w > 0} or dict(sp["profile"])

    rec = {
        "ease_l100_fair": lambda u, p, k, e: ease_reclist(ez, p, k, e),
        "knnpd03": lambda u, p, k, e: knn_pd.recommend(p, k, e),
        "userknn25": lambda u, p, k, e: knn.recommend(p, k, e),
        "condcos": lambda u, p, k, e: cc.recommend(p, ccS, ccA, k, e),
    }
    nd = {n: {} for n in rec}
    for name, fn in rec.items():
        for u, sp in splits.items():
            r = fn(u, profw(u, sp), 20, set(sp["profile"]))
            nd[name][u] = graded_ndcg(sp["holdout"], r, k=20)

    print(f"\nFRESH zero-exposure panel (n={len(uu)})")
    print(f"{'ranker':16s} {'NDCG':>8s}")
    for name in rec:
        print(f"{name:16s} {np.mean([nd[name][u] for u in uu]):8.4f}")
    m, lo, hi = pboot([nd["ease_l100_fair"][u] - nd["userknn25"][u] for u in uu])
    print(f"  ease_l100 - userknn25 = {m:+.4f} [{lo:+.4f},{hi:+.4f}] "
          f"{'SIG' if (lo>0 or hi<0) else 'ns'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
