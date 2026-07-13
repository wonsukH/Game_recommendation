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
- **P6 OOD confirmation: DONE (2026-07-14).** One-shot run on the frozen 1,000-user unbiased panel:
  **H1 confirmed (serving = EASE λ≈100, wins both axes), preference = pctl_game, knnpd03(β.3)
  dropped** — full verdict table: [results](results.md). Gauntlet V1–V6 green; user-signed dry-run.
- **Next: P5** (builder rewire around EASE) after the exploration track lands.
- Exploration track in progress (firewalled from confirm/reserve panels): E1 cohort-shift,
  E2 unbiased popularity/propensity, E3 light-user descriptives, E4 saturation curve (crawl stop
  point). E5 (EASE fine-grid + fusion) unlocked by H1 — exploration pool + mini-prereg + reserve
  if a winner emerges. Plus the absolute-rubric judge (9-2).
- Decisions register: [decisions](decisions.md).
