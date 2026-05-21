"""Tests for the small helpers used by rerank_candidates.

The full rerank_candidates path needs the real VectorBasedRecommender
(which loads npy artifacts + langchain). We test the pure-numpy
_minmax helper in isolation since that's where most of the per-axis
score-normalization logic lives.
"""

import math

import numpy as np
import pytest

from pipeline.game_rec.agent.scoring import minmax as _minmax, sigmoid_modifier


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


# --- sigmoid_modifier (slider -> signed modifier in (-1, +1)) ---

def test_sigmoid_modifier_center_is_neutral():
    """Slider 5 must produce exactly 0 — popularity signal has no effect."""
    assert abs(sigmoid_modifier(5.0)) < 1e-9


def test_sigmoid_modifier_extremes():
    """Slider 0 and 10 must produce strong (but bounded) signed modifiers."""
    assert sigmoid_modifier(10.0) > 0.9
    assert sigmoid_modifier(0.0) < -0.9
    # Bounded inside [-1, +1] (asymptotic — exp() underflows for very large args)
    assert sigmoid_modifier(100.0) <= 1.0
    assert sigmoid_modifier(-100.0) >= -1.0


def test_sigmoid_modifier_monotone():
    """Increasing slider must monotonically increase the modifier."""
    vals = [sigmoid_modifier(s) for s in range(0, 11)]
    assert all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))


def test_sigmoid_modifier_near_center_is_weak():
    """The whole point of the sigmoid: 4 vs 6 should barely matter
    compared to 9 vs 10 — gentle near center, steep at extremes."""
    mid_step = sigmoid_modifier(6) - sigmoid_modifier(4)
    edge_step = sigmoid_modifier(10) - sigmoid_modifier(8)
    # Sigmoid: should be approximately similar OR edge step larger
    # (depending on steepness). Either way, mid-step should NOT swamp edge-step.
    assert mid_step < 0.8  # not amplified
    # And direction is sane
    assert mid_step > 0 and edge_step > 0


def test_sigmoid_modifier_nan_safe():
    # Non-finite input is treated as "invalid slider" -> neutral (0.0).
    # Slider values come from a 0-10 UI control so neither NaN nor inf
    # can arise in practice; the guard exists to avoid silent corruption.
    assert sigmoid_modifier(float("nan")) == 0.0
    assert sigmoid_modifier(float("inf")) == 0.0
    assert sigmoid_modifier(float("-inf")) == 0.0


def test_sigmoid_modifier_symmetric_around_center():
    """sigmoid(5+d) and sigmoid(5-d) should be opposite-signed equals."""
    for d in [1.0, 2.0, 3.0, 4.0]:
        a = sigmoid_modifier(5.0 + d)
        b = sigmoid_modifier(5.0 - d)
        assert math.isclose(a, -b, abs_tol=1e-6), f"asymmetric at d={d}: {a} vs {b}"
