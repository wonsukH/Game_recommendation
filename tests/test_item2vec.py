"""Smoke tests for Item2Vec sentence building and vector extraction."""

import numpy as np
import pandas as pd
import pytest

from pipeline.game_rec.models.item2vec import build_sentences, extract_vectors, train


def test_build_sentences_filters_by_threshold():
    df = pd.DataFrame({
        "steamid": [1, 1, 1, 2, 2],
        "appid": [100, 200, 300, 100, 400],
        "s_round10_rec": [8, 6, 9, 5, 10],
    })
    sentences = build_sentences(df, score_threshold=7)
    # User 1 has appid 100 (s=8) and 300 (s=9); appid 200 (s=6) excluded
    # User 2 has only appid 400 (s=10) — singleton, dropped
    assert len(sentences) == 1
    assert set(sentences[0]) == {"100", "300"}


def test_build_sentences_respects_allowed_appids():
    df = pd.DataFrame({
        "steamid": [1, 1, 1],
        "appid": [100, 200, 300],
        "s_round10_rec": [8, 8, 8],
    })
    sentences = build_sentences(df, score_threshold=7, allowed_appids={100, 200})
    # appid 300 not in allowed set — drops out, leaving user 1 with [100, 200]
    assert len(sentences) == 1
    assert set(sentences[0]) == {"100", "200"}


def test_extract_vectors_zero_for_missing_games():
    # Build a tiny model with vocab {100, 200}
    sentences = [["100", "200"]] * 50
    model = train(sentences, vector_size=8, window=2, min_count=1, epochs=3)
    # row2appid maps row 0 -> appid 100 (in vocab), row 1 -> 999 (missing)
    index_maps = {
        "appid2row": {100: 0, 999: 1},
        "row2appid": {0: 100, 1: 999},
    }
    vecs, stats = extract_vectors(model, index_maps)
    assert vecs.shape == (2, 8)
    # Row 0 should be non-zero, row 1 should be zero
    assert np.linalg.norm(vecs[0]) > 0
    assert np.linalg.norm(vecs[1]) == 0
    assert stats["n_zero"] == 1
    assert stats["n_in_vocab"] == 1
