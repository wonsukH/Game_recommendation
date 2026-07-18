# Decisions register

> type: overview · status: active · updated: 2026-07-17

Decisions that shape the project — what's settled (so we don't re-litigate) and what's still open
(needs the user). Rationale for the settled ones lives in the Korean reasoning log
([`experiments/DELIBERATION_LOG.md`](../experiments/DELIBERATION_LOG.md)); outcomes in
[results](results.md).

## Settled
| Decision | Resolution | Pointer |
|---|---|---|
| Product framing | Personalized-from-history recommender; **retire** the anonymous / vibe / tag-similarity stack (it lost to an LLM-with-library baseline) | [results](results.md), [architecture](architecture.md) |
| Data source | Behavioral SQLite store (ownership + playtime + wishlist), replacing the review-CSV source | [data-layer](data-layer.md) |
| Serving ranker | **EASE** (λ ≈ 100) — P4 shortlist pick **confirmed by P6 OOD one-shot (2026-07-14)**, wins both axes | [results](results.md) |
| Preference signal | **`pctl_game`** (simplest; P6: ns vs pvalue on wishlist, marginally better on NDCG); aggregate playtime-weighting suffices | [results](results.md) |
| Discovery knob | `knnpd03` (β = 0.3) **dropped** per registered falsification (OOD wishlist ns + SIG accuracy harm); β = 0.2 borderline but dominated by EASE — nothing ships | [results](results.md) |
| Crawl strategy | Unbiased random SteamID sampling, achievements OFF, no snowball | [data-layer](data-layer.md) |
| Crawl persistence | Session watchdog only — **no Windows Scheduled Task** (user declined) | [operations](operations.md) |
| Docs & language | English reference docs (this wiki + CLAUDE.md); **user-facing chat stays Korean**; Korean evidence logs stay Korean | `../CLAUDE.md` |
| P6 go + panel (2026-07-14) | **Start now** on the frozen OOD pool; confirmation panel **N = 1,000** + 500-user quarantined reserve; one-shot run only after V1–V6 + user sign-off on a dry-run leaderboard; games-metadata catch-up (~1k calls) before the freeze | [`P6_PREREG.md`](../experiments/p4_sweep/P6_PREREG.md) amendment v3, [status](status.md) |
| P6 exploration scope (2026-07-14) | E1 cohort-shift, E2 unbiased popularity/propensity, E3 light-user descriptives, E4 saturation curve — exploration pool only; **E5** (EASE fine-tune + fusion) conditional on H1; wishlist-as-input and social co-play **rejected** (metric-B contamination risk; 13 in-cohort friend edges = measured dead) | [status](status.md) |
| Agent delegation scope (2026-07-14) | Design/reasoning subagents only for **explicitly original** work; constraint-bound assembly (execution planning from fixed specs/preregs) is done directly | `../CLAUDE.md` |
| Absolute-result presentation (2026-07-15) | **Dual notation**: headline framings must be arithmetic derivations of recorded raw values (raw preserved alongside; caveats attached); **no post-hoc metric changes** to prettify results | [results](results.md), [portfolio-headlines](portfolio-headlines.md) |

## Open (needs the user)
- **Crawl stop point** — E4's curve is still rising (0.233→0.298 over the graph ladder, decelerating)
  ⇒ **keep crawling**; re-measure at the P9 periodic re-eval and stop when the slope flattens.

## Standing constraints
- No Gemini metered spend during autonomous runs.
- No destructive git (no `reset --hard` / force-push / DB deletion).
- Never commit `data_collection/steam.db`, `.env`, or crawl exports (Steam ToU / secrets).
