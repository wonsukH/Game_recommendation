"""Unified SQLite store for all crawled Steam preference/quality data + a
bulletproof daily API-call budget.

Why SQLite (not scattered JSON): indexed, transactional (crash-safe), incremental,
resumable, queryable; one local file. End-user data lives here LOCALLY only and is
gitignored (Steam Web API ToU — never publish/redistribute user data).

Daily budget (the hard guarantee): every API call must first win `reserve()`, which
in a single `BEGIN IMMEDIATE` transaction checks today's counter and atomically
increments it BEFORE the HTTP call. If the increment would exceed the day's limit it
returns False and the caller stops. BEGIN IMMEDIATE serializes writers, so even with
parallel workers/processes the calendar-day total can NEVER exceed the limit
(reserve-before-call also counts failed calls, which Steam counts too).
Default limit 90,000 < Steam's 100,000/day hard cap (10k margin).
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "data_collection" / "steam.db"
DAILY_LIMIT = 90_000          # < 100k Steam hard cap
_UTC = timezone.utc

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  steamid TEXT PRIMARY KEY, country TEXT, level INTEGER, xp INTEGER,
  public INTEGER, complete INTEGER DEFAULT 0, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS owned(
  steamid TEXT, appid INTEGER, playtime_forever REAL, playtime_2weeks REAL,
  PRIMARY KEY(steamid, appid));
CREATE TABLE IF NOT EXISTS recently(
  steamid TEXT, appid INTEGER, playtime_2weeks REAL, PRIMARY KEY(steamid, appid));
CREATE TABLE IF NOT EXISTS wishlist(
  steamid TEXT, appid INTEGER, priority INTEGER, PRIMARY KEY(steamid, appid));
CREATE TABLE IF NOT EXISTS followed(
  steamid TEXT, appid INTEGER, PRIMARY KEY(steamid, appid));
CREATE TABLE IF NOT EXISTS friends(
  steamid TEXT, friend_steamid TEXT, PRIMARY KEY(steamid, friend_steamid));
CREATE TABLE IF NOT EXISTS user_groups(
  steamid TEXT, gid TEXT, PRIMARY KEY(steamid, gid));
CREATE TABLE IF NOT EXISTS achievements(
  steamid TEXT, appid INTEGER, unlocked INTEGER, total INTEGER,
  PRIMARY KEY(steamid, appid));
CREATE TABLE IF NOT EXISTS achievement_rarity(
  appid INTEGER, apiname TEXT, global_pct REAL, PRIMARY KEY(appid, apiname));
CREATE TABLE IF NOT EXISTS reviews(
  recommendationid TEXT PRIMARY KEY, appid INTEGER, author_steamid TEXT,
  voted_up INTEGER, review_text TEXT, votes_up INTEGER, votes_funny INTEGER,
  weighted_vote_score REAL, playtime_at_review REAL, timestamp_created INTEGER);
CREATE TABLE IF NOT EXISTS games(
  appid INTEGER PRIMARY KEY, name TEXT, type TEXT, is_free INTEGER, genres TEXT,
  categories TEXT, price_final INTEGER, metacritic_score INTEGER, release_date TEXT,
  supported_languages TEXT, short_description TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS game_live(
  appid INTEGER PRIMARY KEY, ccu INTEGER, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS steamspy(
  appid INTEGER PRIMARY KEY, owners TEXT, average_forever INTEGER,
  median_forever INTEGER, ccu INTEGER, tags_json TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS budget(day TEXT PRIMARY KEY, calls INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS crawl_state(
  key TEXT PRIMARY KEY, pos INTEGER NOT NULL DEFAULT 0, done INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_owned_appid ON owned(appid);
CREATE INDEX IF NOT EXISTS ix_reviews_author ON reviews(author_steamid);
CREATE INDEX IF NOT EXISTS ix_reviews_appid ON reviews(appid);
CREATE INDEX IF NOT EXISTS ix_ach_appid ON achievements(appid);
"""


def today_utc() -> str:
    return datetime.now(_UTC).strftime("%Y-%m-%d")


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=60, isolation_level=None)  # autocommit; we manage txns
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.executescript(SCHEMA)
    return conn


# ---------------- bulletproof daily budget ----------------
class BudgetExhausted(Exception):
    pass


def seed_today(conn: sqlite3.Connection, already_spent: int, day: str | None = None) -> None:
    """Initialize today's counter to `already_spent` (e.g. quota used earlier outside
    this store). Only raises the counter, never lowers it."""
    day = day or today_utc()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        row = conn.execute("SELECT calls FROM budget WHERE day=?", (day,)).fetchone()
        cur = row[0] if row else 0
        new = max(cur, int(already_spent))
        conn.execute("INSERT INTO budget(day,calls) VALUES(?,?) "
                     "ON CONFLICT(day) DO UPDATE SET calls=?", (day, new, new))
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;"); raise


def reserve(conn: sqlite3.Connection, n: int = 1, limit: int = DAILY_LIMIT,
            day: str | None = None) -> bool:
    """Atomically reserve `n` calls against today's budget BEFORE making them.
    Returns True if reserved (caller may proceed), False if it would exceed `limit`.
    BEGIN IMMEDIATE serializes writers → calendar-day total can never exceed limit."""
    day = day or today_utc()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        row = conn.execute("SELECT calls FROM budget WHERE day=?", (day,)).fetchone()
        cur = row[0] if row else 0
        if cur + n > limit:
            conn.execute("COMMIT;")
            return False
        conn.execute("INSERT INTO budget(day,calls) VALUES(?,?) "
                     "ON CONFLICT(day) DO UPDATE SET calls=calls+?", (day, n, n))
        conn.execute("COMMIT;")
        return True
    except Exception:
        conn.execute("ROLLBACK;"); raise


def spent_today(conn: sqlite3.Connection, day: str | None = None) -> int:
    day = day or today_utc()
    row = conn.execute("SELECT calls FROM budget WHERE day=?", (day,)).fetchone()
    return int(row[0]) if row else 0


# ---------------- cursors (resume) ----------------
def get_cursor(conn: sqlite3.Connection, key: str) -> tuple[int, bool]:
    row = conn.execute("SELECT pos, done FROM crawl_state WHERE key=?", (key,)).fetchone()
    return (int(row[0]), bool(row[1])) if row else (0, False)


def set_cursor(conn: sqlite3.Connection, key: str, pos: int, done: bool = False) -> None:
    conn.execute("INSERT INTO crawl_state(key,pos,done) VALUES(?,?,?) "
                 "ON CONFLICT(key) DO UPDATE SET pos=?, done=?",
                 (key, pos, int(done), pos, int(done)))


# ---------------- bulk upsert ----------------
def upsert_many(conn: sqlite3.Connection, table: str, cols: list[str], rows: list[tuple]) -> int:
    if not rows:
        return 0
    ph = ",".join("?" * len(cols))
    conn.execute("BEGIN;")
    try:
        conn.executemany(f"INSERT OR REPLACE INTO {table}({','.join(cols)}) VALUES({ph})", rows)
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;"); raise
    return len(rows)


def upsert_user(conn: sqlite3.Connection, steamid: str, **fields) -> None:
    """Targeted upsert for the `users` row: updates ONLY the given columns, never
    wiping others (owned/level/summary passes each set different columns). Unlike
    INSERT OR REPLACE which replaces the whole row."""
    cols = ["steamid"] + list(fields.keys())
    vals = [steamid] + list(fields.values())
    ph = ",".join("?" * len(cols))
    sets = ",".join(f"{c}=excluded.{c}" for c in fields)
    conn.execute("BEGIN;")
    try:
        conn.execute(f"INSERT INTO users({','.join(cols)}) VALUES({ph}) "
                     f"ON CONFLICT(steamid) DO UPDATE SET {sets}", vals)
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;"); raise


def counts(conn: sqlite3.Connection) -> dict:
    out = {}
    for t in ("users", "owned", "recently", "wishlist", "followed", "friends",
              "user_groups", "achievements", "achievement_rarity", "reviews",
              "games", "game_live", "steamspy"):
        out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return out


if __name__ == "__main__":
    # smoke + budget-gate proof
    import tempfile, os
    p = Path(tempfile.gettempdir()) / "steam_db_smoke.db"
    if p.exists():
        os.remove(p)
    c = connect(p)
    print("tables:", [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
    seed_today(c, 12_000)
    print("seeded today spent:", spent_today(c))
    ok = sum(reserve(c, 1, limit=12_005) for _ in range(10))  # only 5 should pass
    print(f"reserve 10 with 5 left -> {ok} granted (expect 5); spent now {spent_today(c)} (expect 12005)")
    upsert_many(c, "owned", ["steamid", "appid", "playtime_forever", "playtime_2weeks"],
                [("76561198000000000", 440, 1234.0, 10.0)])
    print("counts:", counts(c))
    c.close(); os.remove(p)
