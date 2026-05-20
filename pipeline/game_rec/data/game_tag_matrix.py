"""Build the Game × Tag matrix (binary + optional weighted-by-votes).

Auto-detects the input format (same as tag_vocab.py):

1. **SteamSpy** (`tags_json` column): produces both X_binary AND
   X_weighted. The weighted matrix uses SteamSpy tag vote counts —
   useful for distinguishing "main tag" (hundreds of votes) from
   "side tag" (a dozen) in step5 Ridge regression.

2. **Legacy** (`tags` column): produces X_binary only.

Tags below `--min-votes` (SteamSpy only) and tags not in
`outputs/tag_vocab.json` are dropped — so this must run AFTER
tag_vocab.py.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, save_npz

from pipeline.game_rec.config import load_config
from pipeline.game_rec.io import load_tag_vocab
from pipeline.game_rec.log import get_logger
from pipeline.game_rec.data.tag_vocab import (
    detect_format, normalize_tag, apply_alias,
)

log = get_logger("game_rec.data.game_tag_matrix")


def iter_game_tag_weights_steamspy(df: pd.DataFrame, min_votes: int):
    """Yield (appid, name, tag, weight) tuples from SteamSpy tags_json."""
    for _, row in df.iterrows():
        try:
            appid = int(row["appid"])
        except (TypeError, ValueError):
            continue
        s = row.get("tags_json")
        if not isinstance(s, str) or len(s) < 3:
            continue
        try:
            d = json.loads(s)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(d, dict):
            continue
        for tag, count in d.items():
            if isinstance(count, (int, float)) and count >= min_votes:
                yield appid, row.get("name"), tag, float(count)


def iter_game_tag_weights_legacy(df: pd.DataFrame):
    """Yield (appid, game_title, tag, 1.0) tuples from comma-separated tags."""
    for _, row in df.iterrows():
        try:
            appid = int(row["appid"])
        except (TypeError, ValueError):
            continue
        tags = row.get("tags")
        if pd.isna(tags) or not tags:
            continue
        title = row.get("game_title")
        for tag in str(tags).split(","):
            tag = tag.strip()
            if tag:
                yield appid, title, tag, 1.0


def main(
    input_csv: str,
    matrix_path: str,
    index_path: str,
    weighted_path: str | None,
    min_votes: int,
    tag_vocab_path: str,
):
    log.info("loading %s (min_votes=%d)", input_csv, min_votes)
    df = pd.read_csv(input_csv)
    fmt = detect_format(df)
    log.info("detected format: %s (rows=%d)", fmt, len(df))

    # Load the canonical tag list — anything not in here gets dropped
    allowed_tags = set(load_tag_vocab(tag_vocab_path))
    log.info("tag_vocab has %d allowed tags", len(allowed_tags))

    # Iterate
    if fmt == "steamspy":
        iterator = iter_game_tag_weights_steamspy(df, min_votes=min_votes)
    else:
        iterator = iter_game_tag_weights_legacy(df)

    # Aggregate per-game tag bag
    game_titles: dict[int, str] = {}
    per_game: dict[int, list[tuple[str, float]]] = defaultdict(list)
    n_dropped_oov = 0
    n_entries = 0
    for appid, title, tag, weight in iterator:
        normalized = apply_alias(normalize_tag(tag))
        if normalized not in allowed_tags:
            n_dropped_oov += 1
            continue
        per_game[appid].append((normalized, weight))
        if appid not in game_titles and title is not None:
            game_titles[appid] = title
        n_entries += 1

    log.info("(game, tag) entries kept: %d (dropped %d not in tag_vocab)",
             n_entries, n_dropped_oov)

    if not per_game:
        log.error("no game-tag entries survived — check input CSV and tag_vocab.json")
        return

    # Build indexes
    games = sorted(per_game.keys())
    appid2row = {appid: i for i, appid in enumerate(games)}
    row2appid = {i: appid for i, appid in enumerate(games)}

    sorted_tags = sorted(allowed_tags)
    tag2idx = {tag: i for i, tag in enumerate(sorted_tags)}
    idx2tag = {i: tag for tag, i in tag2idx.items()}

    # Build sparse matrices
    rows_bin, cols_bin, data_bin = [], [], []
    rows_w, cols_w, data_w = [], [], []
    for appid, entries in per_game.items():
        g = appid2row[appid]
        # Aggregate duplicates (same tag listed twice somehow): take max weight
        merged: dict[int, float] = {}
        for tag, w in entries:
            c = tag2idx[tag]
            merged[c] = max(merged.get(c, 0.0), w)
        for c, w in merged.items():
            rows_bin.append(g); cols_bin.append(c); data_bin.append(1)
            rows_w.append(g); cols_w.append(c); data_w.append(w)

    shape = (len(games), len(sorted_tags))
    X_bin = csr_matrix((data_bin, (rows_bin, cols_bin)), shape=shape, dtype=np.int8)
    log.info("X_binary shape=%s, nnz=%d, density=%.4f",
             X_bin.shape, X_bin.nnz, X_bin.nnz / (shape[0] * shape[1]))

    Path(matrix_path).parent.mkdir(parents=True, exist_ok=True)
    save_npz(matrix_path, X_bin)
    log.info("saved binary matrix to %s", matrix_path)

    if weighted_path and fmt == "steamspy":
        X_w = csr_matrix((data_w, (rows_w, cols_w)), shape=shape, dtype=np.float32)
        save_npz(weighted_path, X_w)
        log.info("saved weighted matrix to %s (max=%.1f, mean=%.2f)",
                 weighted_path, X_w.max(), X_w.data.mean())

    # Index maps
    index_maps = {
        "appid2row": appid2row,
        "row2appid": row2appid,
        "tag2idx": tag2idx,
        "idx2tag": idx2tag,
        "matrix_shape": list(shape),
        "total_relations": int(X_bin.nnz),
        "input_format": fmt,
        "n_oov_tags_dropped": n_dropped_oov,
        "game_titles_sample": dict(list(game_titles.items())[:5]),
    }
    Path(index_path).parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_maps, f, ensure_ascii=False, indent=2)
    log.info("saved index_maps to %s", index_path)


def _parse_args() -> argparse.Namespace:
    cfg = load_config().get("data", {}).get("tag_vocab", {})
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=str,
        default=str(Path("outputs/steamspy_games.csv")),
        help="Input CSV (SteamSpy or legacy format, auto-detected)",
    )
    parser.add_argument(
        "--matrix", type=str,
        default=str(Path("outputs/X_game_tag_csr.npz")),
        help="Output binary CSR matrix path",
    )
    parser.add_argument(
        "--weighted", type=str,
        default=str(Path("outputs/X_game_tag_weighted.npz")),
        help="Output weighted CSR matrix path (SteamSpy only)",
    )
    parser.add_argument(
        "--indexes", type=str,
        default=str(Path("outputs/index_maps.json")),
    )
    parser.add_argument(
        "--tag-vocab", type=str,
        default=str(Path("outputs/tag_vocab.json")),
    )
    parser.add_argument(
        "--min-votes", type=int,
        default=cfg.get("min_votes", 5),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    main(
        args.input, args.matrix, args.indexes,
        args.weighted, args.min_votes, args.tag_vocab,
    )
