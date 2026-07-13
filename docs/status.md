# Status — live

> type: overview · status: active · updated: 2026-07-13

Live project state. Counts are a **snapshot** (regenerate from `data_collection/steam.db` with a
read-only connection — see [operations](operations.md)). Durable phase plan: [roadmap](roadmap.md).
Confirmed results: [results](results.md).

## Crawl (as of 2026-07-13 06:42 UTC)
- **Healthy and live** — the crawler is actively writing (a live DB read showed the newest user
  timestamped to the current second). Two `python.exe` workers running; no restart needed.
- Mode: unbiased random SteamID64 sampling, achievements OFF, no snowball ([data-layer](data-layer.md)).
- **Budget today**: ≈ 19.6k / 90k Steam API calls (UTC-day; resets 00:00 UTC / 09:00 KST).

## Data on hand (snapshot)
| Cohort | Count |
|---|---|
| Crawled public profiles with games | ≈ 11,430 |
| Panel-eligible (≥ 12 owned games) | ≈ 6,700 |
| With a wishlist (independent-metric eligible) | ≈ 6,400 |
| Queue backlog — unbiased OOD (`depth = -1`) | ≈ 87,700 pending |
| Queue backlog — legacy snowball (`depth 0/1`) | present, de-prioritized |

Panel-eligible and wishlist cohorts have roughly doubled since the switch to unbiased random
crawling — the pool is now large enough to run the P6 confirmation.

## Current phase
- **P4 shortlisting: done** (in-cohort + fresh n = 854) — serving pick is EASE; see [results](results.md).
- **Next: P6** — pre-registered confirmation on the unbiased OOD pool with wishlist as co-primary
  ([`P6_PREREG.md`](../experiments/p4_sweep/P6_PREREG.md)). Ready to start.
- Open choices: [decisions](decisions.md).
