# Game Recommendation — wiki

> type: index · status: active · updated: 2026-07-22

Project knowledge base (English). **Read only the depth you need**: this index (Tier 0) → a Tier-1
overview → its Tier-2 detail. The agent's behavioral code is in [`../CLAUDE.md`](../CLAUDE.md). The
Korean append-only logs under `experiments/` are evidence, not translated.

## Start here
- **New to the project?** [architecture](architecture.md) → [results](results.md) → [status](status.md).
- **Picking up autonomous work?** [status](status.md) → [decisions](decisions.md) → [roadmap](roadmap.md).

## Tier 1 — overviews (one screen each)
| Page | What it answers |
|---|---|
| [architecture](architecture.md) | System shape + the pivot (behavioral CF vs the retired vibe stack) |
| [data-layer](data-layer.md) | `steam.db` schema + crawler design / cost / budget |
| [evaluation](evaluation.md) | Metrics, the circularity caveat, statistics, panels |
| [results](results.md) | **Current truth (P4+P6+demo)** — the canonical headline numbers |
| [roadmap](roadmap.md) | Durable phases P4–P9 |
| [status](status.md) | Live crawl, counts, current phase |
| [decisions](decisions.md) | What's settled vs still open |
| [glossary](glossary.md) | Current-stack terms |
| [operations](operations.md) | Run / restart the crawl, budget, safety rules |
| [portfolio-headlines](portfolio-headlines.md) | Approved recruiter-facing framings (dual notation) |

## Conventions
- [STYLEGUIDE](STYLEGUIDE.md) — doc format, the density tiers, and the `check_doc_format.py` gate.
- **Single source of truth**: canonical numbers live once ([results](results.md) for experiments,
  [status](status.md) for live counts); every other page cross-links.

## Evidence & history (Tier-2 detail)
- [`../experiments/INDEX.md`](../experiments/INDEX.md) — the per-experiment index: every comparison
  and where its log/report lives (the deep detail behind [results](results.md)).
- [`../experiments/p4_sweep/`](../experiments/p4_sweep/) — the P4 sweep: `JOURNAL.md`,
  `LEADERBOARD.md`, `P6_PREREG.md` (Korean, append-only evidence).
- [`../experiments/DELIBERATION_LOG.md`](../experiments/DELIBERATION_LOG.md) — the reasoning log (Korean).
- [archive/](archive/) — retired old-stack docs (review-CSV / FE-pipeline / Streamlit vibe app), kept as history.
