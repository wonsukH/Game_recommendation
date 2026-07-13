---
name: wiki-update
description: Use when creating or updating a page in the docs/ LLM-wiki (the project knowledge base). Covers the house rules — status metablock, information-density tiering (Tier 0 index / Tier 1 overview / Tier 2 detail), answer-first, single-source-of-truth with cross-links, and the doc-format check. Trigger on "update the wiki", "add a docs page", "document X", or editing anything under docs/.
---
# Updating the docs/ wiki

`docs/` is an English, tiered LLM-wiki. Follow these rules, or delegate to the `wiki-scribe`
subagent (which encodes them).

## Tiers (information density)
- **Tier 0** — `docs/README.md`: the index. One line (purpose + status) per page. Keep it in sync
  whenever you add, rename, or remove a page.
- **Tier 1** — one-screen, answer-first overview pages (`architecture.md`, `data-layer.md`,
  `evaluation.md`, `results.md`, `roadmap.md`, `status.md`, `decisions.md`, `glossary.md`,
  `operations.md`). Lead with the conclusion; keep to ~one screen.
- **Tier 2** — deep-detail pages, linked from a Tier-1 page, for full schemas / methodology / derivations.

## Rules
1. **Status metablock** at the top of every page: `> type · status: active | deprecated | frozen ·
   updated: YYYY-MM-DD`. See `docs/STYLEGUIDE.md`.
2. **English** prose (code identifiers/metrics stay as-is). Don't translate the Korean evidence logs
   (`experiments/**/JOURNAL.md`, `experiments/DELIBERATION_LOG.md`) — link to them.
3. **Single source of truth**: a canonical number/fact lives on ONE page; elsewhere cross-link, never
   duplicate.
4. **Answer-first**: conclusion/number first, support after.
5. **Cross-link** related pages by relative path; update the Tier-0 index.
6. **Deprecated content** → move to `docs/archive/` with `status: deprecated` (don't delete — history).

## Finish
Run `python scripts/check_doc_format.py` → must be 0 failing. Then commit + push (standard unit).
