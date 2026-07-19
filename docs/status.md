# Status — live

> type: overview · status: active · updated: 2026-07-20

Live project state. Counts are a **snapshot** (regenerate from `data_collection/steam.db` with a
read-only connection — see [operations](operations.md)). Durable phase plan: [roadmap](roadmap.md).
Confirmed results: [results](results.md).

## Crawl (as of 2026-07-20)
- Mode: unbiased random SteamID64 sampling, achievements OFF, no snowball ([data-layer](data-layer.md)).
- Healthy since the 2026-07-18 restart (a ~3-day outage 07-15→07-18 — no OS scheduler by user
  decision, watchdog only runs inside sessions). P5/P6 use frozen extractions, so outages never
  affect results.

## Data on hand (snapshot, 2026-07-20 read — the `outputs/p5` build substrate)
| Cohort | Count |
|---|---|
| Usable users (`public=1 AND complete=1`) | 23,347 |
| — **unbiased OOD** (`user_queue.depth = -1`) | **20,282** |
| — legacy biased (snowball/CSV, `depth ≥ 0`) | ~3,065 |
| Played interactions / pool games | 1.24M / 41,266 |

P6-frozen strata (07-14 snapshot; immutable): confirm 1,000 (consumed) / reserve 500 (untouched) /
exploration 1,936 / light 1,252. Cohort-shift signal: unbiased library median 8 games, 41% have a
wishlist (biased: 97%).

## Current phase
- **P5 builder rewire: DONE (2026-07-20, commit 4171a7e).** The app serves the P6-confirmed
  **EASE(λ100) × pctl_game** from a gate-validated sparse-B artifact (K=2048; truncation loss
  −0.0027 within the −0.005 tolerance, top-20 Jaccard 0.966); catalog artifacts all steam.db-native
  (tags 34.8k games, SteamSpy quality 34.7k, fresh unbiased popularity from 20.3k OOD users);
  **zero runtime CSV**; serving-side score≤0 cutoffs removed (T35-bug class, 3 sites). Smoke
  (LLM-bypassed real app path) PASS; pytest 39 green. Bonus: serving-combo sanity resolved —
  **pctl×EASE beats pvalue×EASE +0.0104 SIG** (exploration pool). Detail: JOURNAL T53.
- **P6 OOD confirmation: DONE (2026-07-14)** — serving = EASE both axes, pref = pctl_game,
  knnpd03 dropped ([results](results.md)). Exploration track E1–E6 + absolute judge: DONE
  (JOURNAL T47–T52).
- **Next: P8** — full end-to-end with the LLM router (user-attended; Gemini spend) + serving
  polish. Backlog: cold-start/new-release surface (two-tower niche), real-human portfolio demo,
  Gemini κ judge cross-check.
- Decisions register: [decisions](decisions.md).
