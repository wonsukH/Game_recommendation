"""Data-scaling ablation — does MORE data improve the CF moat?

Two data axes:
  (1) #users in the co-occurrence  -> testable NOW by subsampling existing users.
  (2) richness per user (library size; capped ~10 here by the crawl bug) -> needs
      GetOwnedGames crawl (NOT done); only notable here, not measured.

This measures axis (1): build co-occurrence from {25,50,75,100}% of the (non-test)
users, evaluate hold-out recall@20 on a FIXED test set. Rising recall => more
users helps (and extrapolates that richer libraries would help too).
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

log = get_logger("orchestration.data_scaling")
EXP = REPO_ROOT / "experiments"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--n-users", type=int, default=120)
    ap.add_argument("--fractions", type=float, nargs="+", default=[0.25, 0.5, 0.75, 1.0])
    ap.add_argument("--min-cooc", type=int, default=3)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-id", type=str, default=None)
    args = ap.parse_args()

    run_id = args.run_id or ("datascaling_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    maps = load_index_maps(args.data_dir / "index_maps.json")
    pool = set(int(a) for a in maps["appid2row"].keys())
    user_pt, game_avg = load_user_data(args.scores, pool, 7.0)

    elig = [u for u, g in user_pt.items() if len(g) >= 8]
    rng = np.random.default_rng(args.seed)
    test = set(rng.choice(np.array(elig, dtype=object), size=min(args.n_users, len(elig)), replace=False).tolist())
    train_users = [u for u in user_pt if u not in test]
    rng.shuffle(train_users)

    # fixed profile/holdout per test user
    splits = {}
    for i, u in enumerate(sorted(test)):
        ap_ = list(user_pt[u].keys())
        r = np.random.default_rng(args.seed + i); r.shuffle(ap_)
        n = max(1, int(round(len(ap_) * 0.7)))
        if len(ap_) - n >= 1:
            splits[u] = (ap_[:n], set(ap_[n:]))

    results = {}
    per_frac_recall = {}
    for frac in args.fractions:
        m = int(len(train_users) * frac)
        sub = {u: set(user_pt[u].keys()) for u in train_users[:m]}
        C, deg, col = build_cooccurrence(sub)
        inv = {j: a for a, j in col.items()}
        recs = []
        for u, (prof, hold) in splits.items():
            pw = [(a, pt_weight(user_pt[u][a], game_avg.get(a, 0.0))) for a in prof]
            acc = cf_scores(pw, C, deg, col, args.min_cooc)
            order = np.argsort(-acc)
            top = []
            excl = set(prof)
            for j in order:
                if acc[j] <= 0:
                    break
                a = inv.get(int(j))
                if a is not None and a not in excl:
                    top.append(a)
                if len(top) >= 20:
                    break
            recs.append(recall_at_k(hold, top, 20))
        per_frac_recall[frac] = np.array(recs)
        results[frac] = {"n_users": m, "recall@20": bootstrap_ci(np.array(recs), B=args.bootstrap, seed=args.seed)}
        log.info("frac=%.2f users=%d recall@20=%.3f", frac, m, results[frac]["recall@20"]["mean"])

    lo, hi = min(args.fractions), max(args.fractions)
    growth = paired_bootstrap_diff(per_frac_recall[lo], per_frac_recall[hi], B=args.bootstrap, seed=args.seed)

    logger = RunLogger(run_id, EXP)
    logger.write_aggregate({"by_fraction": results, "growth_lo_to_hi": growth})
    L = [f"# Data-scaling (user-count axis) — run `{run_id}`", "",
         f"Fixed {len(splits)} test users, hold-out recall@20; co-occurrence from X% of "
         f"{len(train_users)} train users.", "",
         "| users | recall@20 [CI] |", "|---|---|"]
    for frac in args.fractions:
        r = results[frac]
        L.append(f"| {r['n_users']} ({int(frac*100)}%) | {r['recall@20']['mean']:.3f} "
                 f"[{r['recall@20']['lo']:.3f},{r['recall@20']['hi']:.3f}] |")
    monotonic = all(results[args.fractions[i]]["recall@20"]["mean"] <= results[args.fractions[i+1]]["recall@20"]["mean"] + 1e-9
                    for i in range(len(args.fractions)-1))
    L += ["",
          f"- {int(lo*100)}%→{int(hi*100)}% recall Δ = {growth['mean_diff']:+.3f} "
          f"[{growth['lo']:+.3f},{growth['hi']:+.3f}] ({'SIG' if growth['significant'] else 'ns'})",
          f"- monotonic increasing: {monotonic}",
          "", "## 해석",
          "- 유저 수↑ → recall 추세로 데이터 가치 판단. SIG 상승 & 미포화면 '더 늘리면 더 좋아짐'.",
          "- (미측정) 유저당 라이브러리 풍부도(캡~10→GetOwnedGames 수백)는 더 큰 레버일 가능성 — 크롤 필요."]
    logger.write_report("\n".join(L))
    logger.append_registry({"run_id": run_id, "phase": "data-scaling-users",
                            "recall_by_users": {results[f]["n_users"]: results[f]["recall@20"]["mean"] for f in args.fractions},
                            "growth_sig": growth["significant"], "growth": growth["mean_diff"]})
    dlog = EXP / "DELIBERATION_LOG.md"
    if dlog.exists():
        with open(dlog, "a", encoding="utf-8") as f:
            f.write(f"\n\n## (데이터 스케일링) 유저 수 축 — run `{run_id}`\n"
                    f"- recall@20 by users: " + ", ".join(f"{results[fr]['n_users']}={results[fr]['recall@20']['mean']:.3f}" for fr in args.fractions) + "\n"
                    f"- {int(lo*100)}→{int(hi*100)}% Δ={growth['mean_diff']:+.3f} ({'SIG' if growth['significant'] else 'ns'}), monotonic={monotonic}. "
                    f"라이브러리 풍부도(GetOwnedGames)는 미측정.\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
