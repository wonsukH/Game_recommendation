"""D4 — the library-RICHNESS lever (the biggest untested data axis).

data_scaling.py measured the #users axis (more users -> +0.076 recall, sig). The
OTHER axis is per-user library richness. The crawl proxy caps liked-games at ~10
and the realized mean is just 3.05 (diagnostic). GetOwnedGames returns a user's
FULL owned library (often hundreds). Question: does feeding CF MORE of a user's
profile raise recall — i.e. would richer real libraries pay off?

Clean isolation: fix each user's hold-out set (30%), then reveal only the first p
profile games (p ∈ {1,2,3,5,8,...}) to CF; co-occurrence is fixed (leave-user-out
from train). Recall rising with p, on the SAME holdout, isolates the richness
effect. Eligible users need enough liked games to vary p AND keep a holdout.

This is a controlled offline proxy for the live lever (live GetOwnedGames needs
public profiles). Rising + non-saturating => integrate GetOwnedGames as the input.
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
from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.personalization_experiment import load_user_data, cf_scores  # noqa: E402

log = get_logger("orchestration.library_richness")
EXP = REPO_ROOT / "experiments"


def topk(acc, inv, prof, k):
    order = np.argsort(-acc)
    out, excl = [], set(prof)
    for j in order:
        if acc[j] <= 0:
            break
        a = inv.get(int(j))
        if a is not None and a not in excl:
            out.append(a)
        if len(out) >= k:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--n-users", type=int, default=200)
    ap.add_argument("--min-games", type=int, default=11)  # enough to test p up to 8 + holdout
    ap.add_argument("--profile-sizes", type=int, nargs="+", default=[1, 2, 3, 5, 8])
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--min-cooc", type=int, default=3)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-id", type=str, default=None)
    args = ap.parse_args()

    run_id = args.run_id or ("libraryrichness_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    maps = load_index_maps(args.data_dir / "index_maps.json")
    pool = set(int(a) for a in maps["appid2row"].keys())
    user_pt, game_avg = load_user_data(args.scores, pool, 7.0)

    elig = [u for u, g in user_pt.items() if len(g) >= args.min_games]
    log.info("eligible users (>=%d liked): %d", args.min_games, len(elig))
    rng = np.random.default_rng(args.seed)
    test = rng.choice(np.array(elig, dtype=object), size=min(args.n_users, len(elig)), replace=False).tolist()
    train = {u: set(user_pt[u].keys()) for u in user_pt if u not in set(test)}
    C, deg, col = build_cooccurrence(train)
    inv = {j: a for a, j in col.items()}

    # fixed holdout (30%) per user; profile_pool = the other 70%, ordered once
    splits = []
    for i, u in enumerate(sorted(test)):
        ap_ = list(user_pt[u].keys())
        r = np.random.default_rng(args.seed + i); r.shuffle(ap_)
        nhold = max(1, int(round(len(ap_) * 0.3)))
        hold = set(ap_[:nhold]); ppool = ap_[nhold:]
        if len(ppool) >= 1:
            splits.append((u, ppool, hold))

    per_p = {}
    for p in args.profile_sizes:
        recs = []
        for u, ppool, hold in splits:
            prof_ids = ppool[:min(p, len(ppool))]
            pw = [(a, pt_weight(user_pt[u][a], game_avg.get(a, 0.0))) for a in prof_ids]
            acc = cf_scores(pw, C, deg, col, args.min_cooc)
            recs.append(recall_at_k(hold, topk(acc, inv, {a: 1 for a in prof_ids}, args.k), args.k))
        per_p[p] = np.array(recs)
        log.info("p=%d recall@%d=%.4f", p, args.k, per_p[p].mean())

    results = {p: bootstrap_ci(per_p[p], B=args.bootstrap, seed=args.seed) for p in args.profile_sizes}
    lo_p, hi_p = args.profile_sizes[0], args.profile_sizes[-1]
    growth = paired_bootstrap_diff(per_p[lo_p], per_p[hi_p], B=args.bootstrap, seed=args.seed)
    monotonic = all(results[args.profile_sizes[i]]["mean"] <= results[args.profile_sizes[i + 1]]["mean"] + 1e-9
                    for i in range(len(args.profile_sizes) - 1))
    # marginal of the last step (saturation check)
    last_step = paired_bootstrap_diff(per_p[args.profile_sizes[-2]], per_p[hi_p], B=args.bootstrap, seed=args.seed)

    logger = RunLogger(run_id, EXP)
    logger.write_aggregate({"n_test": len(splits), "n_eligible": len(elig),
                            "by_profile_size": {str(p): results[p] for p in args.profile_sizes},
                            "growth_lo_to_hi": growth, "last_step": last_step, "monotonic": monotonic})
    L = [f"# D4 library-richness (profile-size) — run `{run_id}`", "",
         f"{len(splits)} users (>= {args.min_games} liked, {len(elig)} eligible), FIXED 30% holdout, "
         f"recall@{args.k}; reveal first p profile games to leave-user-out CF.", "",
         "| profile size p | recall@20 [CI] |", "|---|---|"]
    for p in args.profile_sizes:
        r = results[p]; L.append(f"| {p} | {r['mean']:.4f} [{r['lo']:.4f},{r['hi']:.4f}] |")
    L += ["",
          f"- p={lo_p}→{hi_p} Δ = {growth['mean_diff']:+.4f} [{growth['lo']:+.4f},{growth['hi']:+.4f}] "
          f"({'SIG' if growth['significant'] else 'ns'}); monotonic={monotonic}",
          f"- last step (p={args.profile_sizes[-2]}→{hi_p}) Δ = {last_step['mean_diff']:+.4f} "
          f"[{last_step['lo']:+.4f},{last_step['hi']:+.4f}] ({'SIG (not saturated)' if last_step['significant'] else 'ns (saturating)'})",
          "", "## 해석",
          "- recall이 p와 함께 유의·단조 상승 → **라이브러리 풍부도가 큰 레버** → GetOwnedGames(수백 게임) 입력이 프록시(평균 3) 대비 큰 이득. 라이브 통합 정당화.",
          "- last step 유의면 미포화(아직 더 늘릴 여지). ns면 수확체감 시작점.",
          "- 캡(10)보다 실현 평균(3.05)이 진짜 병목 — 풍부한 입력만으로 모델 변경 없이 개인화 향상."]
    logger.write_report("\n".join(L))
    logger.append_registry({"run_id": run_id, "phase": "D4-library-richness",
                            "recall_by_p": {str(p): float(per_p[p].mean()) for p in args.profile_sizes},
                            "growth": growth["mean_diff"], "growth_sig": growth["significant"],
                            "monotonic": monotonic, "last_step_sig": last_step["significant"]})
    dlog = EXP / "DELIBERATION_LOG.md"
    if dlog.exists():
        with open(dlog, "a", encoding="utf-8") as f:
            f.write(f"\n\n## (데이터 보강 D4) 라이브러리 풍부도 레버 — run `{run_id}`\n"
                    f"- recall@{args.k} by profile size: " + ", ".join(f"p{p}={per_p[p].mean():.4f}" for p in args.profile_sizes) + "\n"
                    f"- p{lo_p}→{hi_p} Δ={growth['mean_diff']:+.4f} ({'SIG' if growth['significant'] else 'ns'}), "
                    f"monotonic={monotonic}, last-step {'미포화' if last_step['significant'] else '수확체감'}.\n"
                    f"- 결론: 풍부도가 {'큰 레버 — GetOwnedGames 입력 정당' if growth['significant'] else '효과 제한적'}. "
                    f"실현 평균 3.05가 캡(10)보다 진짜 병목.\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
