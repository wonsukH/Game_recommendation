# Results — P4 current truth

> type: experiment-report · status: active · updated: 2026-07-13

**This page is the single source of truth for headline numbers.** Other pages cross-link here
instead of restating figures. Methodology and the circularity caveat: [evaluation](evaluation.md).
Evidence (Korean, append-only): [`experiments/p4_sweep/JOURNAL.md`](../experiments/p4_sweep/JOURNAL.md),
[`experiments/p4_sweep/LEADERBOARD.md`](../experiments/p4_sweep/LEADERBOARD.md).

## Bottom line
- **Validated core (the moat)**: playtime-weighted **item-item co-play CF** beats "give an LLM my
  library" on *personalization*, and is ≈ EASE. On an *anonymous / vibe* framing the LLM wins — so
  the old tag-similarity / vibe stack is **retired**. The value is scoped to personalized-from-history.
- **Serving ranker pick (P4 shortlist)**: **EASE** (closed-form linear item model, λ ≈ 100). After a
  bug fix it beats `userknn` by **+0.062** on the primary metric (SIG; dev + fresh, n = 854). The old
  production baseline `condcos` is the **worst** of the shortlist.
- **Preference definition**: playtime-value (`pvalue`) and per-game percentile (`pctl_game`) are
  **statistically indistinguishable** on the primary metric — aggregate playtime-weighting suffices;
  no finer preference signal earned its keep.
- **Everything learned/neural lost or tied** (see table). The corrected winner is the *simplest*
  linear model.

## The cutoff bug (why the ranker verdict flipped)
The ranker's `recommend` had `if score <= 0: break`, which truncated EASE's (legitimately
negative-scoring) tail — so EASE looked worst and `userknn` looked best. Only EASE was affected (MF
has no such break). Fixed → EASE is the winner (+0.062 SIG, above). This is the canonical example of
why conclusions get an adversarial re-check before they ship.

## The circularity caveat (why we don't trust in-cohort NDCG alone)
The in-cohort graded-NDCG target shares provenance with the playtime-derived preference scores:
per-game Spearman **ρ ≈ 0.958**. So in-cohort NDCG largely measures "reproduce the playtime
percentile," not independent quality. **The target-independent metric is held-out wishlist recall.**
Every claim below that matters is (or will be, at P6) confirmed on wishlist. Full argument:
[evaluation](evaluation.md).

## What was tested (all vs EASE unless noted)
| Candidate | Primary (in-cohort) | Independent (wishlist) | Verdict |
|---|---|---|---|
| **EASE** (λ≈100) | **best** shortlist | — | **serving pick** |
| `userknn` | −0.062 vs EASE (SIG) | — | beaten |
| `condcos` (old prod) | worst | — | retired |
| `knnpd03` (pop-discounted kNN, "S0") | NDCG ns; recall −0.011 (SIG loss) | **+0.0073 (SIG)** | **discovery knob, not an accuracy win** |
| MF family (ALS / BPR / NMF) | lose | — | dropped |
| Informed-negative BPR | −0.0514 (SIG) | — | dropped |
| DL — Mult-DAE neural CF | −0.1497 (SIG) | — | dropped (small/sparse favors linear) |
| Learned reranker (blend) | ns | ns | dropped |
| Achievement neural reranker | ns | +0.0059 (borderline ns) | dropped |
| Individual achievements | — | story +0.0024 (ns) best; rarity slightly neg | **aggregate completion suffices** |
| rarity E-family · intent ε-tier · R5 combos | ns / lose | — | dropped |

**`knnpd03` is a discovery/serendipity knob, not a ranker winner** — it loses accuracy in-cohort but
surfaces more wishlist-relevant discovery. Kept as an optional steering lever, not the default ranker.

## Status
P4 shortlisting is **done** (in-cohort + fresh n = 854). The pre-registered **confirmation is P6**
([`P6_PREREG.md`](../experiments/p4_sweep/P6_PREREG.md), v2, wishlist as co-primary) run on the
**unbiased random OOD pool** (`depth = -1`). Live progress: [status](status.md). What comes after:
[roadmap](roadmap.md).
