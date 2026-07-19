"""DB-native catalog builders (P5): tag bags/matrix, unbiased popularity,
SteamSpy quality shrink, and constraint parsing — on synthetic frames."""

import json

import numpy as np
import pandas as pd

from pipeline.game_rec.data.build_catalog_db import (
    build_popularity, build_quality_steamspy, build_tag_bags,
    build_tag_matrix, parse_catalog_row)

POOL = [10, 20, 30]


def test_tag_bags_and_matrix():
    df = pd.DataFrame([
        {"appid": 10, "tags_json": json.dumps({"Action": 100, "Indie": 6, "Rare": 2})},
        {"appid": 20, "tags_json": json.dumps({"Action": 50})},
        {"appid": 30, "tags_json": None},
        {"appid": 99, "tags_json": json.dumps({"Action": 9})},  # not in pool
    ])
    bags = build_tag_bags(df, POOL, allowed=None, min_votes=5)
    assert set(bags) == {10, 20}
    assert "rare" not in bags[10]          # below min_votes
    X, tag2idx = build_tag_matrix(bags, POOL)
    assert X.shape == (3, len(tag2idx))
    assert X[0].sum() == 2 and X[1].sum() == 1 and X[2].sum() == 0
    assert X[0, tag2idx["action"]] == 1    # canonicalized lowercase


def test_tag_bags_respects_allowed_vocab():
    df = pd.DataFrame([{"appid": 10, "tags_json": json.dumps({"Action": 9, "Zzz": 9})}])
    bags = build_tag_bags(df, POOL, allowed={"action"})
    assert bags[10] == ["action"]


def test_popularity_epsilon_floor():
    pop = build_popularity(POOL, {"10": 0.5, "20": 0.001})
    assert pop[0] == 0.5 and pop[1] == 0.001
    assert pop[2] == 0.001                 # missing -> min positive rate
    assert (pop > 0).all()


def test_quality_shrinks_low_n_toward_mean():
    ss = pd.DataFrame([
        {"appid": 10, "positive": 900, "negative": 100, "tags_json": None},
        {"appid": 20, "positive": 1, "negative": 0, "tags_json": None},
    ])
    q = build_quality_steamspy(ss, POOL, prior_m=100.0)
    g10, g20 = q["games"]["10"], q["games"]["20"]
    assert g10["raw"] == 9.0
    assert g20["raw"] == 10.0
    # 1-vote perfect score must be pulled far toward the global mean
    assert abs(g20["q"] - q["global_mean"]) < abs(g20["raw"] - q["global_mean"]) / 10
    assert g10["n"] == 1000


def test_parse_catalog_row():
    row = pd.DataFrame([{
        "appid": 10, "name": "G",
        "categories_json": json.dumps([{"id": 2, "description": "Single-player"},
                                       {"id": 9, "description": "Co-op"}]),
        "supported_languages": "English, Korean",
        "price_final": 1999, "is_free": 0, "release_date": "12 Mar, 2020",
        "metacritic_score": 88.0,
    }]).iloc[0]
    m = parse_catalog_row(row)
    assert m["coop"] and m["single_player"] and not m["multiplayer"]
    assert m["korean"] and m["price"] == 19.99 and m["metacritic"] == 88.0
    free = pd.DataFrame([{
        "appid": 11, "name": "F", "categories_json": None,
        "supported_languages": None, "price_final": np.nan, "is_free": 1,
        "release_date": None, "metacritic_score": 0.0,
    }]).iloc[0]
    mf = parse_catalog_row(free)
    assert mf["is_free"] and mf["price"] == 0.0 and mf["metacritic"] is None
