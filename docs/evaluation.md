# Evaluation methodology

> type: overview · status: active · updated: 2026-07-22

How the recommender is judged, and the one caveat that governs every headline claim.
Actual confirmed numbers live in **[results](results.md)** (single source of truth) — this page
describes the *method*, not the figures.

## Primary metric (co-primary A)

**Graded NDCG@20 over held-out co-play labels.**

- For each panel user, positive-relevance items are split 70/30 into profile / holdout.
  The split is common per-user and paired across all candidates.
- The ranker sees the profile and is scored on how highly it ranks the holdout.
- **Graded relevance** = each held-out game's *per-game engagement percentile*:
  `max(playtime-percentile-within-game, completion-percentile-within-game)`.
  - Completion-aware and self-adapting — no per-genre branching needed.
  - Code: `build_relevance` / `graded_ndcg` in `pipeline/orchestration/preference_sweep.py`.
- The labels are non-circular *in construction* (held-out co-play, not tag- or LLM-derived).
  But see the caveat below.

## THE CIRCULARITY CAVEAT (read this first)

The in-cohort graded-NDCG **target shares provenance with the playtime-derived preference /
percentile scores it is meant to validate.**

- Measured per-game Spearman ρ(preference score `s`, relevance target) ≈ **0.958**
  (both `pvalue` and `pctl_game`; audit: `pipeline/orchestration/audit_verify.py`).
- At that correlation the target is a near-monotone copy of the preference score.
  So **in-cohort NDCG largely measures "reproduce the playtime percentile," not independent
  recommendation quality.**
- Every same-target axis (SNIPS, masked-engagement, LLM-judge, fresh-panel NDCG) reuses this
  target, so none of them can rebut the circularity.

**The target-independent metric is held-out wishlist recall@20 (co-primary B).**

- Wishlists carry no playtime provenance.
- Input = the user's played profile. Target = most-recent in-pool, **non-owned** wishlist adds
  (`pipeline/orchestration/wishlist_axis.py`).
- Time-ordering guards leakage. Wishlist is eval-only — never an input.
- **Any headline claim must be confirmed on wishlist recall.** The circular axis alone is
  insufficient. See **[results](results.md)** for the confirmed values.

## Statistics

- **Paired bootstrap CIs** on the per-user difference between two variants.
  - Same users, aligned; CI excluding 0 ⇒ significant.
  - `paired_bootstrap_diff` / `bootstrap_ci`, B = 1000, 95%, fixed seed.
- **Benjamini–Hochberg FDR** across the family of headline paired comparisons in the sweep.
  - Wilcoxon signed-rank per pair, then BH correction (`pipeline/orchestration/audit_fdr.py`).
  - The sweep has many cells, so raw per-pair significance is corrected.
- **Pre-registration**: hypotheses, fixed eval slots, and metrics are registered *before* seeing
  OOD data.
  - Register: `experiments/p4_sweep/P6_PREREG.md` (local evidence; append-only after registration).
- **Explicit null / negative reporting**:
  - A `random_support` anchor rides every round as a metric health check — if it ranks near real
    candidates, the metric is broken.
  - Nulls and non-significant results are reported plainly rather than dropped.

## Panels / splits

- Users are split **once** into frozen panels and reused every round (leave-panel-out):
  **train ≈ 1,133 / dev 200 / private-holdout 150**.
  - Eligibility = ≥12 positive-relevance items.
  - `get_panels`, defaults dev_n = 200, priv_n = 150; train is the remaining eligible users.
    The count is observed on the current cohort — verify against `experiments/p4_sweep/panels.json`
    (local evidence).
- **Co-play graphs are built on TRAIN users only**, so dev/private are pure generalization.
- Every round also carries the ORACLE (holdout itself) and POP anchors alongside the random null.
- Supporting (non-decision) metrics: recall@20, SNIPS-debiased recall, long-tail recall.
  Overlap / coverage / Gini serve as distinctiveness screening — not quality.

## Evidence (Korean, append-only — do not translate; local only, not in the public repo)

- `experiments/p4_sweep/JOURNAL.md` — per-round sweep log (circularity quantified, panel freeze).
- `experiments/DELIBERATION_LOG.md` — the reasoning narrative behind these choices.
