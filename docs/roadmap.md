# Roadmap

> type: roadmap · status: active · updated: 2026-07-14

The data layer pivoted from review-CSV to a behavioral SQLite store (`steam.db`), which forces a
re-wire of the recommender's inputs, the "liked" definition, the quality signals, and the whole
evaluation. The **CF moat is unchanged** (playtime-weighted item-item co-play); these phases rewire
everything around it. Order: **crawl (ongoing) → P4 (gate) → P6 (OOD confirmation) → P5 → P7 → P8;
P9 continuous.** P6 runs **before** P5: the one-shot OOD confirmation fixes the serving-ranker
choice, and the builder rewire is committed around that verdict. Each phase gets its own detailed
plan when it starts. Headline numbers live in [results](results.md); methodology in
[evaluation](evaluation.md).

## Phases
- **P4 — Behavioral "liked" / preference definition (gate, done first).** Redefine "liked" from
  playtime, user-relative (ratio/percentile) to resist cohort bias, and pick the serving ranker.
  *Done when:* a pre-registered check shows a behavioral-liked ranker reproduces or beats the old
  baseline. **Shortlisting is complete** — outcome → [results](results.md).

- **P6 — Confirmation on the unbiased OOD pool. DONE (2026-07-14).** The pre-registered one-shot
  confirmation ran on the frozen 1,000-user random-cohort panel: **H1 confirmed — serving = EASE**
  (wins both the primary and the target-independent wishlist axis); preference = `pctl_game`;
  `knnpd03(β.3)` dropped per the registered falsification. Verdicts → [results](results.md);
  method → [evaluation](evaluation.md). Remaining under this phase: exploration track E1–E4
  (incl. the saturation curve that fixes the crawl stop point) → [status](status.md).

- **P5 — Builder rewire (CSV → steam.db) + artifact regeneration. DONE (2026-07-20).** The
  serving app now runs the confirmed **EASE(λ100) × pctl_game** from a gate-validated sparse-B
  artifact; tags/quality/popularity/constraints/titles all rebuilt steam.db-native; **zero runtime
  CSV** (the done-when condition). Build procedure → [operations](operations.md) §7; record →
  JOURNAL T53; stack → [architecture](architecture.md).

- **P7 — Preference-weighted learned model (optional; likely a null).** Learn
  `w_p = f(playtime, completion, recency)` versus the fixed log weight. **Note:** the achievement
  path this phase was originally meant to cash in has been **retired** — P4 found aggregate completion
  suffices and individual achievements don't beat it, and achievement crawling is off
  ([results](results.md)). So P7 is now an optional refinement without rarity features.
  *Done when:* the pre-registered comparison lands; keep the fixed weight if the learned model loses
  (P4 already points that way — a valid null). Depends on P5–6.

- **P8 — Serving update.** Repoint the serving graph to the regenerated artifacts and the new quality
  gate / catalog sources.
  *Done when:* all serving routes pass end-to-end and tests are green. Depends on P5(–7).

- **P9 — Continuous / monitoring (always-on).** Crawl to target; periodically re-run P5–6 on
  accumulated data; commit + push at each pillar. Ongoing.

Where we are now → [status](status.md).
