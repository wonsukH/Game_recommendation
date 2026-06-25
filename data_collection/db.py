"""Unified SQLite store for all crawled Steam preference/quality data + a
bulletproof daily API-call budget.

Design (see plan: 최종 SQLite 스키마):
- **Lossless**: every signal field is captured. steamid/gid stored as INTEGER (64-bit,
  < 2^63 → lossless, ~3x smaller than TEXT). Achievements are INTERNED: the huge
  per-(user,achievement) fact table stores a compact integer `ach_id`, while the
  achievement's appid/apiname/name/condition/rarity live ONCE in the `game_achievement`
  dimension. Full reconstruction via joins (no info lost).
- **Two-phase by cost** (timing efficiency): per-user facts (users phase) vs per-game
  constants fetched once per game (games phase) vs per-game reviews (reviews phase).
- **Crash-safe / resumable / incremental**: WAL, idempotent upserts, a growing user
  queue (CSV bootstrap + friend snowball), per-game "visited" markers.
- **End-user data is LOCAL only** and gitignored (Steam Web API ToU — never publish).

Daily budget (the hard guarantee): every API call must first win `reserve()`, which in a
single `BEGIN IMMEDIATE` transaction checks today's counter and atomically increments it
BEFORE the HTTP call. If the increment would exceed the day's limit it returns False and
the caller stops. BEGIN IMMEDIATE serializes writers, so even with parallel
workers/processes the calendar-day total can NEVER exceed the limit (failed calls count
too, as Steam counts them). Default 90,000 < Steam's 100,000/day hard cap (10k margin).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "data_collection" / "steam.db"
DAILY_LIMIT = 90_000          # < 100k Steam hard cap
_UTC = timezone.utc

SCHEMA = """
-- ===== operational =====
CREATE TABLE IF NOT EXISTS budget(day TEXT PRIMARY KEY, calls INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS crawl_state(
  key TEXT PRIMARY KEY, pos INTEGER NOT NULL DEFAULT 0, done INTEGER NOT NULL DEFAULT 0);
-- growing user crawl queue: CSV bootstrap (depth 0) + friend snowball (depth+1).
-- seq = explicit insertion order (NOT steamid): if steamid were the INTEGER PRIMARY KEY
-- it would alias rowid, and ORDER BY rowid would crawl ascending steamid = oldest/most-
-- private accounts first (biased). seq AUTOINCREMENT preserves enqueue order instead.
CREATE TABLE IF NOT EXISTS user_queue(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, steamid INTEGER UNIQUE,
  depth INTEGER NOT NULL DEFAULT 0, added_at TEXT);

-- ===== Phase 1: users (facts) =====
-- anonymous key + engagement only. NO identity/locale (country/persona).
CREATE TABLE IF NOT EXISTS users(
  steamid INTEGER PRIMARY KEY, public INTEGER, level INTEGER, xp INTEGER,
  xp_needed INTEGER, complete INTEGER NOT NULL DEFAULT 0, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS owned(
  steamid INTEGER, appid INTEGER, playtime_forever REAL, playtime_2weeks REAL,
  playtime_windows REAL, playtime_mac REAL, playtime_linux REAL, playtime_deck REAL,
  playtime_disconnected REAL, rtime_last_played INTEGER,
  has_stats INTEGER, has_leaderboards INTEGER, img_icon_url TEXT,
  PRIMARY KEY(steamid, appid));
CREATE TABLE IF NOT EXISTS recently(
  steamid INTEGER, appid INTEGER, playtime_2weeks REAL, PRIMARY KEY(steamid, appid));
CREATE TABLE IF NOT EXISTS wishlist(
  steamid INTEGER, appid INTEGER, priority INTEGER, date_added INTEGER,
  PRIMARY KEY(steamid, appid));
CREATE TABLE IF NOT EXISTS followed(
  steamid INTEGER, appid INTEGER, PRIMARY KEY(steamid, appid));
CREATE TABLE IF NOT EXISTS friends(
  steamid INTEGER, friend_steamid INTEGER, friend_since INTEGER,
  PRIMARY KEY(steamid, friend_steamid));
CREATE TABLE IF NOT EXISTS user_groups(
  steamid INTEGER, gid INTEGER, PRIMARY KEY(steamid, gid));
CREATE TABLE IF NOT EXISTS badges(           -- per-game engagement / scarcity
  steamid INTEGER, badgeid INTEGER, appid INTEGER NOT NULL DEFAULT 0, level INTEGER,
  completion_time INTEGER, xp INTEGER, scarcity INTEGER, border_color INTEGER,
  PRIMARY KEY(steamid, badgeid, appid));
CREATE TABLE IF NOT EXISTS player_game_ach(  -- per (user,game) achievement CHECK summary
  steamid INTEGER, appid INTEGER, unlocked INTEGER, total INTEGER, checked_at TEXT,
  PRIMARY KEY(steamid, appid));              -- keeps "played but 0 unlocked" (unlocked=0)
CREATE TABLE IF NOT EXISTS user_achievement( -- which specific achievements UNLOCKED (+when)
  steamid INTEGER, ach_id INTEGER, unlocktime INTEGER, PRIMARY KEY(steamid, ach_id));

-- ===== Phase 2: games (dimension) =====
-- one row per distinct achievement; id↔name/condition/rarity mapping lives here ONCE.
CREATE TABLE IF NOT EXISTS game_achievement(
  ach_id INTEGER PRIMARY KEY AUTOINCREMENT, appid INTEGER, apiname TEXT,
  display_name TEXT, description TEXT, hidden INTEGER, icon TEXT, icongray TEXT,
  global_pct REAL, schema_at TEXT, UNIQUE(appid, apiname));
CREATE TABLE IF NOT EXISTS game_stat(        -- custom per-game stats schema (free w/ schema)
  appid INTEGER, name TEXT, display_name TEXT, default_value REAL,
  PRIMARY KEY(appid, name));
CREATE TABLE IF NOT EXISTS games(            -- appdetails; fetched_at = games-phase visited marker
  appid INTEGER PRIMARY KEY, name TEXT, type TEXT, required_age INTEGER, is_free INTEGER,
  controller_support TEXT, dlc_json TEXT, short_description TEXT, detailed_description TEXT,
  about_the_game TEXT, supported_languages TEXT, developers TEXT, publishers TEXT,
  win INTEGER, mac INTEGER, linux INTEGER, price_final INTEGER, price_initial INTEGER,
  price_discount INTEGER, price_currency TEXT, metacritic_score INTEGER, metacritic_url TEXT,
  categories_json TEXT, genres_json TEXT, recommendations_total INTEGER,
  achievements_total INTEGER, release_date TEXT, coming_soon INTEGER, header_image TEXT,
  content_descriptors_json TEXT, website TEXT, support_url TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS steamspy(
  appid INTEGER PRIMARY KEY, name TEXT, developer TEXT, publisher TEXT, score_rank TEXT,
  positive INTEGER, negative INTEGER, userscore INTEGER, owners TEXT,
  average_forever INTEGER, average_2weeks INTEGER, median_forever INTEGER,
  median_2weeks INTEGER, price INTEGER, initialprice INTEGER, discount INTEGER,
  ccu INTEGER, languages TEXT, genre TEXT, tags_json TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS game_live(        -- official live concurrent players
  appid INTEGER PRIMARY KEY, player_count INTEGER, fetched_at TEXT);

-- ===== indexes =====
CREATE INDEX IF NOT EXISTS ix_owned_appid    ON owned(appid);
CREATE INDEX IF NOT EXISTS ix_recently_appid ON recently(appid);
CREATE INDEX IF NOT EXISTS ix_uach_ach       ON user_achievement(ach_id);
CREATE INDEX IF NOT EXISTS ix_pga_appid      ON player_game_ach(appid);
CREATE INDEX IF NOT EXISTS ix_badges_appid   ON badges(appid);
CREATE INDEX IF NOT EXISTS ix_friends_friend ON friends(friend_steamid);
CREATE INDEX IF NOT EXISTS ix_uq_pending     ON user_queue(depth);
"""

ALL_TABLES = ("users", "owned", "recently", "wishlist", "followed", "friends",
              "user_groups", "badges", "player_game_ach", "user_achievement",
              "game_achievement", "game_stat", "games", "steamspy", "game_live",
              "user_queue")


def today_utc() -> str:
    return datetime.now(_UTC).strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(_UTC).isoformat(timespec="seconds")


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=60, isolation_level=None)  # autocommit; we manage txns
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.execute("PRAGMA foreign_keys=OFF;")
    conn.executescript(SCHEMA)
    return conn


# ---------------- bulletproof daily budget ----------------
class BudgetExhausted(Exception):
    pass


def seed_today(conn: sqlite3.Connection, already_spent: int, day: str | None = None) -> None:
    """Initialize today's counter to `already_spent` (quota used earlier outside this
    store). Only raises the counter, never lowers it."""
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


def insert_ignore(conn: sqlite3.Connection, table: str, cols: list[str], rows: list[tuple]) -> int:
    """INSERT OR IGNORE (keep existing rows untouched). Used to seed games(appid,name)
    early from owned without clobbering a fuller games-phase row."""
    if not rows:
        return 0
    ph = ",".join("?" * len(cols))
    conn.execute("BEGIN;")
    try:
        conn.executemany(f"INSERT OR IGNORE INTO {table}({','.join(cols)}) VALUES({ph})", rows)
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;"); raise
    return len(rows)


def upsert_cols(conn: sqlite3.Connection, table: str, pk: list[str], row: dict) -> None:
    """Targeted upsert: insert/update ONLY the given columns, never wiping others
    (different passes set different columns of games/users). ON CONFLICT on `pk`."""
    cols = list(row.keys())
    vals = [row[c] for c in cols]
    ph = ",".join("?" * len(cols))
    upd = ",".join(f"{c}=excluded.{c}" for c in cols if c not in pk)
    conn.execute("BEGIN;")
    try:
        conn.execute(
            f"INSERT INTO {table}({','.join(cols)}) VALUES({ph}) "
            f"ON CONFLICT({','.join(pk)}) DO UPDATE SET {upd}", vals)
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;"); raise


def upsert_user(conn: sqlite3.Connection, steamid: int, **fields) -> None:
    """Targeted upsert for a `users` row (preserves columns set by other passes)."""
    upsert_cols(conn, "users", ["steamid"], {"steamid": int(steamid), **fields})


# ---------------- achievement interning ----------------
def intern_achievements(conn: sqlite3.Connection, appid: int, apinames) -> dict:
    """Ensure (appid, apiname) rows exist in game_achievement (names stay NULL until the
    games phase fills them) and return {apiname: ach_id}. Lets the users phase store
    user_achievement with a compact integer ach_id instead of repeating the apiname."""
    appid = int(appid)
    apinames = list(apinames)
    if apinames:
        conn.execute("BEGIN;")
        try:
            conn.executemany("INSERT OR IGNORE INTO game_achievement(appid, apiname) VALUES(?,?)",
                             [(appid, n) for n in apinames])
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;"); raise
    rows = conn.execute("SELECT apiname, ach_id FROM game_achievement WHERE appid=?",
                        (appid,)).fetchall()
    return {r[0]: r[1] for r in rows}


def upsert_achievement_schema(conn: sqlite3.Connection, appid: int, achs: list[dict]) -> int:
    """games phase: write achievement names/conditions (GetSchemaForGame). Creates the
    (appid, apiname) row if a user never unlocked it; fills display_name/description/etc."""
    if not achs:
        return 0
    appid = int(appid)
    ts = now_iso()
    rows = [(appid, a.get("name"), a.get("displayName"), a.get("description"),
             int(bool(a.get("hidden", 0))), a.get("icon"), a.get("icongray"), ts)
            for a in achs if a.get("name")]
    conn.execute("BEGIN;")
    try:
        conn.executemany(
            "INSERT INTO game_achievement"
            "(appid, apiname, display_name, description, hidden, icon, icongray, schema_at) "
            "VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(appid, apiname) DO UPDATE SET display_name=excluded.display_name, "
            "description=excluded.description, hidden=excluded.hidden, icon=excluded.icon, "
            "icongray=excluded.icongray, schema_at=excluded.schema_at", rows)
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;"); raise
    return len(rows)


def upsert_global_pct(conn: sqlite3.Connection, appid: int, pcts: list[tuple]) -> int:
    """games phase: write per-achievement global unlock % (rarity). pcts=[(apiname, pct)]."""
    if not pcts:
        return 0
    appid = int(appid)
    conn.execute("BEGIN;")
    try:
        conn.executemany("INSERT OR IGNORE INTO game_achievement(appid, apiname) VALUES(?,?)",
                         [(appid, n) for n, _ in pcts])
        conn.executemany("UPDATE game_achievement SET global_pct=? WHERE appid=? AND apiname=?",
                         [(float(p), appid, n) for n, p in pcts])
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;"); raise
    return len(pcts)


# ---------------- user queue (bootstrap + snowball) ----------------
def enqueue_users(conn: sqlite3.Connection, steamids, depth: int = 0) -> int:
    """Add steamids to the crawl queue (idempotent). depth = snowball distance."""
    rows = []
    for s in steamids:
        try:
            rows.append((int(s), depth))
        except (TypeError, ValueError):
            continue
    if not rows:
        return 0
    ts = now_iso()
    conn.execute("BEGIN;")
    try:
        conn.executemany("INSERT OR IGNORE INTO user_queue(steamid, depth, added_at) VALUES(?,?,?)",
                         [(s, d, ts) for s, d in rows])
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;"); raise
    return len(rows)


def next_pending_users(conn: sqlite3.Connection, limit: int) -> list[int]:
    """Next batch of queued steamids not yet fully crawled (complete!=1), BFS order
    (shallowest snowball depth first, then insertion order)."""
    rows = conn.execute(
        "SELECT q.steamid FROM user_queue q "
        "LEFT JOIN users u ON u.steamid = q.steamid "
        "WHERE u.complete IS NULL OR u.complete = 0 "
        "ORDER BY q.depth, q.seq LIMIT ?", (int(limit),)).fetchall()
    return [int(r[0]) for r in rows]


def queue_depth_of(conn: sqlite3.Connection, steamid: int) -> int:
    row = conn.execute("SELECT depth FROM user_queue WHERE steamid=?", (int(steamid),)).fetchone()
    return int(row[0]) if row else 0


# ---------------- games / reviews phase work lists ----------------
def next_games_to_fetch(conn: sqlite3.Connection, limit: int) -> list[int]:
    """Distinct owned appids not yet visited by the games phase (games.fetched_at NULL)."""
    rows = conn.execute(
        "SELECT o.appid FROM (SELECT DISTINCT appid FROM owned) o "
        "LEFT JOIN games g ON g.appid = o.appid "
        "WHERE g.fetched_at IS NULL ORDER BY o.appid LIMIT ?", (int(limit),)).fetchall()
    return [int(r[0]) for r in rows]


# ---------------- per-game "already have it" guards (games-phase resume) ----------------
def has_schema(conn: sqlite3.Connection, appid: int) -> bool:
    return conn.execute("SELECT 1 FROM game_achievement WHERE appid=? AND schema_at IS NOT NULL LIMIT 1",
                        (int(appid),)).fetchone() is not None


def has_global_pct(conn: sqlite3.Connection, appid: int) -> bool:
    return conn.execute("SELECT 1 FROM game_achievement WHERE appid=? AND global_pct IS NOT NULL LIMIT 1",
                        (int(appid),)).fetchone() is not None


def has_steamspy(conn: sqlite3.Connection, appid: int) -> bool:
    return conn.execute("SELECT 1 FROM steamspy WHERE appid=? AND fetched_at IS NOT NULL LIMIT 1",
                        (int(appid),)).fetchone() is not None


def has_live(conn: sqlite3.Connection, appid: int) -> bool:
    return conn.execute("SELECT 1 FROM game_live WHERE appid=? LIMIT 1",
                        (int(appid),)).fetchone() is not None


# ---------------- reporting ----------------
def counts(conn: sqlite3.Connection) -> dict:
    out = {}
    for t in ALL_TABLES:
        out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return out


def pending_users(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM user_queue q LEFT JOIN users u ON u.steamid=q.steamid "
        "WHERE u.complete IS NULL OR u.complete=0").fetchone()[0]


if __name__ == "__main__":
    # smoke + budget-gate + interning proof
    import os
    import tempfile
    p = Path(tempfile.gettempdir()) / "steam_db_smoke.db"
    if p.exists():
        os.remove(p)
    c = connect(p)
    tabs = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("tables:", tabs)
    # budget gate
    seed_today(c, 12_000)
    ok = sum(reserve(c, 1, limit=12_005) for _ in range(10))
    print(f"reserve 10 w/ 5 left -> {ok} granted (expect 5); spent={spent_today(c)} (expect 12005)")
    # interning
    upsert_many(c, "owned", ["steamid", "appid", "playtime_forever"], [(76561198000000000, 440, 1234.0)])
    m = intern_achievements(c, 440, ["ACH_A", "ACH_B"])
    print("interned:", m)
    upsert_many(c, "user_achievement", ["steamid", "ach_id", "unlocktime"],
                [(76561198000000000, m["ACH_A"], 1700000000)])
    upsert_achievement_schema(c, 440, [{"name": "ACH_A", "displayName": "First Blood",
                                        "description": "Win a round", "hidden": 0}])
    upsert_global_pct(c, 440, [("ACH_A", 1.3)])
    row = c.execute(
        "SELECT u.steamid, ga.appid, ga.apiname, ga.display_name, ga.description, ga.global_pct, u.unlocktime "
        "FROM user_achievement u JOIN game_achievement ga ON ga.ach_id=u.ach_id").fetchone()
    print("lossless join:", row)
    print("counts:", counts(c))
    c.close(); os.remove(p)
