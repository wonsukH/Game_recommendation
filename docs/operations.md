# Operations runbook

> type: runbook · status: active · updated: 2026-07-22

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

**Mode in one line:** unbiased random-SteamID64 sampling, achievements OFF, **no snowball**
(random mode implies no friend enqueue), OOD pool tagged `depth=-1` in `user_queue`.

- Fully resumable — just re-run the `.bat`. It picks up from the SQLite cursors and re-runs
  idempotently.
- Output → `data_collection/steam.db`; logs → `data_collection/crawl_daily.log`.

## 2. Watchdog (self-heal within a session)

```
scripts/crawl_watchdog.ps1
```

Checks for a running `python … crawl_unified` process; if none, it relaunches `daily_crawl.bat`
(hidden window) and appends to `data_collection/crawl_watchdog.log`. This recovers from crashes and
throttle-deaths.

**There is intentionally NO Windows Scheduled Task** — the user declined it. The watchdog only runs when
something (a Claude session) is invoking it; it is **not** OS-scheduled. Do not create a Scheduled Task.

## 3. API budget

- **Cap: 90,000 Steam API calls per UTC-day** (`db.DAILY_LIMIT = 90_000`; 10k margin below Steam's
  100k/day hard cap).
  - Every HTTP request must first win `db.reserve()` — an atomic `BEGIN IMMEDIATE` increment
    *before* the call. Failed calls are counted too.
  - So the calendar-day total can never exceed the cap, even with parallel workers.
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

WAL mode lets a read-only connection run concurrently with the live writer without blocking it. For a
**fresh** status read, open read-only **without** `immutable=1`:

```
sqlite3.connect("file:data_collection/steam.db?mode=ro", uri=True)
```

⚠️ **Do not use `immutable=1` for live status** — it tells SQLite the file never changes, so it ignores
the WAL and returns a **stale snapshot** (it will under-report a crawl that is actively writing).
`immutable=1` is only for a DB you know is quiescent.

Prefer **simple `COUNT(*)`** probes (e.g. `SELECT COUNT(*) FROM users WHERE public=1 AND complete=1`).
The queue/work-list helpers (`pending_users`, `next_pending_users`, `next_games_to_fetch`) use `LEFT JOIN`s
that are slow on the live DB — avoid heavy JOINs for a quick status check.

## 6. Hard safety rules

- **Never commit** `data_collection/steam.db`, `.env`, or any crawl export (Steam Web API ToU — end-user
  data is local-only; secrets stay out of git). All are already gitignored.
- `serving/data/ease/graph_users.json` contains raw SteamID64s of the 12k EASE graph users →
  **gitignored as of 2026-07-22**.
  - It was briefly git-tracked 2026-07-20 → 07-22 in a public repo; now untracked, and the repo
    history was purged.
  - Rule: no user-identifiable artifact ever gets tracked under `serving/data/`. The serving app
    only needs the aggregate count from `meta.json`.
- The same 2026-07-22 sweep (`git grep` for the SteamID64 prefix over all tracked files) found raw
  SteamIDs in **evidence JSONs too**:
  - `experiments/**/panels.json` / `p6_panels.json` — 1,483 + 4,688 IDs.
  - `experiments/**/judge/**/unblind*.json` — 12–20 IDs each, mapping panel users to their
    recommendation cases.
  - All were **untracked + gitignored 2026-07-22**. The files stay local, so evidence is preserved.
    (Since the same day's repo cleanup, the whole `experiments/` tree is local-only anyway.)
  - General rule: **derived artifacts and evidence files carrying user identifiers are local-only.**
    Before committing any builder/experiment output, check it for SteamIDs
    (`git grep -E "7656119[0-9]{10}"` — code constants like `STEAMID_BASE` are the only
    legitimate hits).
- **No destructive git** (no force-push / hard reset of others' work).
- Do not stop a running crawl/build unless the user explicitly asks.

## 7. Rebuild the serving artifacts (P5 pipeline)

Run in order after meaningful crawl growth (all read steam.db; the app just restarts on new files):

```
python -m pipeline.game_rec.data.behavioral_extract --out outputs/p5   # snapshot (~8 min)
python -m pipeline.game_rec.data.build_ease_artifact                   # EASE fit + sparse B (~5 min)
python -m pipeline.orchestration.p5_validate                           # gates: truncation/pref/weights
python -m pipeline.game_rec.data.build_catalog_db --pop outputs/p5/pop_unbiased.json
python -m pipeline.orchestration.p5_smoke                              # LLM-bypassed app-path smoke
```

- `build_ease_artifact` defaults: `--cap 12000 --topk 2048 --lam 100` — **top-K was gate-chosen**
  (512/-0.0183 FAIL → 1024/-0.0089 FAIL → 2048/-0.0027 PASS vs tolerance -0.005); don't lower K
  without re-running `p5_validate`. The 345MB `B_topk.npz` is gitignored — rebuild locally.
- Refresh the unbiased popularity prior first if the OOD cohort has grown (see JOURNAL T53 —
  ownership rates over `user_queue.depth=-1` users → `outputs/p5/pop_unbiased.json`).
- Full app run (`streamlit run serving/main_agent.py`) needs `GEMINI_API_KEY` — user-attended only.

## See also

- [status](status.md) — live counts, pool sizes, current step (canonical for changing numbers).
- [roadmap](roadmap.md) — durable phase plan · [decisions](decisions.md) — settled vs open.
- `data_collection/crawl_unified.py` — crawler CLI and phase logic · `data_collection/db.py` — schema + budget gate.
