"""Tests for the small helpers used by rerank_candidates.

The full rerank_candidates path needs the real VectorBasedRecommender
(which loads npy artifacts + langchain). We test the pure-numpy
_minmax helper in isolation since that's where most of the per-axis
score-normalization logic lives.
"""

import numpy as np
import pytest

from pipeline.game_rec.agent.scoring import minmax as _minmax


def test_minmax_basic_range():
    out = _minmax(np.array([1.0, 3.0, 5.0]))
    np.testing.assert_allclose(out, [0.0, 0.5, 1.0])


def test_minmax_handles_constant_input():
    # All-equal input must not produce NaN — fall back to mid value.
    out = _minmax(np.array([7.0, 7.0, 7.0]))
    np.testing.assert_allclose(out, [0.5, 0.5, 0.5])


def test_minmax_negative_range():
    out = _minmax(np.array([-2.0, 0.0, 2.0]))
    np.testing.assert_allclose(out, [0.0, 0.5, 1.0])


def test_minmax_preserves_order():
    rng = np.random.default_rng(11)
    arr = rng.normal(size=20)
    out = _minmax(arr)
    # rank order must be preserved
    np.testing.assert_array_equal(np.argsort(arr), np.argsort(out))
    assert out.min() == pytest.approx(0.0)
    assert out.max() == pytest.approx(1.0)
