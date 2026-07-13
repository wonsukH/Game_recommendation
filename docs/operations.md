# Operations runbook

> type: runbook · status: active · updated: 2026-07-13

Day-to-day runbook for the live Steam crawl. Answer-first; each section is a task you can do now.
Live counts and the current step are **not** here — see [status](status.md).

## 1. Start / restart the crawl

Run the one launcher:

```
scripts/daily_crawl.bat
```

It invokes (verified against the .bat and `crawl_unified.py`):

```
python -m data_collection.crawl_unified \
  --forever --limit 90000 --target 1.0 --no-achievements \
  --user-source random --users-chunk 100
```

- `--forever` — run continuously across UTC-days (sleeps and resumes; never a one-shot).
- `--limit 90000` — daily API-call cap (see §3).
- `--target 1.0` — wall-clock pacing interval in seconds between call *starts* (AIMD adapts it; it is **not** a completion target).
- `--no-achievements` — skip per-game `GetPlayerAchievements` (~96% of per-user cost) → ~25x more users/day.
- `--user-source random` — unbiased random-accountID sampling (batched public screening via `GetPlayerSummaries`), the OOD/P6 panel.
- `--users-chunk 100` — users processed per phase turn (overrides the CLI default of 20).

**Mode in one line:** unbiased random-SteamID64 sampling, achievements OFF, **no snowball** (random mode
implies no friend enqueue), OOD pool tagged `depth=-1` in `user_queue`. Fully resumable — just re-run the
`.bat`; it picks up from the SQLite cursors and re-runs idempotently. Output → `data_collection/steam.db`;
logs → `data_collection/crawl_daily.log`.

## 2. Watchdog (self-heal within a session)

```
scripts/crawl_watchdog.ps1
```

Checks for a running `python … crawl_unified` process; if none, it relaunches `daily_crawl.bat`
(hidden window) and appends to `data_collection/crawl_watchdog.log`. This recovers from crashes and
throttle-deaths.

**There is intentionally NO Windows Scheduled Task** — the user declined it. The watchdog only runs when
something (a Claude session) is invoking it; it is **not** OS-scheduled. Do not create a Scheduled Task.
(The script's own header comment still says "Registered as a Windows Scheduled Task" — that comment is
stale; disregard it.)

## 3. API budget

- **Cap: 90,000 Steam API calls per UTC-day** (`db.DAILY_LIMIT = 90_000`; 10k margin below Steam's
  100k/day hard cap). Every HTTP request must first win `db.reserve()` (atomic `BEGIN IMMEDIATE`
  increment *before* the call, failed calls counted too) — so the calendar-day total can never exceed
  the cap even with parallel workers.
- **Reset: 00:00 UTC (09:00 KST).** The day key is `datetime.now(timezone.utc)` formatted `%Y-%m-%d`,
  so the counter rolls over at UTC midnight.

When the budget is exhausted the crawler pauses (sleeps `--loop-sleep`, default 3600s) and resumes after
the reset — no action needed.

## 4. API key

- `STEAM_API_KEY` lives in `.env` at the repo root (32 hex chars), loaded via `load_dotenv`.
- If it is missing the crawler logs `STEAM_API_KEY not set` and exits.
- If it is present but invalid, requests come back non-200 (HTTP 401) and are dropped as failures
  (`status_code != 200 → return None`): the crawl keeps spending budget but completes ~zero users.
  Symptom = calls climbing while the usable-user count stays flat.
- **Never print, log, or commit the key.**

## 5. Reading crawl status from the DB safely

The live writer holds the WAL. For status queries, open a **read-only / `immutable=1`** connection so a
status read never contends for the write lock:

```
sqlite3.connect("file:data_collection/steam.db?immutable=1", uri=True)
```

Prefer **simple `COUNT(*)`** probes (e.g. `SELECT COUNT(*) FROM users WHERE public=1 AND complete=1`).
The queue/work-list helpers (`pending_users`, `next_pending_users`, `next_games_to_fetch`) use `LEFT JOIN`s
that are slow on the live DB — avoid heavy JOINs for a quick status check.

## 6. Hard safety rules

- **Never commit** `data_collection/steam.db`, `.env`, or any crawl export (Steam Web API ToU — end-user
  data is local-only; secrets stay out of git). All are already gitignored.
- **No destructive git** (no force-push / hard reset of others' work).
- Do not stop a running crawl/build unless the user explicitly asks.

## See also

- [status](status.md) — live counts, pool sizes, current step (canonical for changing numbers).
- [ROADMAP.md](ROADMAP.md) — phase status and handoff.
- `data_collection/crawl_unified.py` — crawler CLI and phase logic · `data_collection/db.py` — schema + budget gate.
