"""Steam Store `appdetails` API crawler — metadata SteamSpy doesn't have.

SteamSpy has tags + popularity. Steam Store API has description,
genres (official), languages, release_date, developers, publishers,
price, platforms — richer metadata for filtering and explanation.

No API key needed. Rate limit unofficial but ~200 req / 5 min is the
documented community guideline; we use 1.0s sliding window which is
~300 req / 5 min and has been stable in practice.

Usage:
    python -m data_collection.crawlers.steam_appdetails --input outputs/steamspy_games.csv
    python -m data_collection.crawlers.steam_appdetails --input outputs/steamspy_games.csv --limit 100
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from pathlib import Path

import aiohttp
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR = REPO_ROOT / "outputs"

sys.path.insert(0, str(REPO_ROOT))
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("crawlers.steam_appdetails")


APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
RATE_S = 1.5            # base inter-request sleep, slower than the 200/5min guideline
BACKOFF_429_BASE_S = 60 # long sleep when Steam returns 429 (burst limit hit)
MAX_RETRIES_429 = 3


async def _fetch_appdetails(
    session: aiohttp.ClientSession,
    appid: int,
    lang: str = "english",
) -> dict | None:
    """Returns the inner `data` dict for the given appid, or None on miss.

    Handles 429 (rate limit) with an exponential long backoff (60s, 120s,
    240s) up to MAX_RETRIES_429 times. Other non-200 statuses (404 for
    dropped apps, 403 for region-locked) return None immediately.

    Connection-level errors are retried with shorter exponential backoff
    (1s, 2s, 4s) since they're usually transient.
    """
    for attempt in range(MAX_RETRIES_429):
        try:
            async with session.get(
                APPDETAILS_URL,
                params={"appids": appid, "cc": "us", "l": lang},
                timeout=30,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    entry = data.get(str(appid)) or {}
                    if not entry.get("success"):
                        return None
                    return entry.get("data")
                if resp.status == 429:
                    sleep_s = BACKOFF_429_BASE_S * (2 ** attempt)
                    log.warning(
                        "HTTP 429 for appid %d (attempt %d/%d) — sleeping %ds",
                        appid, attempt + 1, MAX_RETRIES_429, sleep_s,
                    )
                    await asyncio.sleep(sleep_s)
                    continue
                # Other non-200: don't retry, just record as miss
                log.warning("HTTP %d for appid %d", resp.status, appid)
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("appid %d transient failure (attempt %d): %s",
                        appid, attempt + 1, e)
            await asyncio.sleep(2 ** attempt)
    log.warning("appid %d gave up after %d retries", appid, MAX_RETRIES_429)
    return None


def _flatten(appid: int, data: dict | None) -> dict:
    """Flatten one Steam Store appdetails payload into a single CSV row."""
    if data is None:
        return {"appid": appid, "available": False}
    return {
        "appid": appid,
        "available": True,
        "name": data.get("name"),
        "type": data.get("type"),
        "is_free": data.get("is_free"),
        "short_description": data.get("short_description", "").replace("\n", " ").strip(),
        "detailed_description": data.get("detailed_description", "").replace("\n", " ").strip()[:2000],
        "supported_languages": data.get("supported_languages", "").replace("<br>", " ")[:500],
        "developers": ", ".join(data.get("developers") or []),
        "publishers": ", ".join(data.get("publishers") or []),
        "platforms": json.dumps(data.get("platforms") or {}),
        "genres": ", ".join(g.get("description", "") for g in (data.get("genres") or [])),
        "categories": ", ".join(c.get("description", "") for c in (data.get("categories") or [])),
        "release_date": (data.get("release_date") or {}).get("date"),
        "coming_soon": (data.get("release_date") or {}).get("coming_soon"),
        "price_final": (data.get("price_overview") or {}).get("final"),
        "price_currency": (data.get("price_overview") or {}).get("currency"),
        "metacritic_score": (data.get("metacritic") or {}).get("score"),
        "header_image": data.get("header_image"),
    }


async def main_async(
    input_csv: Path,
    output_csv: Path,
    limit: int | None,
    retry_missing: bool = False,
) -> None:
    df_in = pd.read_csv(input_csv)
    appids = df_in["appid"].astype(int).tolist()
    if limit:
        appids = appids[:limit]

    # Resume mode: skip appids already marked available=True in output_csv.
    # Optionally also re-try the ones marked available=False (retry_missing).
    existing_rows: list[dict] = []
    skip_set: set[int] = set()
    if output_csv.exists():
        prev = pd.read_csv(output_csv)
        existing_rows = prev.to_dict("records")
        already_done = prev[prev["available"] == True]
        skip_set = set(already_done["appid"].astype(int).tolist())
        if retry_missing:
            # Drop the failed rows from existing — we'll re-fetch them
            existing_rows = already_done.to_dict("records")
            log.info(
                "resume: %d already available, %d will be retried, %d to skip",
                len(skip_set),
                int((prev["available"] == False).sum()),
                len(skip_set),
            )
        else:
            log.info("resume: skipping %d appids that already have available=True",
                     len(skip_set))

    todo = [a for a in appids if a not in skip_set]
    log.info("fetching appdetails for %d games (skipping %d) -> %s",
             len(todo), len(appids) - len(todo), output_csv)

    rows = list(existing_rows)
    start = time.time()

    async with aiohttp.ClientSession() as session:
        for idx, appid in enumerate(todo, 1):
            data = await _fetch_appdetails(session, appid)
            rows.append(_flatten(appid, data))
            if idx % 50 == 0:
                elapsed = time.time() - start
                rate = idx / elapsed if elapsed > 0 else 0
                eta_s = (len(todo) - idx) / rate if rate > 0 else 0
                log.info(
                    "progress %d/%d (%.1f/s, eta %.0fs, %d available so far)",
                    idx, len(todo), rate, eta_s,
                    sum(1 for r in rows if r.get("available")),
                )
                _write(rows, output_csv)
            await asyncio.sleep(RATE_S)

    _write(rows, output_csv)
    log.info("done. %d rows total, %d with data", len(rows),
             sum(1 for r in rows if r.get("available")))


def _write(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Union of all keys (rows for unavailable games are smaller)
    fieldnames: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                fieldnames.append(k)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=OUTPUTS_DIR / "steamspy_games.csv",
                        help="Input CSV with `appid` column (e.g. SteamSpy output).")
    parser.add_argument("--output", type=Path, default=OUTPUTS_DIR / "steam_appdetails.csv",
                        help="Output CSV path.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only fetch first N appids (sample / debug).")
    parser.add_argument("--retry-missing", action="store_true",
                        help="Re-fetch appids that previously came back available=False "
                             "(e.g. 429 misses). Skips ones already marked True.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(main_async(args.input, args.output, args.limit, args.retry_missing))


if __name__ == "__main__":
    main()
