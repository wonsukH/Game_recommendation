# Roadmap

> type: roadmap · status: active · updated: 2026-07-22

The data layer pivoted from review-CSV to a behavioral SQLite store (`steam.db`). That forces a
re-wire of the recommender's inputs, the "liked" definition, the quality signals, and the whole
evaluation. The **CF moat is unchanged** (playtime-weighted item-item co-play) — these phases
rewire everything around it.

- Order: **crawl (ongoing) → P4 (gate) → P6 (OOD confirmation) → P5 → P7 → P8; P9 continuous.**
- P6 runs **before** P5: the one-shot OOD confirmation fixes the serving-ranker choice, and the
  builder rewire is committed around that verdict.
- Each phase gets its own detailed plan when it starts.
- Headline numbers: [results](results.md). Methodology: [evaluation](evaluation.md).

## Phases

- **P4 — Behavioral "liked" / preference definition (gate, done first).**
  - Redefine "liked" from playtime, user-relative (ratio/percentile) to resist cohort bias.
  - Pick the serving ranker.
  - *Done when:* a pre-registered check shows a behavioral-liked ranker reproduces or beats the
    old baseline.
  - **Shortlisting is complete** — outcome → [results](results.md).

- **P6 — Confirmation on the unbiased OOD pool. DONE (2026-07-14).**
  - The pre-registered one-shot confirmation ran on the frozen 1,000-user random-cohort panel.
  - **H1 confirmed — serving = EASE** (wins both the primary and the target-independent wishlist axis).
  - Preference = `pctl_game`. `knnpd03(β.3)` dropped per the registered falsification.
  - Verdicts → [results](results.md); method → [evaluation](evaluation.md).
  - Remaining under this phase: exploration track E1–E4, including the saturation curve that fixes
    the crawl stop point → [status](status.md).

- **P5 — Builder rewire (CSV → steam.db) + artifact regeneration. DONE (2026-07-20).**
  - The serving app now runs the confirmed **EASE(λ100) × pctl_game** from a gate-validated
    sparse-B artifact.
  - Tags/quality/popularity/constraints/titles all rebuilt steam.db-native.
  - **Zero runtime CSV** — the done-when condition.
  - Build procedure → [operations](operations.md) §7; record → JOURNAL T53 (local evidence);
    stack → [architecture](architecture.md).

- **P7 — Recommendation-quality levers (rescoped 2026-07-22; optional).**
  Bundles the remaining quality levers, including the two-tower cold-start niche, under one
  optional phase:
  - **(a) Session recency.** The only genuinely untested residue of the original learned-weight scope.
    - The P4 learned blend (JOURNAL T12) searched playtime + completion + pvalue only — it never
      saw a recency signal.
    - Achievement-derived recency (D-family, JOURNAL T8) froze at ns, and achievement crawling is
      retired, so that path is closed.
    - Steam's `rtime_last_played` (a `GetOwnedGames` field, already crawled into
      `owned.rtime_last_played` — see [data-layer](data-layer.md) — but with zero use downstream
      as a feature) has no achievement dependency. It could stand in as a third input to the
      learned-blend search.
    - Expected null; cheap pre-registered one-shot.
  - **(b) Cold-start / new-release surface.** Two-tower's only confirmed niche.
    - Cold-item recall 0.01–0.02 where EASE is structurally 0 (pre-registered P3 directional,
      E4×E6 — [results](results.md)).
    - This is a **capability gap** (games with no co-play can never surface through EASE), not an
      accuracy lever.
    - Absorbs the former standalone "cold-start/new-release" backlog item.
  - **(c) Series/edition dedup on library-route output (user-flagged 2026-07-22).**
    - Co-play alone cannot tell whether two titles are effectively the same game line
      (improved edition / remaster / sequel) or genuinely different.
    - So a user playing the improved version can get its predecessor recommended.
    - The seed route's franchise exclusion (`_series_prefix`) does not cover the library route.
    - Candidate mitigation: exclude recommendations whose series prefix matches an owned game.
      Known over-filtering risk (same-series games that ARE different); needs its own check.
  - Honesty note: the largest *proven* quality lever remains data scale (E4: the EASE curve is
    still rising — [results](results.md)). That lever lives in **P9**, not P7.
  - *Done when:* each sub-lever gets its own pre-registered comparison when picked up; a null keeps
    the current stack. Depends on P5–6.

- **P8 — Serving update. DONE (2026-07-22).**
  - Full e2e with the real Gemini router — 7/7 route cases PASS.
    - The model odyssey resolved to `gemini-3-flash-preview`.
    - The KRW price-constraint chain was fixed and verified.
  - Real-human demo on 5 consented accounts (author + friends); the N=1 self-rating aligns with
    the judge instrument.
  - Seed-route tag gate shipped from live feedback, plus an availability filter (delisted titles
    never surface).
  - Gemini cross-judge κ 0.49/0.58 reproduces EASE ≈ ceiling.
  - Records: JOURNAL T54–T58 and the `docs/portfolio-headlines.md` demo section (both local evidence).

- **P9 — Continuous / monitoring (always-on).**
  - Crawl to target.
  - Periodically re-run P5–6 on accumulated data.
  - Commit + push at each pillar. Ongoing.

Where we are now → [status](status.md).
