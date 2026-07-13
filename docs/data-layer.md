# Data layer

> type: overview · status: active · updated: 2026-07-13

The recommender's data lives in **one SQLite file, `data_collection/steam.db`** (~2 GB), built by a
budget-capped Steam crawler. It captures **behavior** — ownership, playtime, wishlist, friends — because
the project pivoted off the old review-CSV source: co-play CF needs who-plays-what signal, not review text.
For live counts and the current step see [status](status.md); to run or restart the crawl see
[operations](operations.md); per-experiment detail lives in `experiments/`.

## The store

- **`data_collection/steam.db`** — SQLite in **WAL mode** (`PRAGMA journal_mode=WAL`), `synchronous=NORMAL`,
  60 s busy-timeout. Autocommit connection; every write is a small explicit transaction. Schema
  (`db.SCHEMA`) is idempotent (`CREATE TABLE IF NOT EXISTS`) and applied on every `db.connect()`, so the
  crawler is crash-safe and resumable via SQLite cursors + upserts.
- **NEVER commit** `steam.db`, `.env`, or any crawl export. End-user data is local-only (Steam Web API
  ToU); secrets stay out of git. All are already gitignored.
- **18 tables** in three groups (below), keyed on `steamid`/`appid` stored as INTEGER (64-bit, lossless).

## Key tables

**Users & behavior** — the recommendation signal:
- `users`(steamid, public, level, xp, xp_needed, complete, fetched_at) — one row per crawled account;
  `public=1 AND complete=1` is the usable cohort.
- `owned`(steamid, appid, playtime_forever, playtime_2weeks, per-platform playtimes, rtime_last_played,
  has_stats, …) — the core co-play matrix. `recently`, `wishlist`(priority, date_added),
  `followed`, `friends`(friend_steamid, friend_since), `user_groups`, `badges` round out engagement.

**Games (metadata dimension)** — fetched once per distinct owned appid:
- `games` (appdetails: name/type/genres/price/metacritic/release/…), `steamspy` (owners/reviews/tags),
  `game_stat` (per-game stat schema), `game_live` (official live concurrent players).

**Crawl control (operational):**
- `user_queue`(seq, steamid, depth, added_at) — growing crawl queue; `seq` AUTOINCREMENT preserves enqueue
  order (not steamid, which would bias toward old/private accounts). `budget`(day, calls) — the daily gate.
  `crawl_state`(key, pos, done) — resume cursors.

**Achievements — UNUSED (disabled):** `game_achievement`, `player_game_ach`, `user_achievement` (interned
`ach_id` design). Achievement crawling is turned off (`--no-achievements`); aggregate completion was a weak
signal not worth ~25x the per-user cost (P4-ext finding). Tables remain but are not populated by new crawls.

## Crawler (`crawl_unified.py`)

Current mode = **unbiased random SteamID64 sampling** for an out-of-distribution panel:
- Draw random accountIDs, `STEAMID_BASE = 76561197960265728` + `randint(1, random_max)`, skipping IDs
  already in `users`.
- **Batched public screening** via `GetPlayerSummaries` (100 IDs/call) — keep only
  `communityvisibilitystate == 3` (public). Cheap pre-filter before the expensive per-user calls.
- **Achievements OFF** (`--no-achievements`) and **no snowball** in random mode (friends are not enqueued —
  avoids reintroducing cohort bias). The random/OOD pool is tagged **`depth = -1`** in `user_queue`.
- Per public user (achievements off) it fetches: GetOwnedGames (game names come free via
  `include_appinfo=1`), Recently, Friends, Wishlist, Followed, Groups, Badges. `complete=1` is stamped last
  (atomic; resume re-runs idempotently). Wall-clock AIMD pacing + a circuit breaker handle throttling.

## Cost & yield

- **Random-ID funnel** (measured, in code): of random SteamIDs ≈81% exist, ≈79% are public, and ≈11% of
  public expose game details → **≈9% crawlable**.
- **Per acquired public+complete user:** ≈7 API calls in the current no-achievements mode (the seven calls
  above), plus a small amortized share of one `GetPlayerSummaries` screening call (100 IDs/call). With
  achievements enabled it was much higher (one extra call per played game).

## Budget gate

- **Cap: `DAILY_LIMIT = 90_000` Steam API calls per UTC-day** (10k margin under Steam's 100k/day hard cap).
- Every HTTP request must first win `db.reserve()` — an atomic `BEGIN IMMEDIATE` increment of `budget(day)`
  *before* the call (failed calls counted too), so the calendar-day total can never exceed the cap even with
  parallel writers.
- **Reset: 00:00 UTC (09:00 KST)** — the day key is `today_utc()` = `datetime.now(timezone.utc)` formatted
  `%Y-%m-%d`, rolling over at UTC midnight.
- `BudgetExhausted` (cap hit) and `Throttled` (persistent HTTP 429) stop work gracefully — the crawler
  pauses and resumes; nothing is corrupted and no user is falsely marked private.

## See also

- [status](status.md) — live counts, pool sizes, current step (canonical for changing numbers).
- [operations](operations.md) — start/restart, watchdog, budget, safety rules.
- `data_collection/db.py` — schema + budget gate · `data_collection/crawl_unified.py` — crawler phases/CLI.
