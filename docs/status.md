# Status — live

> type: overview · status: active · updated: 2026-07-14

Live project state. Counts are a **snapshot** (regenerate from `data_collection/steam.db` with a
read-only connection — see [operations](operations.md)). Durable phase plan: [roadmap](roadmap.md).
Confirmed results: [results](results.md).

## Crawl (as of 2026-07-14 03:15 KST / 07-13 18:15 UTC)
- Mode: unbiased random SteamID64 sampling, achievements OFF, no snowball ([data-layer](data-layer.md)).
- Last DB write 2026-07-13 17:45 UTC; the `depth = -1` queue is nearly drained (≈2.7k pending) —
  the crawler keeps drawing fresh random IDs when the queue empties.
- P6 uses a **one-time frozen extraction** (`outputs/p6/`), so continued crawling cannot affect the
  running confirmation (prereg amendment A8).

## Data on hand (snapshot, 2026-07-14 read)
| Cohort | Count |
|---|---|
| Usable users (`public=1 AND complete=1`) | 12,794 |
| — **unbiased OOD** (`user_queue.depth = -1`, crawled 07-07→) | **9,742** |
| — legacy biased (snowball/CSV, `depth ≥ 0`) | 3,052 |
| OOD **panel-eligible** (≥12 *effective played* items per `build_relevance` — not raw owned) | **≈3,416** |
| OOD metric-B eligible (≥3 dated non-owned wishlist adds) | 1,971 (≈58% of eligible) |
| OOD light users (5–11 effective items) | 1,316 |
| `owned` rows / distinct games | ≈1.71M / 43,598 |

Cohort-shift signal (what P6 measures): unbiased library median 8 games, only 41% have a wishlist —
vs 97% in the old snowball cohort. Note: an earlier "≈6,700 panel-eligible" figure mixed cohorts and
counted raw-owned ≥12; the canonical eligibility is the ≈3,416 above.

## Current phase
- **P4 shortlisting: done** (in-cohort + fresh n = 854) — serving pick is EASE; see [results](results.md).
- **P6: IN PROGRESS (started 2026-07-14).** Pre-registration amended (v3: EASE slots, panel
  N = 1,000 + 500 reserve, fixed FDR family m = 8, frozen operational definitions) and approved —
  canonical protocol: [`P6_PREREG.md`](../experiments/p4_sweep/P6_PREREG.md). Gate: verification
  gauntlet V1–V6 + user sign-off on a dry-run leaderboard **before** the one-shot confirmation run.
- Exploration track (firewalled from the confirmation panel): E1 cohort-shift quantification,
  E2 unbiased popularity/propensity re-estimation, E3 light-user descriptives, E4 saturation curve
  (fixes the crawl stop point). E5 (EASE fine-tune + fusion) only if H1 confirms.
- Decisions register: [decisions](decisions.md).
