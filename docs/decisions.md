# Decisions register

> type: overview · status: active · updated: 2026-07-13

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

## Open (needs the user)
- **P6 go / timing** — the pool is large enough (≈ 6,700 panel-eligible). Start the pre-registered P6
  confirmation now, or keep crawling toward a larger target first?
- **Panel target** — is ≈ 6,700 the working size, or hold P6 until a specific N (e.g. 10k)?

## Standing constraints
- No Gemini metered spend during autonomous runs.
- No destructive git (no `reset --hard` / force-push / DB deletion).
- Never commit `data_collection/steam.db`, `.env`, or crawl exports (Steam ToU / secrets).
