"""Unit tests for the 4-axis evaluation metrics."""

import numpy as np
import pytest

from pipeline.game_rec.evaluation.metrics import (
    recall_at_k, precision_at_k, ndcg_at_k,
    intra_list_diversity, novelty, serendipity,
    evaluate_recommendation,
)


# ----- Relevance --------------------------------------------------------------

def test_recall_perfect_hits():
    assert recall_at_k({1, 2, 3}, [1, 2, 3, 4, 5], k=3) == pytest.approx(1.0)


def test_recall_partial():
    assert recall_at_k({1, 2, 3}, [1, 99, 99, 99], k=4) == pytest.approx(1 / 3)


def test_recall_empty_true_set():
    assert recall_at_k(set(), [1, 2, 3], k=3) == 0.0


def test_precision_simple():
    assert precision_at_k({1, 2, 3}, [1, 99, 2, 99], k=4) == pytest.approx(0.5)


def test_ndcg_top_hit_better_than_bottom_hit():
    true = {99}
    top_hit_ndcg = ndcg_at_k(true, [99, 0, 0, 0, 0], k=5)
    bot_hit_ndcg = ndcg_at_k(true, [0, 0, 0, 0, 99], k=5)
    assert top_hit_ndcg == pytest.approx(1.0)
    assert bot_hit_ndcg < top_hit_ndcg


def test_ndcg_perfect_recall_gives_1():
    true = {1, 2, 3}
    assert ndcg_at_k(true, [1, 2, 3, 99, 99], k=5) == pytest.approx(1.0)


# ----- Diversity --------------------------------------------------------------

def test_diversity_identical_items_is_zero():
    # 3 copies of the same vector -> pairwise sim = 1, distance = 0
    embs = np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]])
    assert intra_list_diversity([0, 1, 2], embs) == pytest.approx(0.0)


def test_diversity_orthogonal_items_is_one():
    embs = np.eye(3)
    assert intra_list_diversity([0, 1, 2], embs) == pytest.approx(1.0)


def test_diversity_single_item_is_zero():
    embs = np.eye(3)
    assert intra_list_diversity([0], embs) == 0.0


# ----- Novelty ----------------------------------------------------------------

def test_novelty_uniform_popularity():
    # 4 items all equally popular -> info = log2(4) = 2 for each
    popularity = np.array([10.0, 10.0, 10.0, 10.0])
    assert novelty([0, 1, 2, 3], popularity) == pytest.approx(2.0)


def test_novelty_rare_item_scores_higher():
    # Item 0 has 99% of mass, item 1 has 1% — recommending the rare one
    # gives much higher self-info
    popularity = np.array([99.0, 1.0])
    info_popular = novelty([0], popularity)
    info_rare = novelty([1], popularity)
    assert info_rare > info_popular
    # rare ≈ -log2(0.01) ≈ 6.64
    assert info_rare == pytest.approx(np.log2(100), abs=0.01)


# ----- Serendipity ------------------------------------------------------------

def test_serendipity_relevant_and_unexpected():
    # Recs [1, 2, 3]. True = {2, 3}. Popularity baseline says {1, 2}.
    # Item 2 is relevant but also in baseline -> not serendipitous.
    # Item 3 is relevant and NOT in baseline -> serendipitous.
    # Item 1 is in baseline but not in true -> not serendipitous.
    assert serendipity([1, 2, 3], {2, 3}, {1, 2}) == pytest.approx(1 / 3)


def test_serendipity_zero_when_no_relevant():
    assert serendipity([1, 2, 3], set(), {1, 2}) == 0.0


def test_serendipity_zero_when_all_in_baseline():
    # All relevant items also in baseline -> nothing surprising
    assert serendipity([1, 2], {1, 2}, {1, 2, 3}) == 0.0


# ----- Aggregator -------------------------------------------------------------

def test_evaluate_recommendation_returns_all_four_axes():
    embs = np.eye(4)
    popularity = np.array([10.0, 10.0, 10.0, 10.0])
    out = evaluate_recommendation(
        rec_indices=[0, 1, 2],
        true_set={0, 1},
        item_embeddings=embs,
        popularity=popularity,
        popularity_baseline_top={3},
        k=3,
    )
    assert set(out.keys()) == {
        "recall@k", "precision@k", "ndcg@k",
        "diversity@k", "novelty@k", "serendipity@k",
    }
    assert out["recall@k"] == pytest.approx(1.0)
    assert out["precision@k"] == pytest.approx(2 / 3)
    assert out["diversity@k"] == pytest.approx(1.0)
    assert out["novelty@k"] == pytest.approx(2.0)
