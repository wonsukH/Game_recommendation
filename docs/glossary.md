# Glossary

> type: overview · status: active · updated: 2026-07-13

Current-stack terms. Numbers live in [results](results.md); methodology in [evaluation](evaluation.md).

## Models & signals
- **Co-play CF** — item-item collaborative filtering: games are "similar" if the same users play
  both, weighted by playtime. The project's validated core engine.
- **EASE** — Embarrassingly Shallow Auto-Encoder: a closed-form (Woodbury) linear item-item model
  with L2 penalty λ. The corrected P4 serving pick (λ ≈ 100).
- **`condcos` / `userknn` / `knnpd03`** — sweep candidates: conditional-cosine (old production
  baseline, worst), user-kNN, and popularity-discounted kNN (a discovery knob, not a winner).
- **Mult-DAE** — a denoising-autoencoder neural CF; lost to EASE in this small/sparse regime.
- **`pvalue` / `pctl_game`** — preference-target definitions: playtime-value vs per-game engagement
  percentile. Statistically indistinguishable on the primary metric.
- **Moat** — a defensible advantage: here, personalized-from-history recommendations that a generic
  LLM-with-library cannot match.

## Evaluation
- **Graded NDCG@20** — the in-cohort primary metric; graded relevance = per-game engagement
  percentile over held-out co-play labels.
- **Circularity (ρ)** — the in-cohort target correlates ρ ≈ 0.958 with the preference scores, so it
  partly measures "reproduce the playtime percentile." See [evaluation](evaluation.md).
- **Wishlist recall** — the target-independent metric (wishlists carry no playtime provenance); the
  arbiter for headline claims.
- **Panel** — the user cohorts: train ≈ 1,133 / dev 200 / private-holdout 150.
- **Paired bootstrap / BH-FDR** — the significance machinery: paired bootstrap CIs, Benjamini–Hochberg
  false-discovery-rate correction across the sweep.
- **Cutoff bug** — a `score <= 0: break` that truncated EASE's negative-scoring tail and flipped the
  ranker verdict until fixed ([results](results.md)).

## Crawl
- **`depth = -1`** — the tag for the unbiased random-sampled OOD (out-of-distribution) user pool.
- **Snowball** — the legacy friend-graph crawl expansion; disabled in random mode (introduces bias).
- **Public screening** — batched `GetPlayerSummaries` filtering to `communityvisibilitystate == 3`
  before a full crawl.
