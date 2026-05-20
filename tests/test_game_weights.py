"""Bayesian shrinkage sanity checks for game_weights aggregation."""

import numpy as np
import pandas as pd
import pytest

from pipeline.game_rec.data.game_weights import aggregate_scores


@pytest.fixture
def toy_scores():
    """Two games:
    - A (appid=1): 100 raters, mean 8.0
    - B (appid=2): 2 raters, mean 10.0 (small sample, suspicious)
    Global mean comes out around 8.04.
    """
    rng = np.random.default_rng(0)
    a_scores = pd.DataFrame({
        "appid": [1] * 100,
        "s_round10_rec": rng.normal(loc=8.0, scale=0.1, size=100),
    })
    b_scores = pd.DataFrame({
        "appid": [2] * 2,
        "s_round10_rec": [10.0, 10.0],
    })
    return pd.concat([a_scores, b_scores], ignore_index=True)


def test_mean_mode_uses_raw_average(toy_scores):
    out = aggregate_scores(toy_scores, "s_round10_rec", weighting="mean")
    by_appid = out.set_index("appid")
    assert by_appid.loc[1, "weight"] == pytest.approx(by_appid.loc[1, "raw_mean"])
    assert by_appid.loc[2, "weight"] == pytest.approx(10.0)


def test_bayesian_shrinks_small_sample_toward_global_mean(toy_scores):
    out = aggregate_scores(toy_scores, "s_round10_rec",
                           weighting="bayesian", prior_strength=10.0)
    by_appid = out.set_index("appid")
    global_mean = toy_scores["s_round10_rec"].mean()

    a_w = by_appid.loc[1, "weight"]
    b_w = by_appid.loc[2, "weight"]

    # Game A (100 raters) barely moves
    assert abs(a_w - by_appid.loc[1, "raw_mean"]) < 0.05
    # Game B (2 raters) gets pulled toward global mean
    assert b_w < 10.0
    assert b_w > global_mean  # but stays above global since raw_mean was 10.0
    # Specifically B should be closer to global_mean than to 10.0
    assert (10.0 - b_w) > (b_w - global_mean)


def test_bayesian_with_zero_prior_equals_mean(toy_scores):
    mean_out = aggregate_scores(toy_scores, "s_round10_rec", weighting="mean")
    bayes_zero = aggregate_scores(toy_scores, "s_round10_rec",
                                  weighting="bayesian", prior_strength=0.0)
    np.testing.assert_allclose(
        mean_out.sort_values("appid")["weight"].values,
        bayes_zero.sort_values("appid")["weight"].values,
    )


def test_variance_mode_pulls_high_variance_games(toy_scores):
    # Add a third game with same mean as A but big variance
    rng = np.random.default_rng(1)
    noisy = pd.DataFrame({
        "appid": [3] * 100,
        "s_round10_rec": rng.normal(loc=8.0, scale=3.0, size=100),
    })
    df = pd.concat([toy_scores, noisy], ignore_index=True)

    out = aggregate_scores(df, "s_round10_rec", weighting="variance")
    by_appid = out.set_index("appid")
    global_mean = df["s_round10_rec"].mean()

    a_w = by_appid.loc[1, "weight"]
    c_w = by_appid.loc[3, "weight"]
    # A (low var) keeps its mean, C (high var) gets pulled toward global mean
    assert abs(a_w - 8.0) < 0.2
    assert abs(c_w - global_mean) < abs(c_w - 8.0)


def test_invalid_weighting_raises(toy_scores):
    with pytest.raises(ValueError):
        aggregate_scores(toy_scores, "s_round10_rec", weighting="bogus")
