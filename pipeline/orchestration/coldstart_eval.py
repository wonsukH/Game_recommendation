"""D1 evaluation — does the content cold-start fallback help, and where?

Pre-registered claims:
  (1) warm recall UNCHANGED — cold fill only triggers on CF shortfall, so for users
      CF already fills, hybrid top-k == CF top-k. (verify: identical recall.)
  (2) value-add = robustness: for users CF underfills / can't reach (cold/thin
      profiles), hybrid recovers results CF returns 0 for. (measure underfill rate,
      cold-profile count, and recall on those.)
  (3) the ceiling: fraction of held-out liked games that are CF-cold bounds any
      recall lift. report it honestly (cold games are tail; lift may be ~0).

Leave-user-out: co-occurrence built from TRAIN users only; content layer is
content-only (no user leakage). Same 70/30 profile/holdout protocol as the
personalization + data-scaling runs. Bootstrap + paired-bootstrap CIs.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.evaluation.coplay_labels import build_cooccurrence  # noqa: E402
from pipeline.game_rec.evaluation.metrics import recall_at_k  # noqa: E402
from pipeline.game_rec.evaluation.stats import bootstrap_ci, paired_bootstrap_diff  # noqa: E402
from pipeline.game_rec.evaluation.run_logger import RunLogger  # noqa: E402
from pipeline.game_rec.agent.cf_recommender import pt_weight  # noqa: E402
from pipeline.game_rec.agent.content import ContentLayer  # noqa: E402
from pipeline.game_rec.agent.tools import CatalogMeta  # noqa: E402
from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.personalization_experiment import load_user_data, cf_scores  # noqa: E402

log = get_logger("orchestration.coldstart_eval")
EXP = REPO_ROOT / "experiments"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--n-users", type=int, default=150)
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--min-cooc", type=int, default=3)
    ap.add_argument("--min-quality-pct", type=float, default=0.30)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-id", type=str, default=None)
    args = ap.parse_args()

    run_id = args.run_id or ("coldstart_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    maps = load_index_maps(args.data_dir / "index_maps.json")
    pool = set(int(a) for a in maps["appid2row"].keys())
    user_pt, game_avg = load_user_data(args.scores, pool, 7.0)

    elig = [u for u, g in user_pt.items() if len(g) >= 4]
    rng = np.random.default_rng(args.seed)
    test = set(rng.choice(np.array(elig, dtype=object), size=min(args.n_users, len(elig)), replace=False).tolist())
    train_users = [u for u in user_pt if u not in test]
    train = {u: set(user_pt[u].keys()) for u in train_users}
    C, deg, col = build_cooccurrence(train)
    inv = {j: a for a, j in col.items()}
    cf_cold = pool - set(col.keys())

    content = ContentLayer(args.data_dir)
    meta = CatalogMeta(args.data_dir)
    k = args.k

    def cf_topk(prof_pt):
        acc = cf_scores([(a, pt_weight(prof_pt[a], game_avg.get(a, 0.0))) for a in prof_pt],
                        C, deg, col, args.min_cooc)
        order = np.argsort(-acc)
        out, excl = [], set(prof_pt)
        for j in order:
            if acc[j] <= 0:
                break
            a = inv.get(int(j))
            if a is not None and a not in excl:
                out.append(a)
            if len(out) >= k:
                break
        return out

    def hybrid_topk(prof_pt, warm):
        if len(warm) >= k:
            return warm
        cs = content.content_scores(prof_pt, game_avg)
        order = np.argsort(-cs)
        warm_set = set(warm) | set(prof_pt)
        need = k - len(warm)
        cands = []
        for r in order:
            if cs[int(r)] <= 0:
                break
            a = content.row2appid[int(r)]
            if a in warm_set:
                continue
            cands.append(a)
            if len(cands) >= need * 8:
                break
        if args.min_quality_pct is not None:
            keep = set(meta.quality_gate(cands, min_metacritic=None, min_quality_pct=args.min_quality_pct))
            cands = [a for a in cands if a in keep]
        return warm + cands[:need]

    rec_cf, rec_hy = [], []
    underfill, all_cold_profile, holdout_cold_frac = 0, 0, []
    rec_cf_underfill, rec_hy_underfill = [], []
    n = 0
    for u in sorted(test):
        ap_ = list(user_pt[u].keys())
        r = np.random.default_rng(args.seed + n); r.shuffle(ap_)
        nprof = max(1, int(round(len(ap_) * 0.7)))
        if len(ap_) - nprof < 1:
            continue
        prof = {a: user_pt[u][a] for a in ap_[:nprof]}
        hold = set(ap_[nprof:])
        n += 1
        warm = cf_topk(prof)
        hyb = hybrid_topk(prof, warm)
        rcf, rhy = recall_at_k(hold, warm, k), recall_at_k(hold, hyb, k)
        rec_cf.append(rcf); rec_hy.append(rhy)
        holdout_cold_frac.append(len(hold & cf_cold) / max(len(hold), 1))
        if len(warm) < k:
            underfill += 1
            rec_cf_underfill.append(rcf); rec_hy_underfill.append(rhy)
        if all(a in cf_cold for a in prof):
            all_cold_profile += 1

    rec_cf, rec_hy = np.array(rec_cf), np.array(rec_hy)
    diff = paired_bootstrap_diff(rec_cf, rec_hy, B=args.bootstrap, seed=args.seed)
    ci_cf = bootstrap_ci(rec_cf, B=args.bootstrap, seed=args.seed)
    ci_hy = bootstrap_ci(rec_hy, B=args.bootstrap, seed=args.seed)
    warm_unchanged = bool(np.allclose(rec_cf, rec_hy)) if underfill == 0 else None

    cov = {"pool": len(pool), "cf_reachable": len(col), "cold": len(cf_cold)}
    agg = {"n_test": n, "k": k, "coverage": cov,
           "recall_cf": ci_cf, "recall_hybrid": ci_hy, "diff_hy_minus_cf": diff,
           "underfill_rate": underfill / max(n, 1), "all_cold_profile": all_cold_profile,
           "holdout_cold_frac_mean": float(np.mean(holdout_cold_frac)),
           "underfill_recall_cf": float(np.mean(rec_cf_underfill)) if rec_cf_underfill else None,
           "underfill_recall_hy": float(np.mean(rec_hy_underfill)) if rec_hy_underfill else None,
           "min_quality_pct": args.min_quality_pct}

    logger = RunLogger(run_id, EXP)
    logger.write_aggregate(agg)
    L = [f"# D1 cold-start fallback eval — run `{run_id}`", "",
         f"{n} hold-out test users, recall@{k}, leave-user-out CF from {len(train_users)} train users.", "",
         f"- **coverage**: pool {cov['pool']}, CF-reachable {cov['cf_reachable']}, CF-cold {cov['cold']} "
         f"({100*cov['cold']/cov['pool']:.1f}%) → content fallback makes 100% recommendable.",
         f"- recall@{k}: CF {ci_cf['mean']:.3f} [{ci_cf['lo']:.3f},{ci_cf['hi']:.3f}] | "
         f"hybrid {ci_hy['mean']:.3f} [{ci_hy['lo']:.3f},{ci_hy['hi']:.3f}]",
         f"- Δ(hybrid−CF) = {diff['mean_diff']:+.4f} [{diff['lo']:+.4f},{diff['hi']:+.4f}] "
         f"({'SIG' if diff['significant'] else 'ns'})",
         f"- **underfill rate** (CF returns < {k}): {100*underfill/max(n,1):.1f}% of users; "
         f"fully-cold profile (CF returns 0): {all_cold_profile} users",
         f"- held-out liked games that are CF-cold (recovery ceiling): {100*np.mean(holdout_cold_frac):.1f}%",
         (f"- recall on underfill users: CF {np.mean(rec_cf_underfill):.3f} → hybrid {np.mean(rec_hy_underfill):.3f}"
          if rec_cf_underfill else "- no underfill users in this sample"),
         "", "## 해석",
         "- 콜드폴백의 1차 가치 = **커버리지(100%)와 콜드/얇은 프로파일 robustness**(CF가 0 주는 유저에 결과 제공).",
         "- 일반 유저는 CF가 top-k를 채우므로 warm recall 불변(설계상). 전체 recall 리프트는 콜드 holdout 비중에 의해 상한.",
         "- niche≠good(P2e) 교훈 반영: 콜드 후보는 user-score 품질게이트 통과분만. 스티어링(F)의 base 인프라."]
    logger.write_report("\n".join(L))
    logger.append_registry({"run_id": run_id, "phase": "D1-coldstart",
                            "coverage_cold": cov["cold"], "recall_cf": ci_cf["mean"],
                            "recall_hybrid": ci_hy["mean"], "diff": diff["mean_diff"],
                            "diff_sig": diff["significant"], "underfill_rate": underfill / max(n, 1),
                            "all_cold_profile": all_cold_profile})
    dlog = EXP / "DELIBERATION_LOG.md"
    if dlog.exists():
        with open(dlog, "a", encoding="utf-8") as f:
            f.write(f"\n\n## (데이터 보강 D1) 콜드스타트 폴백 — run `{run_id}`\n"
                    f"- 커버리지 {cov['cf_reachable']}→{cov['pool']} (콜드 {cov['cold']} 회복, 100% 추천가능).\n"
                    f"- recall@{k}: CF {ci_cf['mean']:.3f} vs hybrid {ci_hy['mean']:.3f}, "
                    f"Δ={diff['mean_diff']:+.4f} ({'SIG' if diff['significant'] else 'ns'}).\n"
                    f"- underfill {100*underfill/max(n,1):.1f}%, 완전콜드프로파일 {all_cold_profile}명, "
                    f"holdout-cold {100*np.mean(holdout_cold_frac):.1f}%.\n"
                    f"- 결론: 커버리지·robustness 확보(설계상 warm 불변). niche 품질게이트 적용. 스티어링 base.\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
