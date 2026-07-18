# Status — live

> type: overview · status: active · updated: 2026-07-18

Live project state. Counts are a **snapshot** (regenerate from `data_collection/steam.db` with a
read-only connection — see [operations](operations.md)). Durable phase plan: [roadmap](roadmap.md).
Confirmed results: [results](results.md).

## Crawl (as of 2026-07-18 14:17 KST / 05:17 UTC)
- Mode: unbiased random SteamID64 sampling, achievements OFF, no snowball ([data-layer](data-layer.md)).
- **Restarted 2026-07-18 05:16 UTC** after a ~3-day outage (process died ~2026-07-15 00:29 UTC; no
  OS scheduler by user decision, and no session was running the watchdog). Writes confirmed resumed.
- P6 used a **one-time frozen extraction** (`outputs/p6/`), so the outage and the restart have zero
  effect on any P6 result (prereg amendment A8).

## Data on hand (snapshot, 2026-07-18 read)
| Cohort | Count |
|---|---|
| Usable users (`public=1 AND complete=1`) | 17,852 |
| — **unbiased OOD** (`user_queue.depth = -1`) | **14,795** |
| — legacy biased (snowball/CSV, `depth ≥ 0`) | ~3,052 |
| `depth = -1` queue pending | ≈5.1k (self-refilling from random draws) |

P6-frozen strata (from the 07-14 snapshot; unchanged by later crawling): confirm 1,000 (consumed) /
reserve 500 (untouched) / exploration 1,936 / light 1,252 — eligibility ≈3,416 of the then-9,742
OOD users. Cohort-shift signal: unbiased library median 8 games, 41% have a wishlist (biased: 97%).

## Current phase
- **P6 OOD confirmation: DONE (2026-07-14).** One-shot run on the frozen 1,000-user unbiased panel:
  **H1 confirmed (serving = EASE λ≈100, wins both axes), preference = pctl_game, knnpd03(β.3)
  dropped** — full verdict table: [results](results.md). Gauntlet V1–V6 green; user-signed dry-run.
- **Exploration track: DONE (2026-07-14)** — E1 cohort-shift (τ 0.822, shrink 18–30%),
  E2 unbiased popularity (`pop_unbiased.json` for P5), E3 light users (EASE holds), E4×E6 scaling
  (keep crawling; two-tower: no crossover), E5 challengers (EASE defends all; why-EASE tests
  T-a/T-b confirmed), absolute-rubric judge (EASE 44.5% High vs random 6.5%). One-liners →
  [results](results.md); detail → JOURNAL T47–T49.
- **Next: P5** — builder rewire around the confirmed `EASE(λ100)` + `pctl_game` + unbiased
  popularity prior; sanity-check `pctl×EASE` on the exploration pool during the build.
- Decisions register: [decisions](decisions.md).
