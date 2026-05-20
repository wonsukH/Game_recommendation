"""Build the tag vocabulary used by all downstream embedding models.

Accepts two input shapes (auto-detected from CSV columns):

1. **SteamSpy** (`tags_json` column) — preferred for the expanded pool.
   Each row's `tags_json` is a JSON dict `{tag_name: vote_count}`. We
   filter by `--min-votes` (default from config) to drop low-signal
   single-voter mis-tags.

2. **Legacy** (`tags` column, comma-separated string) — the original
   1031-game crawl format. Kept for back-compat. No vote info, all
   tags pass through.

Output: outputs/tag_vocab.json with the sorted unique list of
normalized tags plus the alias map.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

from pipeline.game_rec.config import load_config
from pipeline.game_rec.log import get_logger

log = get_logger("game_rec.data.tag_vocab")


# ----- Normalization ----------------------------------------------------------

def normalize_tag(tag: str) -> str:
    """Lowercase, NFKC, collapse whitespace, replace `/` and spaces with `-`.

    Also collapses consecutive hyphens so 'RPG / Action' -> 'rpg-action'
    rather than 'rpg---action' (which the original team baseline would
    have produced if such tags appeared).
    """
    tag = tag.lower()
    tag = unicodedata.normalize("NFKC", tag)
    tag = re.sub(r"\s+", " ", tag).strip()
    tag = tag.replace("/", "-").replace(" ", "-")
    tag = re.sub(r"-+", "-", tag).strip("-")
    return tag


ALIAS_MAP = {
    "rogue like": "roguelike",
    "rogue-like": "roguelike",
    "single player": "single-player",
    "multi player": "multiplayer",
}


def apply_alias(tag: str) -> str:
    return ALIAS_MAP.get(tag, tag)


# ----- Input format detection -------------------------------------------------

def detect_format(df: pd.DataFrame) -> str:
    if "tags_json" in df.columns:
        return "steamspy"
    if "tags" in df.columns:
        return "legacy"
    raise ValueError(
        f"input CSV has neither 'tags_json' nor 'tags' column; got {list(df.columns)}"
    )


def extract_tags_steamspy(df: pd.DataFrame, min_votes: int) -> list[str]:
    """Pull all (game, tag) entries from SteamSpy tags_json with vote filter."""
    out: list[str] = []
    parse_errors = 0
    for s in df["tags_json"]:
        if not isinstance(s, str) or len(s) < 3:
            continue
        try:
            d = json.loads(s)
        except (json.JSONDecodeError, TypeError):
            parse_errors += 1
            continue
        if not isinstance(d, dict):
            continue
        for tag, count in d.items():
            if isinstance(count, (int, float)) and count >= min_votes:
                out.append(tag)
    if parse_errors:
        log.warning("%d rows had unparseable tags_json (skipped)", parse_errors)
    return out


def extract_tags_legacy(df: pd.DataFrame) -> list[str]:
    """Pull all (game, tag) entries from legacy comma-separated 'tags' column."""
    out: list[str] = []
    for tags in df["tags"]:
        if pd.isna(tags):
            continue
        for tag in str(tags).split(","):
            tag = tag.strip()
            if tag:
                out.append(tag)
    return out


# ----- Main -------------------------------------------------------------------

def main(input_csv: str, out_json: str, min_votes: int):
    log.info("loading %s (min_votes=%d)", input_csv, min_votes)
    df = pd.read_csv(input_csv)
    fmt = detect_format(df)
    log.info("detected format: %s (rows=%d)", fmt, len(df))

    if fmt == "steamspy":
        raw_tags = extract_tags_steamspy(df, min_votes=min_votes)
    else:
        raw_tags = extract_tags_legacy(df)

    normalized = [apply_alias(normalize_tag(t)) for t in raw_tags]
    counter = Counter(normalized)
    unique_tags = sorted(counter.keys())

    log.info("total (game, tag) entries: %d", len(normalized))
    log.info("unique tags after normalize+alias: %d", len(unique_tags))
    log.info("top 10 tags by frequency: %s", counter.most_common(10))

    vocab = {
        "tags": unique_tags,
        "alias_map": ALIAS_MAP,
        "total_tags": len(normalized),
        "unique_tags": len(unique_tags),
        "input_format": fmt,
        "min_votes": min_votes if fmt == "steamspy" else None,
    }

    out_path = Path(out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=2)
    log.info("saved %s (%d unique tags)", out_json, len(unique_tags))


def _parse_args() -> argparse.Namespace:
    cfg = load_config().get("data", {}).get("tag_vocab", {})
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=str,
        default=str(Path("outputs/steamspy_games.csv")),
        help="Input CSV (SteamSpy: tags_json col; or legacy: tags col)",
    )
    parser.add_argument(
        "--output", type=str,
        default=str(Path("outputs/tag_vocab.json")),
    )
    parser.add_argument(
        "--min-votes", type=int,
        default=cfg.get("min_votes", 5),
        help="Minimum SteamSpy vote count to keep a tag (default 5; ignored for legacy)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    main(args.input, args.output, args.min_votes)
