"""Ranker benchmark — is our co-occurrence CF actually good vs traditional recsys?

Honest answer to "is this better than two-tower / classic recsys?": benchmark our
conditional-cosine item-item CF against the strong CLASSICAL baselines on the SAME
non-circular co-play hold-out:
  - Popularity        floor
  - CF (ours)         conditional cosine C[i,j]/sqrt(deg_i deg_j), playtime-weighted
  - EASE (Steck 2019) closed-form item-item ridge — the shallow model that beats
                      many neural methods (incl. two-tower) in controlled studies
  - ALS (Hu 2008)     implicit-feedback matrix factorization

EASE/ALS need no torch (numpy/scipy only). If a baseline wins, the honest move is
to ADOPT it as the ranker under the agent (the ranker is a swappable tool; the
agentic layer — NL, multi-entity, constraints, steering, explanation — is unchanged).

Same train/test split, item universe, metric (recall@20 + ndcg@20), bootstrap +
paired-bootstrap vs CF. Pre-registered: report whatever wins, including a CF loss.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.evaluation.coplay_labels import build_cooccurrence  # noqa: E402
from pipeline.game_rec.evaluation.metrics import recall_at_k, ndcg_at_k  # noqa: E402
from pipeline.game_rec.evaluation.stats import bootstrap_ci, paired_bootstrap_diff  # noqa: E402
from pipeline.game_rec.evaluation.run_logger import RunLogger  # noqa: E402
from pipeline.game_rec.agent.cf_recommender import pt_weight  # noqa: E402
from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.personalization_experiment import load_user_data, cf_scores  # noqa: E402

log = get_logger("orchestration.ranker_benchmark")
EXP = REPO_ROOT / "experiments"


# ---------------- models ----------------
def ease_B(X: csr_matrix, lam: float) -> np.ndarray:
    """Closed-form EASE item-item weights. X = users×items binary."""
    G = (X.T @ X).toarray().astype(np.float64)
    di = np.diag_indices(G.shape[0])
    G[di] += lam
    P = np.linalg.inv(G)
    B = -P / np.diag(P)[None, :]
    B[di] = 0.0
    return B


def als_factors(user_items: list[list[int]], item_users: list[list[int]], n_items: int,
                d: int, reg: float, alpha: float, iters: int, seed: int):
    """Implicit-feedback ALS (Hu et al. 2008), binary obs -> confidence 1+alpha."""
    rng = np.random.default_rng(seed)
    U = rng.standard_normal((len(user_items), d)).astype(np.float64) * 0.01
    V = rng.standard_normal((n_items, d)).astype(np.float64) * 0.01
    I = np.eye(d)

    def solve_side(factors_other, groups):
        out = np.zeros((len(groups), d))
        GtG = factors_other.T @ factors_other
        for i, obs in enumerate(groups):
            if not obs:
                continue
            Fo = factors_other[obs]
            A = GtG + alpha * (Fo.T @ Fo) + reg * I
            b = (1.0 + alpha) * Fo.sum(axis=0)
            out[i] = np.linalg.solve(A, b)
        return out

    for it in range(iters):
        U = solve_side(V, user_items)
        V = solve_side(U, item_users)
        log.info("ALS iter %d/%d done", it + 1, iters)
    return U, V


def als_foldin(profile_idx, V, reg, alpha):
    d = V.shape[1]
    Fo = V[profile_idx]
    A = (V.T @ V) + alpha * (Fo.T @ Fo) + reg * np.eye(d)
    b = (1.0 + alpha) * Fo.sum(axis=0)
    return np.linalg.solve(A, b)


def topk_from_vec(scores: np.ndarray, exclude_idx: set, k: int, inv_items) -> list:
    order = np.argsort(-scores)
    out = []
    for j in order:
        if scores[j] <= 0 and len(out) > 0:
            break
        if j in exclude_idx:
            continue
        out.append(inv_items[j])
        if len(out) >= k:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--methods", type=str, default="pop,cf,ease,als")
    ap.add_argument("--n-users", type=int, default=200)
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--min-support", type=int, default=3, help="item kept if liked by >= this many train users")
    ap.add_argument("--min-cooc", type=int, default=3)
    ap.add_argument("--ease-lambda", type=float, default=250.0)
    ap.add_argument("--als-d", type=int, default=64)
    ap.add_argument("--als-reg", type=float, default=10.0)
    ap.add_argument("--als-alpha", type=float, default=40.0)
    ap.add_argument("--als-iters", type=int, default=12)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-id", type=str, default=None)
    args = ap.parse_args()

    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    run_id = args.run_id or ("rankerbench_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    maps = load_index_maps(args.data_dir / "index_maps.json")
    pool = set(int(a) for a in maps["appid2row"].keys())
    user_pt, game_avg = load_user_data(args.scores, pool, 7.0)

    elig = [u for u, g in user_pt.items() if len(g) >= 4]
    rng = np.random.default_rng(args.seed)
    test = set(rng.choice(np.array(elig, dtype=object), size=min(args.n_users, len(elig)), replace=False).tolist())
    train = {u: set(user_pt[u].keys()) for u in user_pt if u not in test}

    # shared item universe: items liked by >= min_support train users
    counts = Counter()
    for liked in train.values():
        counts.update(liked)
    items = sorted(a for a, c in counts.items() if c >= args.min_support)
    idx = {a: i for i, a in enumerate(items)}
    inv_items = {i: a for a, i in idx.items()}
    n_items = len(items)
    log.info("train users=%d, item universe=%d (support>=%d)", len(train), n_items, args.min_support)

    # train user×item binary matrix (for EASE/ALS)
    rows, cols = [], []
    train_user_list = list(train.keys())
    user_items_idx = []
    for ui, u in enumerate(train_user_list):
        obs = [idx[a] for a in train[u] if a in idx]
        user_items_idx.append(obs)
        for j in obs:
            rows.append(ui); cols.append(j)
    X = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(train_user_list), n_items))

    # ----- build models -----
    models = {}
    if "pop" in methods:
        models["pop"] = np.asarray(X.sum(axis=0)).ravel()  # item popularity
    if "cf" in methods:
        C, deg, col = build_cooccurrence(train)
        cf_inv = {j: a for a, j in col.items()}
        models["cf"] = (C, deg, col, cf_inv)
    if "ease" in methods:
        log.info("building EASE (inv %dx%d)...", n_items, n_items)
        models["ease"] = ease_B(X, args.ease_lambda)
    if "als" in methods:
        item_users_idx = [[] for _ in range(n_items)]
        for ui, obs in enumerate(user_items_idx):
            for j in obs:
                item_users_idx[j].append(ui)
        log.info("training ALS d=%d iters=%d ...", args.als_d, args.als_iters)
        _, V = als_factors(user_items_idx, item_users_idx, n_items, args.als_d,
                           args.als_reg, args.als_alpha, args.als_iters, args.seed)
        models["als"] = V

    # ----- eval -----
    recalls = {m: [] for m in methods}
    ndcgs = {m: [] for m in methods}
    for n, u in enumerate(sorted(test)):
        ap_ = list(user_pt[u].keys())
        r = np.random.default_rng(args.seed + n); r.shuffle(ap_)
        nprof = max(1, int(round(len(ap_) * 0.7)))
        if len(ap_) - nprof < 1:
            continue
        prof = ap_[:nprof]; hold = set(ap_[nprof:])
        prof_idx = [idx[a] for a in prof if a in idx]
        excl_idx = set(prof_idx)

        for m in methods:
            if m == "pop":
                top = topk_from_vec(models["pop"], excl_idx, args.k, inv_items)
            elif m == "cf":
                C, deg, col, cf_inv = models["cf"]
                pw = [(a, pt_weight(user_pt[u][a], game_avg.get(a, 0.0))) for a in prof]
                acc = cf_scores(pw, C, deg, col, args.min_cooc)
                order = np.argsort(-acc); top, ex = [], set(prof)
                for j in order:
                    if acc[j] <= 0:
                        break
                    a = cf_inv.get(int(j))
                    if a is not None and a not in ex:
                        top.append(a)
                    if len(top) >= args.k:
                        break
            elif m == "ease":
                if not prof_idx:
                    top = []
                else:
                    s = models["ease"][prof_idx, :].sum(axis=0)
                    top = topk_from_vec(s, excl_idx, args.k, inv_items)
            elif m == "als":
                if not prof_idx:
                    top = []
                else:
                    xu = als_foldin(prof_idx, models["als"], args.als_reg, args.als_alpha)
                    s = models["als"] @ xu
                    top = topk_from_vec(s, excl_idx, args.k, inv_items)
            recalls[m].append(recall_at_k(hold, top, args.k))
            ndcgs[m].append(ndcg_at_k(hold, top, args.k))

    # ----- stats -----
    res = {}
    base = "cf" if "cf" in methods else methods[0]
    for m in methods:
        rc = np.array(recalls[m]); nd = np.array(ndcgs[m])
        res[m] = {"recall": bootstrap_ci(rc, B=args.bootstrap, seed=args.seed),
                  "ndcg": bootstrap_ci(nd, B=args.bootstrap, seed=args.seed)}
    diffs = {}
    for m in methods:
        if m == base:
            continue
        diffs[m] = {
            "recall": paired_bootstrap_diff(np.array(recalls[base]), np.array(recalls[m]), B=args.bootstrap, seed=args.seed),
            "ndcg": paired_bootstrap_diff(np.array(ndcgs[base]), np.array(ndcgs[m]), B=args.bootstrap, seed=args.seed)}
    winner = max(methods, key=lambda m: res[m]["recall"]["mean"])

    logger = RunLogger(run_id, EXP)
    logger.write_aggregate({"n_test": len(recalls[base]), "n_items": n_items, "by_method": res,
                            "diffs_vs_%s" % base: diffs, "winner": winner,
                            "params": {"ease_lambda": args.ease_lambda, "als_d": args.als_d,
                                       "als_reg": args.als_reg, "als_alpha": args.als_alpha, "als_iters": args.als_iters}})
    L = [f"# Ranker benchmark — CF vs classical recsys — run `{run_id}`", "",
         f"{len(recalls[base])} hold-out users, recall@{args.k}/ndcg@{args.k}, item universe {n_items} "
         f"(support>={args.min_support}), leave-user-out. base = {base}.", "",
         "| method | recall@20 [CI] | ndcg@20 [CI] | Δrecall vs CF |", "|---|---|---|---|"]
    for m in methods:
        d = diffs.get(m, {}).get("recall")
        ds = f"{d['mean_diff']:+.4f} [{d['lo']:+.4f},{d['hi']:+.4f}] {'SIG' if d['significant'] else 'ns'}" if d else "—(base)"
        L.append(f"| {m} | {res[m]['recall']['mean']:.4f} [{res[m]['recall']['lo']:.4f},{res[m]['recall']['hi']:.4f}] | "
                 f"{res[m]['ndcg']['mean']:.4f} [{res[m]['ndcg']['lo']:.4f},{res[m]['ndcg']['hi']:.4f}] | {ds} |")
    L += ["", f"- **winner (recall): {winner}**",
          "", "## 해석",
          "- EASE/ALS가 CF를 유의하게 이기면 → 그게 에이전트 밑 랭커로 채택할 후보(품질 향상). CF가 비등/우위면 단순 CF 유지 정당.",
          "- 어느 쪽이든 '두 타워보다 낫다'는 직접 주장은 아님(EASE는 통제연구에서 다수 neural을 이기는 강baseline이므로, EASE 대비 위치가 곧 전통 recsys 대비 위치의 보수적 하한).",
          "- 랭커는 교체 가능한 도구 — agentic 레이어(NL·다중주체·제약·스티어링·설명)는 불변."]
    logger.write_report("\n".join(L))
    logger.append_registry({"run_id": run_id, "phase": "ranker-benchmark",
                            "recall": {m: res[m]["recall"]["mean"] for m in methods},
                            "winner": winner,
                            "diff_vs_cf": {m: diffs[m]["recall"]["mean_diff"] for m in diffs}})
    dlog = EXP / "DELIBERATION_LOG.md"
    if dlog.exists():
        with open(dlog, "a", encoding="utf-8") as f:
            f.write(f"\n\n## (랭커 벤치마크) CF vs EASE vs ALS — run `{run_id}`\n"
                    f"- recall@{args.k}: " + ", ".join(f"{m}={res[m]['recall']['mean']:.4f}" for m in methods) + "\n"
                    f"- winner={winner}. Δrecall vs CF: "
                    + ", ".join(f"{m}={diffs[m]['recall']['mean_diff']:+.4f}({'SIG' if diffs[m]['recall']['significant'] else 'ns'})" for m in diffs) + "\n"
                    f"- 해석: EASE 대비 위치 = 전통 recsys 대비 보수적 하한. 이기는 랭커를 에이전트 밑에 채택(교체 가능).\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
