# Doc style guide

> type: design-spec · status: active · updated: 2026-07-13

> **Goal**: standardize this repo's docs into a form a **future Claude (agent) can search fast and cite accurately** — the primary purpose is retrieval/verification optimization, not human aesthetics. **Hard constraint: never change body content, numbers, or wording (no summarizing). Standardize only formatting, structure, and splitting.**

The whole doc set is designed as a **wiki an LLM navigates**: start at the home index ([`README.md`](README.md)); each page is one topic's article (metablock + answer-first lead + body + cross-links), densely linked hub↔child and canonical↔alias. The point: in a future session, when Claude answers a question, it should (a) reach the right file fast, (b) read only the part it needs, and (c) cite only current, correct information. Everything below serves that.

## 1. Metablock (required header on every doc)

Every doc puts an H1 (`# ...`) as its first line, and a one-line blockquote metablock directly under it. Both must appear **within the first ~8 lines** — that is the window the checker reads.

```
# <Title>

> type: <type> · status: active | deprecated | frozen · updated: YYYY-MM-DD
```

The checker is **bilingual**. It accepts EITHER form on the metablock line:

- **English (use this for all new `docs/` wiki pages):**
  `> type: <type> · status: <status> · updated: YYYY-MM-DD`
- **Legacy Korean (kept only by the append-only Korean evidence logs):**
  `> **유형**: <type> · **상태**: <status> · **갱신**: YYYY-MM-DD`

New wiki pages use the English form. The Korean append-only logs (`experiments/**/JOURNAL.md`, `experiments/DELIBERATION_LOG.md`) are evidence — leave them Korean, metablock included.

Fields are parsed independently, so extra fields may sit between them:
- **roadmap** may append branch/origin: `· branch: \`feat/…\` · origin = github.com/…`.
- **experiment-report** may append `· run: \`<run_id>\``.

`status` meaning: `active` (current) · `deprecated` (pre-pivot record, not canonical) · `frozen` (generator removed etc.; hand-maintained only).

## 2. type vocabulary

`type` must be exactly one of the set the checker allows (`VOCAB` in `scripts/check_doc_format.py`):

| type | what | example |
|---|---|---|
| `behavior-rules` | working rules | `../CLAUDE.md` |
| `overview` | project overview | `README.md` |
| `roadmap` | durable phase plan | `docs/roadmap.md` |
| `design-spec` | design intent / spec | this doc, `experiments/p4_sweep/P6_PREREG.md` |
| `bug-log` | diagnosed issue record | `docs/archive/issues/*` |
| `runbook` | operational how-to | `docs/operations.md` |
| `index` | navigation / catalog | `experiments/INDEX.md`, `experiments/README.md` |
| `reasoning-log` | append-only deliberation narrative | `experiments/DELIBERATION_LOG.md` |
| `experiment-report` | per-run result report (auto-generated) | `experiments/<run>/report.md` |
| `metric-report` | metric trust validation | `metric_trust_report.md` |
| `eval-output` | evaluation artifact | `outputs/*.md` |
| `portfolio` | hiring / presentation | `docs/portfolio/*` |
| `html-reference` | HTML reference material | `docs/technical_reference.html` |

Full set: `behavior-rules, overview, roadmap, design-spec, bug-log, runbook, index, reasoning-log, experiment-report, metric-report, eval-output, portfolio, html-reference`.

## 3. status and deprecation banner

`status` ∈ `active | deprecated | frozen`.

A `deprecated` or `frozen` doc must carry, **near the top** (within the checked head), a deprecation banner or a canonical pointer. The checker accepts any one of these markers: `[폐기·이력]`, `정본`, `[deprecated]`, or `canonical:`. Standard form:

```
> ⚠️ **[deprecated]** <one-line reason>. canonical: [`../README.md`](../README.md).
```

## 4. Information-density tiers

The wiki is organized into tiers so a reader takes on only the depth the question needs — **read only the depth you need**.

- **Tier 0 — index** (`README.md`): the catalog. One line + status per page; the map you scan first, not a place to read detail.
- **Tier 1 — overview pages**: one-screen, answer-first summaries of a topic (conclusion/number up top). Keep each to roughly one screen; push depth down to Tier 2.
- **Tier 2 — detail pages**: deep, full-detail pages, each linked from its Tier-1 overview. This is where long tables, derivations, and per-run specifics live.

Navigation is top-down: Tier 0 points to Tier 1, Tier 1 points to Tier 2. A reader stops at the shallowest tier that answers the question.

## 5. House rules

- **Answer-first**: lead with the conclusion / decision / key number. A report's first few lines must yield the verdict (e.g. a `## Decision` section or a `**decision**: …` lead line), so retrieval hits the answer immediately.
- **Single source of truth**: a canonical number lives on **exactly one** page. Every other mention cross-links to it — never re-state (and risk desyncing) the value. Current canonical hubs: [`results.md`](results.md) (experiment numbers) and [`status.md`](status.md) (live counts).
- **Cross-link by relative path**: file references use relative markdown links `[`path`](path)`. `[[wiki-link]]` syntax is reserved for memory cross-refs only (e.g. `[[confirm-before-code-change]]`).
- **Keep Tier-1 pages to ~one screen**: if an overview outgrows a screen, split detail into a Tier-2 page and link it, rather than letting the overview sprawl.
- **English prose, identifiers as-is**: body prose is English, but keep code, CLI, identifiers, and metric names verbatim (existing convention).
- **Do not translate the Korean evidence logs**: `experiments/**/JOURNAL.md` and `experiments/DELIBERATION_LOG.md` are append-only evidence — leave them Korean and edit them append-only (no in-place rewrite of past entries).
- **Headers**: `##` = section, `###` = subsection. Do not use `**bold**` or ALLCAPS as a header substitute; header depth reflects real content nesting.
- **Dates**: ISO `YYYY-MM-DD` (run-directory `YYYYMMDD_HHMMSS` timestamps stay as-is).
- **blockquote `>`**: reserved for the metablock, the deprecation banner, and at most one TL;DR callout per doc — not for generic emphasis.

## 6. Content preservation (highest priority)

At no step of formatting work do you **change or shorten body text, numbers, or sentences**. If a page is too long, split it along existing section boundaries (the union of the split must match the original byte-for-byte); if it is stale, mark `status: deprecated` + banner but preserve the content. If deletion or summarizing seems necessary, confirm with the user first ([[confirm-before-code-change]]).

## 7. Check (enforced)

Run before committing:

```
python scripts/check_doc_format.py
```

`scripts/check_doc_format.py` (read-only) scans every tracked doc (`README.md`, `docs/**`, `experiments/**` `.md`; `outputs/`, `docs/portfolio/`, `.venv/`, `node_modules/` are excluded as gitignored/non-prose) and, within each doc's first 8 lines, checks: (a) an H1; (b) a metablock with `type` in the vocabulary, `status` in `{active, deprecated, frozen}`, and `updated` as `YYYY-MM-DD` — in either the English or legacy Korean form; (c) for `deprecated`/`frozen`, a banner or canonical pointer near the top. Any violation exits non-zero. It must report **0 failing** before commit.
