"""Masked-tag recovery — the cleanest test of whether SVD *generalizes*.

Phase 1 showed PPMI+SVD is worse than tag-cosine at EXACT similar-mode
retrieval. But SVD's claimed value is second-order generalization: placing a
game near a tag it does NOT carry but is semantically related to (the whole
point of the embedding for vibe mode). This experiment isolates exactly that.

Procedure
---------
1. Pick (game, tag) pairs where the game strongly carries the tag (high vote).
2. MASK those memberships (set X[game, tag] = 0) and rebuild PPMI + SVD on the
   masked matrix — so the model never sees that the game has that tag.
3. For each masked pair, rank the game among ALL games by SVD cosine to the
   removed tag's vector. If SVD ranks it well above chance, the embedding
   genuinely generalizes from the game's OTHER tags.

Why this is clean
-----------------
- Non-circular: the signal being recovered was deleted from the input.
- Raw tag-cosine is ~chance by construction (the masked entry is 0), so this
  measures a capability SVD *might* have that raw tags structurally cannot.
- No LLM, no API — pure numpy/scipy/sklearn, deterministic given seed.

Caveat: recovery-above-chance shows SVD has generalization CAPACITY; whether
that capacity yields better recommendations than tag-cosine in practice is a
separate question (vibe-mode judge, Phase 2 part 3).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.io import load_csr, load_index_maps, load_tag_vocab, save_stats  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("evaluation.masked_tag")


def ppmi_svd(X: csr_matrix, dim: int, seed: int) -> np.ndarray:
    """tag_vecs = TruncatedSVD(PPMI(X^T X)), matching the pipeline's recipe.

    Returns (n_tags, dim) tag embeddings (U*Sigma).
    """
    C = (X.T @ X).toarray().astype(np.float64)  # tag x tag co-occurrence (small: 447^2)
    total = C.sum()
    marg = C.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        expected = np.outer(marg, marg) / max(total, 1e-12)
        pmi = np.log(np.divide(C, expected, out=np.zeros_like(C), where=expected > 0) + 1e-12)
    ppmi = np.maximum(pmi, 0.0)
    svd = TruncatedSVD(n_components=dim, random_state=seed)
    return svd.fit_transform(ppmi)  # (n_tags, dim) = U*Sigma


def game_vectors(X: csr_matrix, tag_vecs: np.ndarray) -> np.ndarray:
    """Game vectors = row-normalized tag profile @ tag_vecs, then L2-normalized.

    A faithful-enough stand-in for the pipeline's softmax-weighted synthesis
    for the purpose of testing tag recovery.
    """
    Xn = normalize(X, norm="l1", axis=1)  # per-game tag weight distribution
    G = Xn @ tag_vecs
    return normalize(G, norm="l2", axis=1)


def pick_mask_pairs(X: csr_matrix, tag2idx: dict, n_tags_sample: int, per_tag: int, seed: int):
    """Pick (game_row, tag_col) pairs: strong memberships across diverse tags."""
    rng = np.random.default_rng(seed)
    n_tags = X.shape[1]
    # sample tags that have enough strong members
    col = X.tocsc()
    tag_cols = list(range(n_tags))
    rng.shuffle(tag_cols)
    pairs = []
    for t in tag_cols:
        start, end = col.indptr[t], col.indptr[t + 1]
        rows = col.indices[start:end]
        vals = col.data[start:end]
        if len(rows) < per_tag + 5:
            continue
        # pick the strongest members (high vote) so masking removes a real signal
        top = rows[np.argsort(vals)[::-1][:per_tag]]
        for g in top:
            pairs.append((int(g), int(t)))
        if len({t for _, t in pairs}) >= n_tags_sample:
            break
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--weighted-x", type=Path, default=REPO_ROOT / "outputs" / "X_game_tag_weighted.npz")
    ap.add_argument("--dim", type=int, default=128)
    ap.add_argument("--n-tags-sample", type=int, default=120)
    ap.add_argument("--per-tag", type=int, default=3)
    ap.add_argument("--ks", type=int, nargs="+", default=[10, 50, 100])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "experiments" / "masked_tag_report.md")
    args = ap.parse_args()

    maps = load_index_maps(args.data_dir / "index_maps.json")
    tag2idx = maps["tag2idx"]
    X = load_csr(args.weighted_x).astype(np.float64)
    n_games, n_tags = X.shape
    log.info("X shape %s", X.shape)

    pairs = pick_mask_pairs(X, tag2idx, args.n_tags_sample, args.per_tag, args.seed)
    log.info("masking %d (game,tag) pairs across %d tags", len(pairs), len({t for _, t in pairs}))

    # Mask
    Xm = X.tolil()
    for g, t in pairs:
        Xm[g, t] = 0.0
    Xm = Xm.tocsr()
    Xm.eliminate_zeros()

    # Rebuild PPMI+SVD on masked matrix; build masked game vectors
    tag_vecs = ppmi_svd(Xm, args.dim, args.seed)
    tag_vecs_n = normalize(tag_vecs, norm="l2", axis=1)
    G = game_vectors(Xm, tag_vecs)  # already L2-normalized

    # Raw masked baseline: column of the masked weighted matrix (votes), L2 over games
    Xm_csc = Xm.tocsc()

    ks = sorted(args.ks)
    svd_hits = {k: 0 for k in ks}
    raw_hits = {k: 0 for k in ks}
    svd_ranks, raw_ranks = [], []
    rng = np.random.default_rng(args.seed)
    for g, t in pairs:
        # SVD recovery: rank game g among all games by cosine to removed tag vec
        scores = G @ tag_vecs_n[t]
        rank = int((scores > scores[g]).sum())  # 0 = best
        svd_ranks.append(rank / n_games)
        for k in ks:
            if rank < k:
                svd_hits[k] += 1
        # Raw recovery: rank by masked column value (g is 0 there -> buried)
        colv = np.asarray(Xm_csc.getcol(t).todense()).ravel()
        # tie-break zeros randomly so raw == chance, not artificially 0/last
        jitter = rng.random(n_games) * 1e-9
        rs = colv + jitter
        rrank = int((rs > rs[g]).sum())
        raw_ranks.append(rrank / n_games)
        for k in ks:
            if rrank < k:
                raw_hits[k] += 1

    n = len(pairs)
    chance = {k: k / n_games for k in ks}
    svd_recall = {k: svd_hits[k] / n for k in ks}
    raw_recall = {k: raw_hits[k] / n for k in ks}

    L = [
        "# Phase 2a — Masked-tag recovery (does SVD generalize?)",
        "",
        f"Masked **{n}** strong (game,tag) memberships across **{len({t for _,t in pairs})}** tags, "
        f"rebuilt PPMI+SVD (dim={args.dim}) on the masked matrix, then tried to recover the removed "
        f"game from the removed tag's vector. n_games={n_games}.",
        "",
        "| k | SVD recall@k | raw-masked recall@k | chance |",
        "|---|---|---|---|",
    ]
    for k in ks:
        L.append(f"| {k} | {svd_recall[k]:.3f} | {raw_recall[k]:.3f} | {chance[k]:.4f} |")
    L += [
        "",
        f"- **SVD median rank percentile**: {np.median(svd_ranks):.3f} (0 = top, 0.5 = chance)",
        f"- **raw-masked median rank percentile**: {np.median(raw_ranks):.3f}",
        "",
        "## Reading",
        "",
        f"- SVD recall@10 = {svd_recall[ks[0]]:.3f} vs chance {chance[ks[0]]:.4f}: "
        + ("SVD recovers removed memberships **far above chance** → genuine second-order generalization capacity."
           if svd_recall[ks[0]] > 5 * chance[ks[0]]
           else "SVD recovery is near chance → little generalization capacity."),
        "- raw-masked ≈ chance by construction (the masked entry is 0): tag-cosine structurally CANNOT recover "
        "removed memberships. This is the one thing SVD can do that raw tags cannot.",
        "",
        "## Honest caveat",
        "",
        "Recovery-above-chance shows generalization CAPACITY, not that SVD recommends better than tag-cosine. "
        "Phase 1 showed SVD is worse for exact similar-mode retrieval; whether its generalization is a NET win "
        "for vibe recommendations is decided by the vibe-mode judge (Phase 2 part 3).",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(L), encoding="utf-8")
    save_stats({
        "n_pairs": n, "n_games": n_games,
        "svd_recall": svd_recall, "raw_recall": raw_recall, "chance": chance,
        "svd_median_rank_pct": float(np.median(svd_ranks)),
        "raw_median_rank_pct": float(np.median(raw_ranks)),
        "seed": args.seed, "dim": args.dim,
    }, args.out.with_suffix(".json"))
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
