"""Item2Vec: game embeddings from co-play behavior.

For each user, take the set of games they marked favorite (s_round10_rec
above a threshold) as a "sentence", then train SkipGram (Mikolov 2013)
over these sentences. Result: a game vector whose neighbors are games
that frequently appear in the same users' favorites.

This is a different signal from PPMI+SVD over the game-tag matrix:
- PPMI captures "games that share tags".
- Item2Vec captures "games that share fans".

Used as one of the two ensemble inputs in
`pipeline.game_rec.models.game_vectors` (along with PPMI vectors).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from gensim.models import Word2Vec

from pipeline.game_rec.io import save_stats, load_index_maps
from pipeline.game_rec.config import load_config
from pipeline.game_rec.log import get_logger

log = get_logger("game_rec.models.item2vec")


def build_sentences(
    scores_df: pd.DataFrame,
    score_threshold: int,
    allowed_appids: set | None = None,
) -> list[list[str]]:
    """Per-user list of favorite appids (as strings, since gensim wants tokens)."""
    df = scores_df[scores_df["s_round10_rec"] >= score_threshold]
    if allowed_appids is not None:
        df = df[df["appid"].isin(allowed_appids)]
    sentences = (
        df.groupby("steamid")["appid"]
        .apply(lambda s: [str(int(x)) for x in s])
        .tolist()
    )
    # Drop singletons — SkipGram needs at least 2 tokens to learn anything
    sentences = [s for s in sentences if len(s) >= 2]
    return sentences


def train(
    sentences: list[list[str]],
    vector_size: int,
    window: int,
    min_count: int,
    epochs: int,
    sg: int = 1,
    seed: int = 42,
) -> Word2Vec:
    log.info("training Item2Vec on %d sentences (vector_size=%d, window=%d, sg=%d, epochs=%d)",
             len(sentences), vector_size, window, sg, epochs)
    model = Word2Vec(
        sentences=sentences,
        vector_size=vector_size,
        window=window,
        min_count=min_count,
        sg=sg,
        epochs=epochs,
        workers=4,
        seed=seed,
    )
    log.info("Item2Vec vocab size: %d", len(model.wv))
    return model


def extract_vectors(
    model: Word2Vec,
    index_maps: dict,
) -> tuple[np.ndarray, dict]:
    """Build a (n_games, vector_size) array aligned to index_maps['row2appid'].

    Games not in Item2Vec vocab (cold-start: never appeared in any user's
    favorite set) get a zero vector. The stats dict records how many.
    """
    row2appid = index_maps["row2appid"]
    n_games = len(row2appid)
    dim = model.vector_size
    out = np.zeros((n_games, dim), dtype=np.float32)
    missing = []
    for row_idx, appid in row2appid.items():
        key = str(appid)
        if key in model.wv:
            out[row_idx] = model.wv[key]
        else:
            missing.append(int(appid))
    return out, {
        "n_games": n_games,
        "n_in_vocab": n_games - len(missing),
        "n_zero": len(missing),
        "vector_size": dim,
    }


def main(
    scores_csv: str,
    index_maps_path: str,
    output_path: str,
    stats_path: str,
    cfg: dict,
):
    log.info("loading scores from %s", scores_csv)
    scores_df = pd.read_csv(scores_csv)

    log.info("loading index_maps from %s (for row alignment)", index_maps_path)
    index_maps = load_index_maps(index_maps_path)
    allowed_appids = set(index_maps["appid2row"].keys())

    sentences = build_sentences(
        scores_df,
        score_threshold=cfg["score_threshold"],
        allowed_appids=allowed_appids,
    )
    log.info("built %d sentences after filtering (threshold=%d, allowed=%d games)",
             len(sentences), cfg["score_threshold"], len(allowed_appids))

    if not sentences:
        log.error("no sentences to train on — check score_threshold and data")
        return

    model = train(
        sentences,
        vector_size=cfg["vector_size"],
        window=cfg["window"],
        min_count=cfg["min_count"],
        epochs=cfg["epochs"],
        sg=cfg["sg"],
    )

    vectors, vstats = extract_vectors(model, index_maps)
    log.info("extracted vectors shape=%s (%d in vocab, %d zero)",
             vectors.shape, vstats["n_in_vocab"], vstats["n_zero"])

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    np.save(output_path, vectors)

    save_stats({
        "vector_stats": vstats,
        "training": {
            "n_sentences": len(sentences),
            "avg_sentence_length": float(np.mean([len(s) for s in sentences])),
            "vocab_size": len(model.wv),
        },
        "parameters": dict(cfg),
    }, stats_path)
    log.info("saved %s (shape=%s) + %s", output_path, vectors.shape, stats_path)


def _parse_args() -> argparse.Namespace:
    cfg = load_config()["models"]["item2vec"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=str,
                        default="outputs/user_game_scores.csv")
    parser.add_argument("--indexes", type=str,
                        default="outputs/index_maps.json")
    parser.add_argument("--output", type=str,
                        default="outputs/game_vecs_user_signal.npy")
    parser.add_argument("--stats", type=str,
                        default="outputs/game_vecs_user_signal_stats.json")
    parser.add_argument("--vector-size", type=int, default=cfg["vector_size"])
    parser.add_argument("--window", type=int, default=cfg["window"])
    parser.add_argument("--min-count", type=int, default=cfg["min_count"])
    parser.add_argument("--epochs", type=int, default=cfg["epochs"])
    parser.add_argument("--sg", type=int, default=cfg["sg"])
    parser.add_argument("--score-threshold", type=int, default=cfg["score_threshold"])
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    cfg_override = {
        "vector_size": args.vector_size,
        "window": args.window,
        "min_count": args.min_count,
        "epochs": args.epochs,
        "sg": args.sg,
        "score_threshold": args.score_threshold,
    }
    main(args.scores, args.indexes, args.output, args.stats, cfg_override)
