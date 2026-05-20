"""Compute cosine similarity between tags from the user-tag score matrix.

This is a collaborative-filtering-style tag similarity, separate from
the PPMI+SVD tag embeddings in game_rec.models.tag_embeddings. Kept as
a secondary signal / sanity check.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from pipeline.game_rec.log import get_logger

log = get_logger("game_rec.index.tag_similarity")

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUTS = REPO_ROOT / "outputs"


def compute_tag_similarity(scores_path: Path, tags_path: Path, output_path: Path) -> None:
    df_scores = pd.read_csv(scores_path)
    df_tags = pd.read_csv(tags_path)

    # explode tags
    tags_series = df_tags["tags"].fillna("").astype(str).str.replace(";", ",")
    df_tags = df_tags.assign(tag=tags_series.str.split(",")).explode("tag")
    df_tags["tag"] = df_tags["tag"].astype(str).str.strip()
    df_tags = df_tags[df_tags["tag"] != ""]

    value_col = (
        "s_round10_rec" if "s_round10_rec" in df_scores.columns
        else "game_score" if "game_score" in df_scores.columns
        else None
    )
    if value_col is None:
        raise ValueError("점수 컬럼을 찾을 수 없습니다. 's_round10_rec' 또는 'game_score'가 필요합니다.")

    df = df_scores.merge(df_tags[["appid", "tag"]], on="appid", how="inner")
    user_tag_matrix = df.pivot_table(
        index="steamid", columns="tag", values=value_col, aggfunc="sum", fill_value=0,
    )

    log.info("user-tag matrix shape: %s", user_tag_matrix.shape)

    similarity_matrix = cosine_similarity(user_tag_matrix.T)
    similarity_df = pd.DataFrame(
        similarity_matrix,
        index=user_tag_matrix.columns,
        columns=user_tag_matrix.columns,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    similarity_df.to_csv(output_path)
    log.info("saved tag similarity matrix to %s", output_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute cosine similarity between game tags from user scores",
    )
    parser.add_argument(
        "--scores", type=Path,
        default=DEFAULT_OUTPUTS / "user_game_scores.csv",
        help="Path to user_game_scores CSV",
    )
    parser.add_argument(
        "--tags", type=Path,
        default=DEFAULT_OUTPUTS / "steam_games_tags.csv",
        help="Path to steam_games_tags CSV",
    )
    parser.add_argument(
        "-o", "--output", type=Path,
        default=DEFAULT_OUTPUTS / "tag_similarity_cosine.csv",
        help="Output path for similarity CSV",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    compute_tag_similarity(args.scores, args.tags, args.output)


if __name__ == "__main__":
    main()
