"""Project tag embeddings to 2D + cluster them.

Outputs:
- outputs/tag_2d.npy           (n_tags, 2)  UMAP-projected coordinates
- outputs/tag_clusters.npy     (n_tags,)    KMeans cluster id per tag
- outputs/tag_neighbors.json   {tag: [top-k neighbors by cosine]}

These feed serving/pages/2_tag_map.py (M6.2) which shows the tag map
as an interactive scatter.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity

from pipeline.game_rec.io import load_vectors, load_tag_vocab, save_stats
from pipeline.game_rec.log import get_logger

log = get_logger("game_rec.index.tag_projection")


def project_2d(tag_vecs: np.ndarray, n_neighbors: int = 15, min_dist: float = 0.1, seed: int = 42) -> np.ndarray:
    """UMAP -> 2D. Falls back to PCA if umap-learn isn't installed."""
    try:
        from umap import UMAP
        log.info("UMAP projecting (n_neighbors=%d, min_dist=%.2f)", n_neighbors, min_dist)
        reducer = UMAP(n_components=2, n_neighbors=n_neighbors, min_dist=min_dist, random_state=seed)
        return reducer.fit_transform(tag_vecs).astype(np.float32)
    except ImportError:
        log.warning("umap-learn not installed; falling back to PCA")
        from sklearn.decomposition import PCA
        return PCA(n_components=2, random_state=seed).fit_transform(tag_vecs).astype(np.float32)


def cluster_tags(tag_vecs: np.ndarray, n_clusters: int = 12, seed: int = 42) -> np.ndarray:
    log.info("KMeans clustering (k=%d)", n_clusters)
    km = KMeans(n_clusters=n_clusters, random_state=seed, n_init=10)
    return km.fit_predict(tag_vecs).astype(np.int32)


def build_neighbor_map(tag_vecs: np.ndarray, tag_names: list[str], top_k: int = 10) -> dict:
    log.info("computing top-%d neighbors per tag", top_k)
    sim = cosine_similarity(tag_vecs)
    np.fill_diagonal(sim, -1.0)  # exclude self
    out: dict[str, list[tuple[str, float]]] = {}
    for i, name in enumerate(tag_names):
        top = np.argsort(-sim[i])[:top_k]
        out[name] = [(tag_names[int(j)], float(sim[i, int(j)])) for j in top]
    return out


def main(
    tag_vecs_path: str,
    tag_vocab_path: str,
    out_2d: str,
    out_clusters: str,
    out_neighbors: str,
    n_clusters: int,
    n_neighbors: int,
    min_dist: float,
    top_k: int,
):
    tag_vecs = load_vectors(tag_vecs_path)
    tag_names = load_tag_vocab(tag_vocab_path)
    log.info("loaded %d tags from %s", len(tag_names), tag_vocab_path)

    coords = project_2d(tag_vecs, n_neighbors=n_neighbors, min_dist=min_dist)
    clusters = cluster_tags(tag_vecs, n_clusters=n_clusters)
    neighbors = build_neighbor_map(tag_vecs, tag_names, top_k=top_k)

    Path(out_2d).parent.mkdir(parents=True, exist_ok=True)
    np.save(out_2d, coords)
    np.save(out_clusters, clusters)
    with open(out_neighbors, "w", encoding="utf-8") as f:
        json.dump(neighbors, f, ensure_ascii=False, indent=2)
    log.info("saved %s (%s), %s (%s), %s",
             out_2d, coords.shape, out_clusters, clusters.shape, out_neighbors)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag-vecs", type=str, default="outputs/tag_vecs.npy")
    parser.add_argument("--tag-vocab", type=str, default="outputs/tag_vocab.json")
    parser.add_argument("--out-2d", type=str, default="outputs/tag_2d.npy")
    parser.add_argument("--out-clusters", type=str, default="outputs/tag_clusters.npy")
    parser.add_argument("--out-neighbors", type=str, default="outputs/tag_neighbors.json")
    parser.add_argument("--n-clusters", type=int, default=12)
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--min-dist", type=float, default=0.1)
    parser.add_argument("--top-k", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    main(
        args.tag_vecs, args.tag_vocab,
        args.out_2d, args.out_clusters, args.out_neighbors,
        args.n_clusters, args.n_neighbors, args.min_dist, args.top_k,
    )
