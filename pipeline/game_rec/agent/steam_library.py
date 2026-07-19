"""Steam library tool — the real personalization input (and the data-enrichment
lever the scaling ablation pointed at).

GetOwnedGames returns a user's OWNED games + total playtime — far richer than the
crawled review proxy (capped ~10/user). This is BOTH the live serving input and
the way to grow the data beyond the cap.

get_owned_games(steamid) -> {appid: playtime_minutes} restricted to the pool.
Requires STEAM_API_KEY and a PUBLIC profile. proxy_library() pulls a real user's
library from the crawled data for offline demo/testing (no API/public-profile needed).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("game_rec.agent.steam_library")
_OWNED_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"


def _pool(data_dir: Path) -> set[int]:
    return set(int(a) for a in load_index_maps(data_dir / "index_maps.json")["appid2row"].keys())


def get_owned_games(steamid: str, data_dir: str | Path = REPO_ROOT / "serving" / "data",
                    api_key: str | None = None, restrict_pool: bool = True) -> dict[int, float]:
    """Live: owned games + playtime (minutes) for a public profile, in-pool only."""
    key = api_key or os.environ.get("STEAM_API_KEY")
    if not key:
        raise RuntimeError("STEAM_API_KEY not set")
    r = requests.get(_OWNED_URL, params={
        "key": key, "steamid": steamid, "include_appinfo": 0,
        "include_played_free_games": 1, "format": "json"}, timeout=20)
    r.raise_for_status()
    games = (r.json().get("response", {}) or {}).get("games", []) or []
    pool = _pool(Path(data_dir)) if restrict_pool else None
    lib = {}
    for g in games:
        a = int(g.get("appid", 0))
        if pool is None or a in pool:
            lib[a] = float(g.get("playtime_forever", 0))
    log.info("steamid %s: %d owned games (%d in-pool)", steamid, len(games), len(lib))
    return lib


def proxy_library(min_liked: int = 8, seed: int = 0,
                  db_path: str | Path = REPO_ROOT / "data_collection" / "steam.db",
                  data_dir: str | Path = REPO_ROOT / "serving" / "data") -> dict[int, float]:
    """Offline demo: a real crawled user's played games + playtime, straight
    from steam.db (P5 — the review-CSV proxy is retired). Deterministic per seed."""
    import sqlite3
    import numpy as np
    pool = _pool(Path(data_dir))
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    users = [int(r[0]) for r in con.execute(
        "SELECT steamid FROM users WHERE public=1 AND complete=1 ORDER BY steamid")]
    rng = np.random.default_rng(seed)
    for _ in range(200):
        u = int(users[int(rng.integers(0, len(users)))])
        rows = con.execute(
            "SELECT appid, playtime_forever FROM owned "
            "WHERE steamid=? AND playtime_forever>0", (u,)).fetchall()
        lib = {int(a): float(pt) for a, pt in rows if int(a) in pool}
        if len(lib) >= min_liked:
            con.close()
            log.info("proxy library: steamid=%d, %d in-pool played games", u, len(lib))
            return lib
    con.close()
    raise RuntimeError("no demo user with enough played games found")
