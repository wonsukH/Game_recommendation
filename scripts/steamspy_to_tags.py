"""Adapter: SteamSpy CSV -> steam_games_tags.csv (legacy format).

The offline pipeline (`pipeline.game_rec.data.tag_vocab`,
`game_tag_matrix`) was written against the original 1031-game crawl's
`steam_games_tags.csv` schema: appid, game_title, tags (comma-sep
string), tag_count.

SteamSpy stores the same info as a JSON-encoded dict
`{tag_name: vote_count}` in `tags_json`. This script flattens that
into the legacy schema so the rest of the pipeline runs unchanged on
the expanded pool.

By default we keep tags with vote_count >= 5 (filters noise from
single-voter mis-tags). Use --min-votes to override.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("scripts.steamspy_to_tags")


def parse_tags_json(s: object, min_votes: int) -> tuple[str, int]:
    """Return (comma-separated tag string, count) after vote filtering."""
    if not isinstance(s, str) or len(s) < 3:
        return "", 0
    try:
        d = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return "", 0
    if not isinstance(d, dict):
        return "", 0
    # Filter then sort by vote count descending so the "main" tags come first
    kept = [(t, c) for t, c in d.items() if isinstance(c, (int, float)) and c >= min_votes]
    kept.sort(key=lambda x: -x[1])
    return ", ".join(t for t, _ in kept), len(kept)


def convert(input_csv: Path, output_csv: Path, min_votes: int) -> None:
    df = pd.read_csv(input_csv)
    if "tags_json" not in df.columns:
        log.error("input CSV missing 'tags_json' column (got %s)", list(df.columns))
        return

    log.info("loaded %d rows from %s (min_votes=%d)", len(df), input_csv, min_votes)

    parsed = df["tags_json"].apply(lambda s: parse_tags_json(s, min_votes))
    out = pd.DataFrame({
        "appid": df["appid"].astype(int),
        "game_title": df["name"],
        "tags": parsed.apply(lambda x: x[0]),
        "tag_count": parsed.apply(lambda x: x[1]),
    })

    before = len(out)
    out = out[out["tag_count"] > 0].reset_index(drop=True)
    log.info("kept %d games with >=1 tag (dropped %d empty)",
             len(out), before - len(out))

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_csv, index=False, encoding="utf-8-sig")
    log.info("wrote %s (%d rows)", output_csv, len(out))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path,
                        default=REPO_ROOT / "outputs" / "steamspy_games.csv")
    parser.add_argument("--output", type=Path,
                        default=REPO_ROOT / "outputs" / "steam_games_tags.csv")
    parser.add_argument("--min-votes", type=int, default=5,
                        help="Minimum SteamSpy tag vote count to keep (default 5)")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    convert(args.input, args.output, args.min_votes)
