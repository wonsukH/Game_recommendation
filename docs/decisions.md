# Decisions register

> type: overview · status: active · updated: 2026-07-14

Decisions that shape the project — what's settled (so we don't re-litigate) and what's still open
(needs the user). Rationale for the settled ones lives in the Korean reasoning log
([`experiments/DELIBERATION_LOG.md`](../experiments/DELIBERATION_LOG.md)); outcomes in
[results](results.md).

## Settled
| Decision | Resolution | Pointer |
|---|---|---|
| Product framing | Personalized-from-history recommender; **retire** the anonymous / vibe / tag-similarity stack (it lost to an LLM-with-library baseline) | [results](results.md), [architecture](architecture.md) |
| Data source | Behavioral SQLite store (ownership + playtime + wishlist), replacing the review-CSV source | [data-layer](data-layer.md) |
| Serving ranker | **EASE** (λ ≈ 100) as the P4 shortlist pick | [results](results.md) |
| Preference signal | Aggregate playtime-weighting; finer signals (per-game percentile, individual achievements) did not earn their keep | [results](results.md) |
| Crawl strategy | Unbiased random SteamID sampling, achievements OFF, no snowball | [data-layer](data-layer.md) |
| Crawl persistence | Session watchdog only — **no Windows Scheduled Task** (user declined) | [operations](operations.md) |
| Docs & language | English reference docs (this wiki + CLAUDE.md); **user-facing chat stays Korean**; Korean evidence logs stay Korean | `../CLAUDE.md` |
| P6 go + panel (2026-07-14) | **Start now** on the frozen OOD pool; confirmation panel **N = 1,000** + 500-user quarantined reserve; one-shot run only after V1–V6 + user sign-off on a dry-run leaderboard; games-metadata catch-up (~1k calls) before the freeze | [`P6_PREREG.md`](../experiments/p4_sweep/P6_PREREG.md) amendment v3, [status](status.md) |
| P6 exploration scope (2026-07-14) | E1 cohort-shift, E2 unbiased popularity/propensity, E3 light-user descriptives, E4 saturation curve — exploration pool only; **E5** (EASE fine-tune + fusion) conditional on H1; wishlist-as-input and social co-play **rejected** (metric-B contamination risk; 13 in-cohort friend edges = measured dead) | [status](status.md) |
| Agent delegation scope (2026-07-14) | Design/reasoning subagents only for **explicitly original** work; constraint-bound assembly (execution planning from fixed specs/preregs) is done directly | `../CLAUDE.md` |

## Open (needs the user)
- **Dry-run sign-off** — the P6 one-shot confirmation waits on the user reviewing the exploration-pool
  dry-run leaderboard (gate recorded in [`P6_PREREG.md`](../experiments/p4_sweep/P6_PREREG.md) v3).
- **Crawl stop point** — decided by E4's saturation curve once it runs.

## Standing constraints
- No Gemini metered spend during autonomous runs.
- No destructive git (no `reset --hard` / force-push / DB deletion).
- Never commit `data_collection/steam.db`, `.env`, or crawl exports (Steam ToU / secrets).
