"""Derive per-game popularity used by Novelty / Serendipity metrics.

Popularity has two possible sources, in order of preference:

1. **SteamSpy owners range** — `outputs/steamspy_games.csv`'s `owners`
   column is a string like "1,000,000 .. 2,000,000". We take the
   midpoint of the two numbers as a robust integer estimate. This
   covers our full game pool with consistent global statistics.

2. **Review count fallback** — for games not in SteamSpy (or when the
   SteamSpy CSV is missing entirely), use the number of rows that
   appid has in `outputs/user_all_reviews.csv` as a proxy.

The output is a numpy array aligned to `index_maps['row2appid']`:
`outputs/game_popularity.npy` (game count,). Sum of all entries is a
"total exposure" proxy used to compute `P(item) = popularity[i] / total`
in the Novelty metric (`-log2(P)`).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.game_rec.io import load_index_maps, save_stats
from pipeline.game_rec.log import get_logger

log = get_logger("game_rec.data.game_popularity")


_OWNERS_RANGE = re.compile(r"([\d,]+)\s*\.\.\s*([\d,]+)")


def parse_owners_range(s: str) -> float:
    """Convert '1,000,000 .. 2,000,000' to 1_500_000.0. NaN on bad input."""
    if not isinstance(s, str):
        return float("nan")
    m = _OWNERS_RANGE.search(s)
    if not m:
        return float("nan")
    low = float(m.group(1).replace(",", ""))
    high = float(m.group(2).replace(",", ""))
    return (low + high) / 2.0


def build_popularity_array(
    row2appid: dict,
    steamspy_df: pd.DataFrame | None,
    reviews_df: pd.DataFrame | None,
) -> tuple[np.ndarray, dict]:
    """Return (popularity_per_row, source_stats). At least one of the dfs
    must be non-None.
    """
    n = len(row2appid)
    pop = np.full(n, np.nan, dtype=np.float64)
    source = np.full(n, "missing", dtype=object)

    # Build appid -> owners midpoint map from SteamSpy
    spy_lookup: dict[int, float] = {}
    if steamspy_df is not None and "owners" in steamspy_df.columns:
        for _, row in steamspy_df.iterrows():
            try:
                appid = int(row["appid"])
            except (ValueError, TypeError):
                continue
            est = parse_owners_range(row["owners"])
            if est and not np.isnan(est):
                spy_lookup[appid] = est

    # Build appid -> review count from user_all_reviews
    rev_lookup: dict[int, int] = {}
    if reviews_df is not None and "appid" in reviews_df.columns:
        counts = reviews_df["appid"].value_counts().to_dict()
        rev_lookup = {int(k): int(v) for k, v in counts.items()}

    for row_idx, appid in row2appid.items():
        if appid in spy_lookup:
            pop[row_idx] = spy_lookup[appid]
            source[row_idx] = "steamspy_owners"
        elif appid in rev_lookup:
            pop[row_idx] = rev_lookup[appid]
            source[row_idx] = "review_count"

    # For rows still NaN, assign the global minimum (1.0) so log doesn't blow up
    n_missing = int(np.isnan(pop).sum())
    pop[np.isnan(pop)] = 1.0

    stats = {
        "n_games": n,
        "n_from_steamspy": int((source == "steamspy_owners").sum()),
        "n_from_reviews": int((source == "review_count").sum()),
        "n_missing_imputed": n_missing,
        "min": float(pop.min()),
        "max": float(pop.max()),
        "median": float(np.median(pop)),
        "mean": float(pop.mean()),
    }
    return pop, stats


def main(
    indexes_path: str,
    steamspy_csv: str,
    reviews_csv: str,
    output_path: str,
    stats_path: str,
):
    log.info("indexes=%s steamspy=%s reviews=%s", indexes_path, steamspy_csv, reviews_csv)
    index_maps = load_index_maps(indexes_path)
    row2appid = index_maps["row2appid"]

    steamspy_df = pd.read_csv(steamspy_csv) if Path(steamspy_csv).exists() else None
    if steamspy_df is None:
        log.warning("SteamSpy CSV missing — popularity will fall back to review counts")

    reviews_df = pd.read_csv(reviews_csv) if Path(reviews_csv).exists() else None
    if reviews_df is None and steamspy_df is None:
        log.error("neither SteamSpy nor reviews CSV available — cannot compute popularity")
        return

    pop, source_stats = build_popularity_array(row2appid, steamspy_df, reviews_df)

    log.info("popularity stats: %s", source_stats)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    np.save(output_path, pop)
    save_stats({"source": source_stats, "output_shape": list(pop.shape)}, stats_path)
    log.info("saved %s (shape=%s) + %s", output_path, pop.shape, stats_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--indexes", type=str, default="outputs/index_maps.json")
    parser.add_argument("--steamspy", type=str, default="outputs/steamspy_games.csv")
    parser.add_argument("--reviews", type=str, default="outputs/user_all_reviews.csv")
    parser.add_argument("--output", type=str, default="outputs/game_popularity.npy")
    parser.add_argument("--stats", type=str, default="outputs/game_popularity_stats.json")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    main(args.indexes, args.steamspy, args.reviews, args.output, args.stats)
