# Roadmap

> type: roadmap · status: active · updated: 2026-07-13

The data layer pivoted from review-CSV to a behavioral SQLite store (`steam.db`), which forces a
re-wire of the recommender's inputs, the "liked" definition, the quality signals, and the whole
evaluation. The **CF moat is unchanged** (playtime-weighted item-item co-play); these phases rewire
everything around it. Order: **crawl (ongoing) → P4 (gate) → P5 → P6 → P7 → P8; P9 continuous.**
Each phase gets its own detailed plan when it starts. Headline numbers live in [results](results.md);
methodology in [evaluation](evaluation.md).

## Phases
- **P4 — Behavioral "liked" / preference definition (gate, done first).** Redefine "liked" from
  playtime, user-relative (ratio/percentile) to resist cohort bias, and pick the serving ranker.
  *Done when:* a pre-registered check shows a behavioral-liked ranker reproduces or beats the old
  baseline. **Shortlisting is complete** — outcome → [results](results.md).

- **P5 — Builder rewire (CSV → steam.db) + artifact regeneration.** Rebuild co-play/CF, tag
  vocab/matrix, popularity, the quality gate, titles, and catalog metadata directly from `steam.db`;
  the catalog pool grows with the crawl.
  *Done when:* serving artifacts are regenerated from `steam.db` with no runtime CSV. Depends on P4.

- **P6 — Confirmation on rich data + OOD bias.** Re-bench the P4 shortlist on the **unbiased random
  OOD pool** with wishlist recall as co-primary; quantify cohort bias vs the old snowball pool and a
  saturation curve that fixes the crawl stop point.
  *Done when:* the pre-registered confirmation runs on the OOD pool
  ([`P6_PREREG.md`](../experiments/p4_sweep/P6_PREREG.md)). Confirmation → [results](results.md);
  method → [evaluation](evaluation.md). Depends on P5. **Ready to start.**

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
