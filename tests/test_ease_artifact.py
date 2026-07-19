"""EASE serving-artifact round-trip: on a tiny synthetic dataset, the sparse
top-K B (with K = n_items, i.e. untruncated) must reproduce EXACT Woodbury
scoring for every non-profile item — proving the B-materialization math and
the row-sum serving scorer agree with ease_recheck-style exact scoring."""

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from pipeline.game_rec.data.build_ease_artifact import (
    build_B_topk, exact_scores, fit_ease)

RNG = np.random.default_rng(7)
N_USERS, N_ITEMS, LAM = 30, 12, 10.0


@pytest.fixture(scope="module")
def tiny_fit():
    rows = []
    for u in range(N_USERS):
        owned = RNG.choice(N_ITEMS, size=RNG.integers(3, 8), replace=False)
        for a in owned:
            rows.append({"steamid": 1000 + u, "appid": int(a) + 10,
                         "s": float(RNG.uniform(0.1, 1.0))})
    scores = pd.DataFrame(rows)
    pool = set(range(10, 10 + N_ITEMS))
    users = sorted(scores["steamid"].unique())
    return fit_ease(scores, users, pool, LAM)


def test_b_rows_match_exact_scores(tiny_fit):
    X, V, diagP, items, col = tiny_fit
    B = build_B_topk(X, V, diagP, LAM, len(items), topk=len(items), chunk=5)
    for _ in range(10):
        prof_items = RNG.choice(len(items), size=3, replace=False)
        x = np.zeros(len(items))
        x[prof_items] = RNG.uniform(0.2, 1.0, size=3)
        exact = exact_scores(X, V, diagP, LAM, x)
        via_b = np.asarray((sparse.csr_matrix(x) @ B).todense()).ravel()
        mask = np.ones(len(items), bool)
        mask[prof_items] = False  # profile items are excluded at ranking anyway
        np.testing.assert_allclose(via_b[mask], exact[mask], rtol=1e-4, atol=1e-6)


def test_truncation_selects_by_abs_and_preserves_sign(tiny_fit):
    X, V, diagP, items, col = tiny_fit
    full = build_B_topk(X, V, diagP, LAM, len(items), topk=len(items), chunk=5)
    assert (full.data < 0).any(), "EASE B must carry negative weights (T-a signal)"
    trunc = build_B_topk(X, V, diagP, LAM, len(items), topk=4, chunk=5)
    assert trunc.diagonal().max() == 0.0
    assert np.diff(trunc.indptr).max() <= 4
    for j in range(len(items)):
        frow = np.asarray(full.getrow(j).todense()).ravel()
        kept = trunc.getrow(j)
        expect = set(np.argsort(-np.abs(frow))[:kept.nnz])
        assert set(kept.indices) == expect, f"row {j}: kept != top-|value| set"
        # sign preserved for every kept entry
        np.testing.assert_allclose(kept.toarray().ravel()[kept.indices],
                                   frow[kept.indices], rtol=1e-5)
