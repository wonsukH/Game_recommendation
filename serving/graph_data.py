"""Shared graph data loader for tag force-graph pages (2D + 3D).

Reads the same artifacts the UMAP scatter page uses (tag_neighbors,
tag_clusters, X_game_tag_csr, game_popularity, steam_games_tags) and
returns a renderer-agnostic dict of nodes + edges so each page
(streamlit-agraph for 2D, 3d-force-graph for 3D) can format it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.sparse import load_npz

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "serving" / "data"


# 12-color qualitative palette (cluster id -> hex)
CLUSTER_COLORS = [
    "#E53935", "#1E88E5", "#43A047", "#FB8C00", "#8E24AA", "#00ACC1",
    "#FDD835", "#6D4C41", "#3949AB", "#D81B60", "#7CB342", "#5E35B1",
]


def cluster_color(cluster_id: int) -> str:
    return CLUSTER_COLORS[int(cluster_id) % len(CLUSTER_COLORS)]


def _load_top_games(k: int = 5) -> dict[str, list[str]]:
    x_path = DATA_DIR / "X_game_tag_csr.npz"
    pop_path = DATA_DIR / "game_popularity.npy"
    imap_path = DATA_DIR / "index_maps.json"
    games_path = DATA_DIR / "steam_games_tags.csv"
    if not all(p.exists() for p in [x_path, pop_path, imap_path, games_path]):
        return {}

    X = load_npz(x_path).tocsc()
    pop = np.load(pop_path).astype(float)
    imap = json.loads(imap_path.read_text(encoding="utf-8"))
    games = pd.read_csv(games_path)

    row2appid = imap.get("row2appid", {})
    if isinstance(row2appid, dict):
        ordered = [v for _, v in sorted(
            ((int(k_), v) for k_, v in row2appid.items()), key=lambda x: x[0]
        )]
    else:
        ordered = list(row2appid)

    appid_to_title = dict(zip(games["appid"].astype(int), games["game_title"]))
    tag2idx = imap.get("tag2idx", {})

    out: dict[str, list[str]] = {}
    for tag_name, col_idx in tag2idx.items():
        col_idx = int(col_idx)
        if col_idx >= X.shape[1]:
            continue
        rows = X[:, col_idx].indices
        if len(rows) == 0:
            out[tag_name] = []
            continue
        rows = rows[rows < len(pop)]
        if len(rows) == 0:
            out[tag_name] = []
            continue
        order = np.argsort(pop[rows])[::-1][:k]
        titles: list[str] = []
        for r in rows[order]:
            if r < len(ordered):
                titles.append(appid_to_title.get(int(ordered[r]), f"appid={ordered[r]}"))
        out[tag_name] = titles
    return out


def _game_counts_per_tag() -> dict[str, int]:
    x_path = DATA_DIR / "X_game_tag_csr.npz"
    imap_path = DATA_DIR / "index_maps.json"
    if not (x_path.exists() and imap_path.exists()):
        return {}
    X = load_npz(x_path).tocsc()
    imap = json.loads(imap_path.read_text(encoding="utf-8"))
    tag2idx = imap.get("tag2idx", {})
    out: dict[str, int] = {}
    for tag_name, col_idx in tag2idx.items():
        col_idx = int(col_idx)
        if col_idx < X.shape[1]:
            out[tag_name] = int(X[:, col_idx].nnz)
    return out


def _cluster_names(
    tag_names: list[str],
    clusters: np.ndarray,
    counts: dict[str, int],
) -> dict[int, str]:
    """For each cluster, generate a short label from its top 2 tags by game count.

    Returns e.g. {0: "Action · RPG", 1: "Indie · Casual", ...}.
    """
    by_cluster: dict[int, list[tuple[str, int]]] = {}
    for tag, cid in zip(tag_names, clusters):
        cid_int = int(cid)
        by_cluster.setdefault(cid_int, []).append((tag, counts.get(tag, 0)))
    out: dict[int, str] = {}
    for cid, items in by_cluster.items():
        items.sort(key=lambda x: -x[1])
        top = [t for t, _ in items[:2]]
        out[cid] = " · ".join(top) if top else f"Cluster {cid}"
    return out


def load_graph(top_k_games: int = 5, neighbor_k: int = 5) -> dict[str, Any]:
    """Return renderer-agnostic graph data.

    Returns
    -------
    {
        "nodes": [
            {"id": tag, "cluster": int, "cluster_name": str, "color": hex,
             "size": int, "top_games": list[str], "n_games": int}, ...
        ],
        "edges": [{"source": tag1, "target": tag2, "weight": float}, ...]
    }
    """
    vocab_path = DATA_DIR / "tag_vocab.json"
    clusters_path = DATA_DIR / "tag_clusters.npy"
    neighbors_path = DATA_DIR / "tag_neighbors.json"

    vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
    tag_names = vocab.get("tags") if isinstance(vocab, dict) else vocab
    clusters = (
        np.load(clusters_path)
        if clusters_path.exists()
        else np.zeros(len(tag_names), dtype=int)
    )
    neighbors = (
        json.loads(neighbors_path.read_text(encoding="utf-8"))
        if neighbors_path.exists() else {}
    )

    top_games = _load_top_games(k=top_k_games)
    counts = _game_counts_per_tag()
    cnames = _cluster_names(tag_names, clusters, counts)

    # Normalize sizes for visualization
    raw_counts = np.array([counts.get(t, 1) for t in tag_names], dtype=float)
    if raw_counts.max() > 0:
        norm = np.log1p(raw_counts) / np.log1p(raw_counts.max())
    else:
        norm = np.zeros_like(raw_counts)

    nodes = []
    for i, tag in enumerate(tag_names):
        c = int(clusters[i]) if i < len(clusters) else 0
        nodes.append({
            "id": tag,
            "cluster": c,
            "cluster_name": cnames.get(c, f"Cluster {c}"),
            "color": cluster_color(c),
            "size": float(norm[i]),
            "n_games": int(counts.get(tag, 0)),
            "top_games": top_games.get(tag, []),
        })

    tag_set = set(tag_names)
    edges = []
    seen: set[tuple[str, str]] = set()
    for tag, nbrs in neighbors.items():
        if tag not in tag_set:
            continue
        for nb in nbrs[:neighbor_k]:
            # neighbors entries can be [name, score] or {name, similarity}
            if isinstance(nb, (list, tuple)):
                nb_name, nb_score = nb[0], float(nb[1])
            elif isinstance(nb, dict):
                nb_name = nb.get("tag") or nb.get("name")
                nb_score = float(nb.get("cosine_similarity") or nb.get("score") or 0.0)
            else:
                continue
            if nb_name not in tag_set or nb_name == tag:
                continue
            key = tuple(sorted([tag, nb_name]))
            if key in seen:
                continue
            seen.add(key)
            edges.append({"source": tag, "target": nb_name, "weight": nb_score})

    return {"nodes": nodes, "edges": edges}
