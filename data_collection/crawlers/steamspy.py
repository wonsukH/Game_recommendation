"""SteamSpy API crawler — tags + popularity in one call.

SteamSpy (https://steamspy.com/) exposes user-defined tags + vote counts
+ owner ranges + 2-week player counts, which is exactly what the
official Steam Store API does NOT provide. No API key needed.

Two endpoints used:
- `request=all&page=N` — batch listing (1000 games per page). Free,
  used for bulk discovery.
- `request=appdetails&appid=X` — per-game tag dict with vote counts.
  Rate limit: 1 req/sec (we apply a 1.1s sliding window to stay safe).

Usage:
    python -m data_collection.crawlers.steamspy --target-count 10000
    python -m data_collection.crawlers.steamspy --target-count 100 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from pathlib import Path
from typing import Iterable

import aiohttp

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR = REPO_ROOT / "outputs"

sys.path.insert(0, str(REPO_ROOT))
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("crawlers.steamspy")


STEAMSPY_BASE = "https://steamspy.com/api.php"
APPDETAILS_RATE_S = 1.1   # 1 req/sec limit + safety margin
ALL_PAGE_RATE_S = 1.0     # batch endpoint less restricted


async def _fetch_json(session: aiohttp.ClientSession, params: dict, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            async with session.get(STEAMSPY_BASE, params=params, timeout=30) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                log.warning("HTTP %d for params=%s (attempt %d)", resp.status, params, attempt + 1)
        except Exception as e:
            log.warning("request failed (attempt %d): %s", attempt + 1, e)
        await asyncio.sleep(2 ** attempt)
    return None


async def fetch_all_pages(session: aiohttp.ClientSession, target_count: int) -> list[dict]:
    """Iterate /all pages until target reached. Each page has up to 1000 games."""
    games: list[dict] = []
    page = 0
    while len(games) < target_count:
        log.info("fetching /all page=%d (so far %d games)", page, len(games))
        data = await _fetch_json(session, {"request": "all", "page": page})
        if not data:
            log.warning("page %d empty or failed, stopping", page)
            break
        # Response is a dict keyed by appid (str)
        batch = list(data.values())
        if not batch:
            break
        games.extend(batch)
        page += 1
        await asyncio.sleep(ALL_PAGE_RATE_S)
    return games[:target_count]


async def fetch_appdetails_many(session: aiohttp.ClientSession, appids: Iterable[int]) -> dict[int, dict]:
    """Fetch per-appid details with tag dicts. Serial (rate limit)."""
    out: dict[int, dict] = {}
    appids = list(appids)
    total = len(appids)
    start = time.time()
    for idx, appid in enumerate(appids, 1):
        data = await _fetch_json(session, {"request": "appdetails", "appid": appid})
        if data and "tags" in data:
            out[appid] = data
        if idx % 100 == 0:
            elapsed = time.time() - start
            rate = idx / elapsed
            eta_s = (total - idx) / rate
            log.info("appdetails progress %d/%d (%.1f/s, eta %.0fs)", idx, total, rate, eta_s)
        await asyncio.sleep(APPDETAILS_RATE_S)
    return out


def _row_for(game: dict) -> dict:
    """Normalize a SteamSpy /all or /appdetails record into a flat row."""
    tags = game.get("tags") or {}
    if isinstance(tags, list):  # /all returns dict, but defensive
        tags = {}
    return {
        "appid": game.get("appid"),
        "name": game.get("name"),
        "developer": game.get("developer"),
        "publisher": game.get("publisher"),
        "owners": game.get("owners"),
        "average_forever": game.get("average_forever"),
        "average_2weeks": game.get("average_2weeks"),
        "median_forever": game.get("median_forever"),
        "median_2weeks": game.get("median_2weeks"),
        "ccu": game.get("ccu"),
        "price": game.get("price"),
        "initialprice": game.get("initialprice"),
        "discount": game.get("discount"),
        "languages": game.get("languages"),
        "genre": game.get("genre"),
        "tags_json": json.dumps(tags, ensure_ascii=False),
    }


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        log.warning("no rows to write to %s", path)
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log.info("wrote %d rows to %s", len(rows), path)


async def main_async(target_count: int, dry_run: bool, out_path: Path) -> None:
    async with aiohttp.ClientSession() as session:
        log.info("phase 1: bulk discovery via /all (target=%d)", target_count)
        bulk = await fetch_all_pages(session, target_count)
        log.info("got %d games from /all", len(bulk))

        appids = [int(g["appid"]) for g in bulk if g.get("appid")]

        if dry_run:
            log.info("dry-run: skipping per-appid tag enrichment")
            rows = [_row_for(g) for g in bulk]
        else:
            log.info("phase 2: enriching with per-appid tag dicts")
            details = await fetch_appdetails_many(session, appids)
            # Merge: prefer details where available, fall back to bulk
            rows = []
            for g in bulk:
                appid = int(g["appid"])
                if appid in details:
                    merged = {**g, **details[appid]}
                else:
                    merged = g
                rows.append(_row_for(merged))

        write_csv(rows, out_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-count", type=int, default=10000,
                        help="Number of games to collect (paginated from popular).")
    parser.add_argument("--output", type=Path, default=OUTPUTS_DIR / "steamspy_games.csv",
                        help="Output CSV path.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip per-appid enrichment (faster, used for sample/test).")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(main_async(args.target_count, args.dry_run, args.output))


if __name__ == "__main__":
    main()
