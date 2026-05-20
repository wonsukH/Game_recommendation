"""Popularity derivation: SteamSpy owners parsing + source preference."""

import numpy as np
import pandas as pd
import pytest

from pipeline.game_rec.data.game_popularity import build_popularity_array, parse_owners_range


@pytest.mark.parametrize("s,expected", [
    ("1,000,000 .. 2,000,000", 1_500_000.0),
    ("50,000 .. 100,000", 75_000.0),
    ("0 .. 20,000", 10_000.0),
    ("not a range", float("nan")),
    ("", float("nan")),
])
def test_parse_owners_range(s, expected):
    got = parse_owners_range(s)
    if expected != expected:  # NaN
        assert got != got
    else:
        assert got == pytest.approx(expected)


def test_steamspy_preferred_over_reviews():
    row2appid = {0: 100, 1: 200, 2: 300}
    spy = pd.DataFrame({
        "appid": [100, 200],
        "owners": ["1,000 .. 3,000", "5,000 .. 9,000"],
    })
    rev = pd.DataFrame({"appid": [100, 200, 200, 300, 300, 300]})

    pop, stats = build_popularity_array(row2appid, spy, rev)
    # 100 -> SteamSpy midpoint 2000
    assert pop[0] == pytest.approx(2000.0)
    # 200 -> SteamSpy midpoint 7000 (NOT 2 from review count)
    assert pop[1] == pytest.approx(7000.0)
    # 300 -> falls back to review count = 3
    assert pop[2] == pytest.approx(3.0)

    assert stats["n_from_steamspy"] == 2
    assert stats["n_from_reviews"] == 1
    assert stats["n_missing_imputed"] == 0


def test_missing_games_get_imputed_one():
    row2appid = {0: 999}
    spy = pd.DataFrame({"appid": [100], "owners": ["100 .. 200"]})
    rev = pd.DataFrame({"appid": [100]})
    pop, stats = build_popularity_array(row2appid, spy, rev)
    # 999 not in either source -> imputed as 1.0
    assert pop[0] == pytest.approx(1.0)
    assert stats["n_missing_imputed"] == 1


def test_reviews_only_when_steamspy_none():
    row2appid = {0: 100, 1: 200}
    rev = pd.DataFrame({"appid": [100, 100, 100, 200]})
    pop, stats = build_popularity_array(row2appid, None, rev)
    assert pop[0] == pytest.approx(3.0)
    assert pop[1] == pytest.approx(1.0)
    assert stats["n_from_steamspy"] == 0
    assert stats["n_from_reviews"] == 2
