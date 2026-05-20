"""Per-game weight derivation from user-game scores.

Three weighting modes:
- **mean** (original baseline): raw average of s_round10_rec per game.
  Games with very few raters get noisy estimates that distort the
  downstream PPMI weighting.
- **bayesian** (recommended): shrinkage toward global mean.
    w_g = (n_g * mean_g + k * global_mean) / (n_g + k)
  k = prior_strength. Small-sample games get pulled toward the global
  mean, so their noisy means don't dominate.
- **variance**: inverse-variance weighting.
    w_g = (n_g / var_g) -normalized
  Penalizes high-variance games (disagreement among raters) regardless
  of their mean.

All three modes are then min-max normalized and gamma-corrected, just
like the original game_weights script.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from pipeline.game_rec.io import save_stats
from pipeline.game_rec.config import load_config
from pipeline.game_rec.log import get_logger

log = get_logger("game_rec.data.game_weights")


def aggregate_scores(
    df: pd.DataFrame,
    score_col: str,
    weighting: str = "bayesian",
    prior_strength: float = 10.0,
) -> pd.DataFrame:
    """Aggregate per-(user, game) scores into per-game weights.

    Returns a DataFrame with columns: appid, n_raters, raw_mean,
    raw_var, weight (pre-normalization).
    """
    grouped = df.groupby("appid")[score_col].agg(["count", "mean", "var"]).reset_index()
    grouped = grouped.rename(columns={"count": "n_raters", "mean": "raw_mean", "var": "raw_var"})
    grouped["raw_var"] = grouped["raw_var"].fillna(0.0)  # 1-sample variance is NaN

    global_mean = float(df[score_col].mean())
    global_var = float(df[score_col].var())

    if weighting == "mean":
        grouped["weight"] = grouped["raw_mean"]
    elif weighting == "bayesian":
        n = grouped["n_raters"]
        grouped["weight"] = (n * grouped["raw_mean"] + prior_strength * global_mean) / (n + prior_strength)
    elif weighting == "variance":
        # Inverse-variance weighted mean toward global_mean.
        # var=0 (single rater) is replaced with global_var for numerical sanity.
        var = grouped["raw_var"].replace(0.0, global_var)
        precision = grouped["n_raters"] / var
        global_precision = 1.0 / global_var if global_var > 0 else 1.0
        grouped["weight"] = (
            precision * grouped["raw_mean"] + global_precision * global_mean
        ) / (precision + global_precision)
    else:
        raise ValueError(f"unknown weighting mode: {weighting}")

    log.info("weighting=%s, n_games=%d, global_mean=%.4f, global_var=%.4f",
             weighting, len(grouped), global_mean, global_var)
    return grouped.sort_values("appid").reset_index(drop=True)


def normalize_scores(scores: np.ndarray, gamma: float = 0.5) -> np.ndarray:
    """Min-max to [0,1] then gamma correction. Lifts low values when gamma<1."""
    scaler = MinMaxScaler()
    scores_norm = scaler.fit_transform(scores.reshape(-1, 1)).flatten()
    return np.power(scores_norm, gamma)


def main(
    input_csv: str,
    score_col: str,
    gamma: float,
    weighting: str,
    prior_strength: float,
    output_path: str,
    stats_path: str,
):
    log.info("loading %s (score_col=%s, weighting=%s, gamma=%s)",
             input_csv, score_col, weighting, gamma)

    df = pd.read_csv(input_csv)
    if score_col not in df.columns:
        available = [c for c in df.columns if "score" in c.lower() or "s_" in c]
        log.error("score_col '%s' not in CSV. available score-like cols: %s",
                  score_col, available)
        return

    agg = aggregate_scores(df, score_col, weighting=weighting, prior_strength=prior_strength)

    raw_array = agg["weight"].values
    normalized_scores = normalize_scores(raw_array, gamma)

    log.info("raw weight stats: min=%.4f max=%.4f mean=%.4f std=%.4f",
             raw_array.min(), raw_array.max(), raw_array.mean(), raw_array.std())
    log.info("normalized weight stats: min=%.4f max=%.4f mean=%.4f std=%.4f",
             normalized_scores.min(), normalized_scores.max(),
             normalized_scores.mean(), normalized_scores.std())

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    np.save(output_path, normalized_scores)

    stats = {
        "raw_stats": {
            "min": float(raw_array.min()),
            "max": float(raw_array.max()),
            "mean": float(raw_array.mean()),
            "std": float(raw_array.std()),
        },
        "normalized_stats": {
            "min": float(normalized_scores.min()),
            "max": float(normalized_scores.max()),
            "mean": float(normalized_scores.mean()),
            "std": float(normalized_scores.std()),
        },
        "parameters": {
            "score_column": score_col,
            "gamma": gamma,
            "weighting": weighting,
            "prior_strength": prior_strength,
            "num_games": int(len(agg)),
        },
        "rater_counts": {
            "min": int(agg["n_raters"].min()),
            "max": int(agg["n_raters"].max()),
            "median": float(agg["n_raters"].median()),
            "mean": float(agg["n_raters"].mean()),
        },
        "game_ids": agg["appid"].tolist(),
    }
    save_stats(stats, stats_path)
    log.info("saved %s (shape=%s) + %s", output_path, normalized_scores.shape, stats_path)


def _parse_args() -> argparse.Namespace:
    cfg = load_config()["data"]["game_weights"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=str,
        default=str(Path("outputs/user_game_scores.csv")),
    )
    parser.add_argument(
        "--score-col", type=str,
        default=cfg["score_col"],
        help=f"Score column (default from config: {cfg['score_col']})",
    )
    parser.add_argument(
        "--gamma", type=float,
        default=cfg["gamma"],
        help=f"Gamma correction (default from config: {cfg['gamma']})",
    )
    parser.add_argument(
        "--weighting", type=str,
        default=cfg.get("weighting", "bayesian"),
        choices=["mean", "bayesian", "variance"],
        help=f"Aggregation mode (default from config: {cfg.get('weighting', 'bayesian')})",
    )
    parser.add_argument(
        "--prior-strength", type=float,
        default=cfg.get("prior_strength", 10.0),
        help=f"Bayesian shrinkage k (default from config: {cfg.get('prior_strength', 10.0)})",
    )
    parser.add_argument(
        "--output", type=str,
        default=str(Path("outputs/game_weight.npy")),
    )
    parser.add_argument(
        "--stats", type=str,
        default=str(Path("outputs/game_weight_stats.json")),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    main(
        args.input, args.score_col, args.gamma,
        args.weighting, args.prior_strength,
        args.output, args.stats,
    )
