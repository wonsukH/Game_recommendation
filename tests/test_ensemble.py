"""Verify the PPMI + Item2Vec ensemble combiner."""

import numpy as np
import pytest

from pipeline.game_rec.models.game_vectors import ensemble_game_vectors


def test_alpha_one_returns_ppmi_normalized():
    ppmi = np.array([[3.0, 4.0], [1.0, 0.0]])
    user = np.array([[1.0, 0.0], [0.0, 1.0]])
    out = ensemble_game_vectors(ppmi, user, alpha=1.0)
    expected = np.array([[0.6, 0.8], [1.0, 0.0]])
    np.testing.assert_allclose(out, expected, atol=1e-5)


def test_alpha_zero_returns_user_signal_normalized():
    ppmi = np.array([[1.0, 0.0]])
    user = np.array([[3.0, 4.0]])
    out = ensemble_game_vectors(ppmi, user, alpha=0.0)
    np.testing.assert_allclose(out, [[0.6, 0.8]], atol=1e-5)


def test_zero_user_signal_falls_back_to_ppmi():
    # Row 0 has Item2Vec signal, row 1 doesn't (all zeros).
    # Row 1 must use PPMI directly regardless of alpha.
    ppmi = np.array([[1.0, 0.0], [0.0, 1.0]])
    user = np.array([[0.0, 1.0], [0.0, 0.0]])
    out = ensemble_game_vectors(ppmi, user, alpha=0.5)
    # Row 1: pure PPMI [0, 1] (already normalized)
    np.testing.assert_allclose(out[1], [0.0, 1.0], atol=1e-5)
    # Row 0: blend of [1, 0] and [0, 1] with alpha=0.5
    # 0.5 * (1,0) + 0.5 * (0,1) = (0.5, 0.5), normalized -> (sqrt(0.5), sqrt(0.5))
    np.testing.assert_allclose(out[0], [np.sqrt(0.5), np.sqrt(0.5)], atol=1e-5)


def test_output_is_l2_normalized_per_row():
    rng = np.random.default_rng(7)
    ppmi = rng.normal(size=(10, 8))
    user = rng.normal(size=(10, 8))
    out = ensemble_game_vectors(ppmi, user, alpha=0.6)
    norms = np.linalg.norm(out, axis=1)
    np.testing.assert_allclose(norms, np.ones(10), atol=1e-5)


def test_shape_mismatch_raises():
    with pytest.raises(ValueError):
        ensemble_game_vectors(
            np.zeros((5, 8)), np.zeros((5, 16)), alpha=0.5,
        )
