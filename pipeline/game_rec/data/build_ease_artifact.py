"""P5 — EASE serving-artifact builder (steam.db snapshot -> sparse top-K B).

Packages the P6-confirmed serving ranker (EASE λ=100 × pctl_game preference)
as a compact serving artifact. The full model is too large to persist naively
(dense V ≈ GBs at the current 23k-user scale), so:

  1. FIT on a seeded uniform subsample of usable users (--cap, default 12,000,
     >=--min-items positive-preference items each) — float32 dense Gram,
     float64 inverse (numerical safety), user-space Woodbury factors.
  2. Materialize EXACT rows of B chunk-by-chunk (the validated EasePositiveB
     math from the E5 T-a ablation), keep the top-K entries per row by |value|
     — NEGATIVE weights included (T-a: clipping them costs -0.0088 SIG).
  3. Persist to serving/data/ease/: B_topk.npz (CSR), items.npy, pt_ecdf.npz
     (per-item playtime-quantile grid so a NEW user's pctl_game weight can be
     interpolated at serving time), meta.json (lam/cap/seed/K/git/source).

Acceptance is gated by pipeline/orchestration/p5_validate.py (sparse-B must be
paired-ns / Δ >= -0.005 vs exact scoring on the exploration pool).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import sparse

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("data.build_ease_artifact")

OUT_DEFAULT = REPO_ROOT / "serving" / "data" / "ease"
ART_DEFAULT = REPO_ROOT / "outputs" / "p5"
ECDF_QS = np.linspace(0.0, 1.0, 21)


def load_snapshot(art_dir: Path):
    import pandas as pd
    inter = pd.read_pickle(art_dir / "interactions.pkl")
    game_stats = pd.read_pickle(art_dir / "game_stats.pkl")
    user_stats = pd.read_pickle(art_dir / "user_stats.pkl")
    pool = set(json.loads((art_dir / "pool.json").read_text())["pool"])
    return inter, game_stats, user_stats, pool


def select_graph_users(scores, cap: int, min_items: int, seed: int) -> list[int]:
    pos = scores[scores["s"] > 0]
    cnt = pos.groupby("steamid").size()
    eligible = sorted(int(u) for u in cnt[cnt >= min_items].index)
    if len(eligible) <= cap:
        return eligible
    rng = np.random.default_rng(seed)
    return sorted(int(u) for u in rng.choice(eligible, size=cap, replace=False))


def fit_ease(scores, graph_users: list[int], pool: set[int], lam: float):
    """Memory-aware EASE fit (float32 dense / float64 inverse). Returns the
    Woodbury factors needed for exact scoring and B-row materialization."""
    d = scores[(scores["s"] > 0) & scores["appid"].isin(pool)]
    d = d[d["steamid"].isin(set(graph_users))]
    items = np.array(sorted(d["appid"].unique()))
    col = {int(a): j for j, a in enumerate(items)}
    urow = {u: i for i, u in enumerate(sorted(d["steamid"].unique()))}
    r = d["steamid"].map(urow).values
    c = d["appid"].map(col).values
    X = sparse.csr_matrix((d["s"].values.astype(np.float32), (r, c)),
                          shape=(len(urow), len(items)))
    t0 = time.time()
    Xd = X.toarray()  # float32, u x i
    log.info("fit: X %d users x %d items nnz=%d dense=%.2fGB",
             *Xd.shape, X.nnz, Xd.nbytes / 1e9)
    M = (Xd @ Xd.T).astype(np.float64)
    M[np.diag_indices_from(M)] += lam
    Minv = np.linalg.inv(M).astype(np.float32)
    del M
    V = Minv @ Xd  # float32, u x i
    del Minv
    diagP = (1.0 - np.einsum("ui,ui->i", Xd, V)) / lam
    diagP = np.maximum(diagP.astype(np.float64), 1e-9)
    del Xd
    log.info("fit done (%.0fs)", time.time() - t0)
    return X, V, diagP, items, col


def exact_scores(X, V, diagP, lam: float, x: np.ndarray) -> np.ndarray:
    """Fair full-EASE scoring (== ease_recheck.ease_reclist math)."""
    xXt = X @ x
    xP = (x - xXt @ V) / lam
    return x - xP / diagP


def build_B_topk(X, V, diagP, lam: float, n_items: int, topk: int,
                 chunk: int = 512) -> sparse.csr_matrix:
    """Exact B rows in chunks (E5 EasePositiveB math), truncated to top-K by
    |value| per row, sign preserved, zero diagonal."""
    t0 = time.time()
    Xc = X.tocsc()
    rows_i, rows_j, rows_v = [], [], []
    for s0 in range(0, n_items, chunk):
        cc = list(range(s0, min(s0 + chunk, n_items)))
        Xi = np.asarray(Xc[:, cc].todense(), dtype=np.float32)  # u x c
        P_rows = -(V.T @ Xi).T / lam                            # c x i
        for t, j in enumerate(cc):
            row = P_rows[t].astype(np.float64)
            row[j] += 1.0 / lam
            brow = -row / diagP
            brow[j] += 1.0
            brow[j] = 0.0
            k = min(topk, len(brow) - 1)
            idx = np.argpartition(np.abs(brow), -k)[-k:]
            vals = brow[idx]
            keep = vals != 0.0
            rows_i.append(np.full(int(keep.sum()), j, dtype=np.int32))
            rows_j.append(idx[keep].astype(np.int32))
            rows_v.append(vals[keep].astype(np.float32))
        if (s0 // chunk) % 10 == 0:
            log.info("B rows %d/%d (%.0fs)", s0 + len(cc), n_items, time.time() - t0)
    B = sparse.csr_matrix(
        (np.concatenate(rows_v), (np.concatenate(rows_i), np.concatenate(rows_j))),
        shape=(n_items, n_items))
    log.info("B_topk: nnz=%d (%.1f/row) %.0fMB (%.0fs)", B.nnz, B.nnz / n_items,
             (B.data.nbytes + B.indices.nbytes + B.indptr.nbytes) / 1e6,
             time.time() - t0)
    return B


def build_pt_ecdf(inter, items: np.ndarray, pool: set[int]) -> np.ndarray:
    """Per-item playtime quantile grid (21 points) over positive playtimes —
    lets serving interpolate a NEW user's pctl_game weight."""
    pos = inter[(inter["playtime_forever"] > 0) & inter["appid"].isin(pool)]
    grid = np.zeros((len(items), len(ECDF_QS)), dtype=np.float32)
    g = pos.groupby("appid")["playtime_forever"]
    qs = g.quantile(ECDF_QS).unstack()
    qs = qs.reindex(items)
    grid[:] = qs.fillna(0.0).values.astype(np.float32)
    return grid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts", type=Path, default=ART_DEFAULT)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--pref", default="pctl_game")
    ap.add_argument("--lam", type=float, default=100.0)
    ap.add_argument("--cap", type=int, default=12000)
    ap.add_argument("--min-items", type=int, default=5)
    ap.add_argument("--topk", type=int, default=512)
    ap.add_argument("--seed", type=int, default=20260720)
    args = ap.parse_args()

    inter, game_stats, user_stats, pool = load_snapshot(args.artifacts)
    scores = bs.compute(args.pref, inter, game_stats, user_stats)
    graph_users = select_graph_users(scores, args.cap, args.min_items, args.seed)
    log.info("graph users: %d (cap=%d, min_items=%d)", len(graph_users),
             args.cap, args.min_items)

    X, V, diagP, items, col = fit_ease(scores, graph_users, pool, args.lam)

    # exact Woodbury factors for p5_validate (gitignored outputs/, deletable)
    fac = args.artifacts / "ease_factors"
    fac.mkdir(parents=True, exist_ok=True)
    sparse.save_npz(fac / "X.npz", X)
    np.save(fac / "V.npy", V)
    np.save(fac / "diagP.npy", diagP)
    np.save(fac / "items.npy", items.astype(np.int64))

    B = build_B_topk(X, V, diagP, args.lam, len(items), args.topk)
    ecdf = build_pt_ecdf(inter, items, pool)
    avg_pt = (game_stats.set_index("appid")["pt_pos_mean"]
              .reindex(items).fillna(0.0).values.astype(np.float32))

    args.out.mkdir(parents=True, exist_ok=True)
    sparse.save_npz(args.out / "B_topk.npz", B)
    np.save(args.out / "items.npy", items.astype(np.int64))
    np.save(args.out / "avg_pt.npy", avg_pt)
    np.savez_compressed(args.out / "pt_ecdf.npz", grid=ecdf, qs=ECDF_QS)
    import subprocess
    try:
        git = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                      cwd=REPO_ROOT).decode().strip()
    except Exception:
        git = "unknown"
    meta = {"pref": args.pref, "lam": args.lam, "cap": args.cap,
            "min_items": args.min_items, "topk": args.topk, "seed": args.seed,
            "n_graph_users": len(graph_users), "n_items": int(len(items)),
            "B_nnz": int(B.nnz), "source_artifacts": str(args.artifacts),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "git_head": git}
    (args.out / "meta.json").write_text(json.dumps(meta, indent=2))
    # graph-user audit list (local only; serving/data/ease is gitignored)
    (args.out / "graph_users.json").write_text(json.dumps(graph_users))
    log.info("EASE artifact -> %s | %s", args.out, meta)
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
