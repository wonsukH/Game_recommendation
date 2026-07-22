# Decisions register

> type: overview · status: active · updated: 2026-07-22

Decisions that shape the project. Settled ones are listed so we don't re-litigate them; open ones
need the user. Rationale for the settled ones lives in the Korean reasoning log
(`experiments/DELIBERATION_LOG.md`, local evidence — not in the public repo). Outcomes live in
[results](results.md).

## Settled

- **Product framing** — a personalized-from-history recommender.
  - The anonymous / vibe / tag-similarity stack is **retired**: it lost to an LLM-with-library baseline.
  - See [results](results.md), [architecture](architecture.md).

- **Data source** — behavioral SQLite store (ownership + playtime + wishlist).
  - Replaces the review-CSV source. See [data-layer](data-layer.md).

- **Serving ranker** — **EASE** (λ ≈ 100).
  - P4 shortlist pick, **confirmed by the P6 OOD one-shot (2026-07-14)**. Wins both axes.
  - See [results](results.md).

- **Preference signal** — **`pctl_game`** (the simplest candidate).
  - P6: ns vs `pvalue` on wishlist, marginally better on NDCG.
  - Aggregate playtime-weighting suffices. See [results](results.md).

- **Discovery knob** — `knnpd03` (β = 0.3) **dropped**, per the registered falsification.
  - OOD wishlist edge collapsed (ns) and it significantly harms accuracy.
  - β = 0.2 kept a borderline edge but is dominated by EASE on both axes. Nothing ships.
  - See [results](results.md).

- **Crawl strategy** — unbiased random SteamID sampling.
  - Achievements OFF. No snowball. See [data-layer](data-layer.md).

- **Crawl persistence** — session watchdog only.
  - **No Windows Scheduled Task** (user declined). See [operations](operations.md).

- **Docs & language** — reference docs (this wiki + CLAUDE.md) are English.
  - **User-facing chat stays Korean.** Korean evidence logs stay Korean.
  - See `../CLAUDE.md`.

- **P6 go + panel** (2026-07-14) — start now on the frozen OOD pool.
  - Confirmation panel **N = 1,000**, plus a 500-user quarantined reserve.
  - One-shot run only after checks V1–V6 and user sign-off on a dry-run leaderboard.
  - Games-metadata catch-up (~1k calls) before the freeze.
  - Registered in `experiments/p4_sweep/P6_PREREG.md` amendment v3 (local evidence). See [status](status.md).

- **P6 exploration scope** (2026-07-14) — exploration pool only.
  - Ran: E1 cohort-shift, E2 unbiased popularity/propensity, E3 light-user descriptives, E4 saturation curve.
  - **E5** (EASE fine-tune + fusion) conditional on H1.
  - **Rejected**: wishlist-as-input (metric-B contamination risk) and social co-play (13 in-cohort friend edges = measured dead).
  - See [status](status.md).

- **Agent delegation scope** (2026-07-14) — design/reasoning subagents only for **explicitly original** work.
  - Constraint-bound assembly (execution planning from fixed specs/preregs) is done directly.
  - See `../CLAUDE.md`.

- **Absolute-result presentation** (2026-07-15) — **dual notation**.
  - Headline framings must be arithmetic derivations of recorded raw values.
  - The raw value is preserved alongside; caveats stay attached.
  - **No post-hoc metric changes** to prettify results.
  - See [results](results.md); recruiter-facing copy in `docs/portfolio-headlines.md` (local only).

- **P5 scope + serving artifact** (2026-07-20) — full serving swap (user-chosen).
  - Steering kept, with DB-rebuilt tags. Cold-start surface → backlog.
  - EASE persisted as **sparse top-K B, K = 2048** — gate-chosen via the measured ladder
    (512 and 1024 FAIL, 2048 PASS at −0.0027; the ladder extension was user-approved).
  - Serving preference = `pctl_game` via per-game playtime-ECDF interpolation.
  - See [operations](operations.md) §7; JOURNAL T53 (local evidence).

## Open (needs the user)

- **Crawl stop point** — E4's curve is still rising (0.233 → 0.298 over the graph ladder, decelerating).
  - ⇒ **Keep crawling.** Re-measure at the P9 periodic re-eval; stop when the slope flattens.

## Standing constraints

- No Gemini metered spend during autonomous runs.
- No destructive git (no `reset --hard` / force-push / DB deletion).
- Never commit `data_collection/steam.db`, `.env`, or crawl exports (Steam ToU / secrets).
