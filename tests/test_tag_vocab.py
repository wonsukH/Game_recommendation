"""SteamSpy / legacy auto-detection + vote filtering for tag_vocab."""

import pandas as pd
import pytest

from pipeline.game_rec.data.tag_vocab import (
    detect_format,
    extract_tags_steamspy,
    extract_tags_legacy,
    normalize_tag,
    apply_alias,
)


def test_detect_steamspy_format():
    df = pd.DataFrame({"appid": [1], "tags_json": ['{"Roguelike": 100}']})
    assert detect_format(df) == "steamspy"


def test_detect_legacy_format():
    df = pd.DataFrame({"appid": [1], "tags": ["Roguelike, Cute"]})
    assert detect_format(df) == "legacy"


def test_detect_unknown_format_raises():
    df = pd.DataFrame({"appid": [1], "something_else": ["x"]})
    with pytest.raises(ValueError):
        detect_format(df)


def test_steamspy_extract_filters_low_votes():
    df = pd.DataFrame({
        "appid": [1, 2],
        "tags_json": [
            '{"Roguelike": 100, "Cute": 3, "Action": 50}',
            '{"Anime": 4, "RPG": 200}',
        ],
    })
    out = extract_tags_steamspy(df, min_votes=5)
    # Cute (3) and Anime (4) excluded
    assert sorted(out) == ["Action", "RPG", "Roguelike"]


def test_steamspy_extract_handles_garbage_json():
    df = pd.DataFrame({
        "appid": [1, 2, 3],
        "tags_json": ['{"OK": 10}', "not json", None],
    })
    out = extract_tags_steamspy(df, min_votes=1)
    assert out == ["OK"]


def test_legacy_extract_splits_commas():
    df = pd.DataFrame({
        "appid": [1, 2],
        "tags": ["Roguelike, Cute, RPG", None],
    })
    out = extract_tags_legacy(df)
    assert sorted(out) == ["Cute", "RPG", "Roguelike"]


def test_normalize_tag_basics():
    assert normalize_tag("  Open World  ") == "open-world"
    assert normalize_tag("RPG / Action") == "rpg-action"
    assert normalize_tag("SOULSlike") == "soulslike"


def test_apply_alias():
    assert apply_alias("rogue like") == "roguelike"
    assert apply_alias("rogue-like") == "roguelike"
    assert apply_alias("single player") == "single-player"
    # Unknown alias -> passthrough
    assert apply_alias("anime") == "anime"


def test_full_pipeline_steamspy_to_normalized():
    """Realistic: parse SteamSpy JSON, then normalize + dedupe."""
    df = pd.DataFrame({
        "appid": [1],
        "tags_json": ['{"Open World": 100, "Rogue-Like": 50, "Open World ": 30}'],
    })
    raw = extract_tags_steamspy(df, min_votes=5)
    normalized = [apply_alias(normalize_tag(t)) for t in raw]
    # "Open World" and "Open World " both normalize to "open-world"
    # "Rogue-Like" -> "rogue-like" -> aliased to "roguelike"
    assert sorted(set(normalized)) == ["open-world", "roguelike"]
