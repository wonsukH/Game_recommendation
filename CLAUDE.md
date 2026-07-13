# CLAUDE.md — Game Recommendation

Personalized Steam game recommender. The validated core is **playtime-weighted item-item co-play
CF** — a proven, scoped moat (beats "give an LLM my library" on personalization; ≈ EASE; loses on
anonymous/vibe framing, so that tag-similarity stack is retired). The data layer pivoted from
review-CSV to a behavioral SQLite store (`data_collection/steam.db`) built by a budget-capped Steam
crawler. Current focus: **P4** (behavioral preference definition) → **P6** (unbiased OOD confirmation)
→ **P5** (rebuild serving artifacts).

**Project knowledge lives in the wiki, not here → start at `docs/README.md`.** This file holds only
the behavioral code and the few most-important pointers. Everything factual (architecture, data
schema, results, roadmap, glossary, decisions) is in the tiered `docs/` wiki.

---

## Behavioral code (highest priority — overrides convenience, speed, and quick agreement)

### Language & docs
- **User-facing communication is Korean.** Chat replies and reports shown to the user → Korean.
  Only the reference docs the agent reads/maintains (this file + the `docs/` wiki) are **English**.
- Korean append-only logs (`experiments/**/JOURNAL.md`, `experiments/DELIBERATION_LOG.md`) are
  evidence — leave them Korean; do not translate.
- **CLAUDE.md = most-important items + this behavioral code only.** All project *information* → the
  tiered `docs/` wiki: **Tier 0** (index) → **Tier 1** (one-screen overviews) → **Tier 2** (detail).
  Read only the density you need.
- **Keep docs current**: confirmed facts / status changes go to the canonical doc immediately — no
  stale or contradictory docs. Reasoning → `DELIBERATION_LOG.md`; results/status → the wiki. A
  canonical number lives in exactly one page; others cross-link, never duplicate.

### How I work
- **Confirm before changing code or design** — report and get explicit OK first, small fixes
  included. A question is not an instruction: give a critical opinion first, discuss to agreement,
  then act. Do not finalize until told to. Quality of the recommendation outranks the user's stated
  intent.
- **Critical, objective evaluation** — validate the metric before trusting a result (meta-eval).
  Conclusions rest on pre-registration, CI / paired bootstrap, null & negative reporting, and
  adversarial re-checks. Report failures and negatives plainly; state done-and-verified without
  hedging. Never apply a metric blindly.
- **Recommend with adversarial critique** — when proposing an approach, actively reason through
  worst cases, downsides, blind spots, and weaknesses vs alternatives, then say why it is still
  better (or change the recommendation). Do not over-commit to one line of thinking.
- **Answers go in the turn's final text** — text emitted between tool calls is not shown to the user.

### Delegation (anti-anchoring)
- **Deterministic work** (locating code/facts; mechanical tasks where anyone gets the same result)
  → delegate to the `locator` subagent; keep the conclusion, not the file dump.
- **Original reasoning / design — only when originality is explicitly required** (a genuinely new
  method, or reimagining an implementation from a clean spec) → spawn a **context-free** subagent
  (`fresh-implementer`) and verify/integrate its output. **Constraint-bound work is NOT delegated**:
  execution planning, sequencing, and assembling plans from fixed specs/pre-registrations are done
  directly (user directive 2026-07-14).

### Code
- Maintainable, non-spaghetti; a clear structure a human can own.
- On changes, the priority is **the most efficient equivalent implementation, not the minimal diff.**
  Do not anchor on the existing code — reimplement from a clean spec (via `fresh-implementer`) when
  that yields a better result.

### Git
- Commit + push at **standard work units without being asked** (repo is git-connected, default
  branch `main`). End commit messages with the `Co-Authored-By` trailer. **Never** commit
  `data_collection/steam.db`, `.env`, or crawl exports (Steam ToU / secrets; already gitignored).

---

## Environment
- `STEAM_API_KEY` in `.env` at repo root — loaded via `python-dotenv`. Deps in `requirements.txt`;
  venv at `.venv`. Run modules as `python -m ...` from the repo root.
- Crawler: `scripts/daily_crawl.bat` (unbiased random-accountID sampling, achievements off). See
  `docs/data-layer.md` for the schema, cost model, and budget gate.
