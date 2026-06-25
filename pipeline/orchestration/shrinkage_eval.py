"""D3 — does low-support shrinkage help the CF moat?

Diagnostic: CF co-occurrence is sparse (deg median 9; 71% of items have deg<30).
The conditional cosine C[g,p]/sqrt(deg[g]·deg[p]) with a min_cooc>=3 floor still
trusts a c=3 pair as much as a c=300 pair (up to the cosine denom). A standard fix
is a support-confidence shrinkage factor  C/(C+λ)  that smoothly down-weights
low-co-occurrence pairs.

This sweeps λ ∈ {0,1,3,5,10} (λ=0 == current baseline), hold-out recall@20,
leave-user-out, paired bootstrap vs λ=0. PRE-REGISTERED: adopt only if some λ
beats λ=0 with a 95% CI excluding 0; otherwise report null and DROP (no
goal-post moving).
"""

from __future__ import annotations

import argparse
import math
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
from pipeline.orchestration.personalization_experiment import load_user_data  # noqa: E402

log = get_logger("orchestration.shrinkage_eval")
EXP = REPO_ROOT / "experiments"


def cf_scores_shrunk(profile_weighted, C, deg, col, min_cooc, lam):
    """Conditional cosine with optional support shrinkage C/(C+λ)."""
    acc = np.zeros(C.shape[0], dtype=np.float64)
    for appid, w in profile_weighted:
        j = col.get(appid)
        if j is None:
            continue
        row = C.getrow(j).tocoo()
        dj = deg[j]
        for g, c in zip(row.col, row.data):
            if c < min_cooc or g == j:
                continue
            denom = math.sqrt(dj * deg[g])
            if denom > 0:
                sim = c / denom
                if lam > 0:
                    sim *= c / (c + lam)
                acc[g] += w * sim
    return acc


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
    ap.add_argument("--n-users", type=int, default=150)
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--min-cooc", type=int, default=3)
    ap.add_argument("--lambdas", type=float, nargs="+", default=[0, 1, 3, 5, 10])
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-id", type=str, default=None)
    args = ap.parse_args()

    run_id = args.run_id or ("shrinkage_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    maps = load_index_maps(args.data_dir / "index_maps.json")
    pool = set(int(a) for a in maps["appid2row"].keys())
    user_pt, game_avg = load_user_data(args.scores, pool, 7.0)

    elig = [u for u, g in user_pt.items() if len(g) >= 4]
    rng = np.random.default_rng(args.seed)
    test = set(rng.choice(np.array(elig, dtype=object), size=min(args.n_users, len(elig)), replace=False).tolist())
    train = {u: set(user_pt[u].keys()) for u in user_pt if u not in test}
    C, deg, col = build_cooccurrence(train)
    inv = {j: a for a, j in col.items()}

    splits = []
    for i, u in enumerate(sorted(test)):
        ap_ = list(user_pt[u].keys())
        r = np.random.default_rng(args.seed + i); r.shuffle(ap_)
        nprof = max(1, int(round(len(ap_) * 0.7)))
        if len(ap_) - nprof < 1:
            continue
        splits.append((u, {a: user_pt[u][a] for a in ap_[:nprof]}, set(ap_[nprof:])))

    per_lam = {}
    for lam in args.lambdas:
        recs = []
        for u, prof, hold in splits:
            pw = [(a, pt_weight(prof[a], game_avg.get(a, 0.0))) for a in prof]
            acc = cf_scores_shrunk(pw, C, deg, col, args.min_cooc, lam)
            recs.append(recall_at_k(hold, topk(acc, inv, prof, args.k), args.k))
        per_lam[lam] = np.array(recs)
        log.info("lambda=%.1f recall@%d=%.4f", lam, args.k, per_lam[lam].mean())

    base = per_lam[0.0] if 0.0 in per_lam else per_lam[args.lambdas[0]]
    results = {}
    best_lam, best_mean = 0.0, base.mean()
    for lam in args.lambdas:
        ci = bootstrap_ci(per_lam[lam], B=args.bootstrap, seed=args.seed)
        diff = paired_bootstrap_diff(base, per_lam[lam], B=args.bootstrap, seed=args.seed)  # lam - base
        results[lam] = {"recall": ci, "diff_vs_base": diff}
        if lam != 0.0 and per_lam[lam].mean() > best_mean:
            best_mean, best_lam = per_lam[lam].mean(), lam
    adopt = best_lam != 0.0 and results[best_lam]["diff_vs_base"]["significant"] and \
        results[best_lam]["diff_vs_base"]["mean_diff"] > 0

    logger = RunLogger(run_id, EXP)
    logger.write_aggregate({"by_lambda": {str(l): results[l] for l in args.lambdas},
                            "best_lambda": best_lam, "adopt": adopt})
    L = [f"# D3 support-shrinkage sweep — run `{run_id}`", "",
         f"{len(splits)} hold-out users, recall@{args.k}, leave-user-out. "
         f"sim ·= C/(C+λ). λ=0 is the current baseline.", "",
         "| λ | recall@20 [CI] | Δ vs λ=0 [CI] |", "|---|---|---|"]
    for lam in args.lambdas:
        r = results[lam]; d = r["diff_vs_base"]
        L.append(f"| {lam:g} | {r['recall']['mean']:.4f} [{r['recall']['lo']:.4f},{r['recall']['hi']:.4f}] | "
                 f"{d['mean_diff']:+.4f} [{d['lo']:+.4f},{d['hi']:+.4f}] {'SIG' if d['significant'] else 'ns'} |")
    L += ["", f"- best λ={best_lam:g} ({best_mean:.4f}); **adopt={adopt}** "
          f"(pre-registered: only if Δ>0 with CI excluding 0).",
          "", "## 해석",
          "- 채택이면 저-support 쌍 down-weight가 sparse 공출현에서 신호↑.",
          "- 미채택이면 정직히 드롭: min_cooc≥3 floor + conditional-cosine이 이미 충분(추가 shrinkage 무익)."]
    logger.write_report("\n".join(L))
    logger.append_registry({"run_id": run_id, "phase": "D3-shrinkage",
                            "best_lambda": best_lam, "adopt": adopt,
                            "recall_by_lambda": {str(l): float(per_lam[l].mean()) for l in args.lambdas}})
    dlog = EXP / "DELIBERATION_LOG.md"
    if dlog.exists():
        with open(dlog, "a", encoding="utf-8") as f:
            f.write(f"\n\n## (데이터 보강 D3) 저-support shrinkage — run `{run_id}`\n"
                    f"- recall@{args.k} by λ: " + ", ".join(f"{l:g}={per_lam[l].mean():.4f}" for l in args.lambdas) + "\n"
                    f"- best λ={best_lam:g}, **adopt={adopt}** (사전등록: Δ>0 & CI 0 제외 시만). "
                    f"{'채택' if adopt else '미채택 → 정직히 드롭(기존 conditional-cosine+min_cooc로 충분)'}.\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
