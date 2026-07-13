# Architecture

> type: overview · status: active · updated: 2026-07-13

**What it is**: a personalized Steam recommender. Input = a user's play history (owned games +
playtime, optionally wishlist); output = a ranked list of games they don't own. The validated engine
is a **playtime-weighted item-item co-play collaborative filter** (≈ EASE); see [results](results.md).

## Current stack (validated)
```
Steam Web API ──crawl──▶ steam.db (behavioral store) ──▶ offline eval harness ──▶ ranker (EASE / co-play CF)
                          owned · wishlist · friends        co-play labels + wishlist recall
```
- **Data layer** — `data_collection/` (crawler `crawl_unified.py`, schema `db.py`) writing SQLite.
  Details: [data-layer](data-layer.md).
- **Modeling + evaluation** — `pipeline/` (`game_rec/`): the CF/EASE rankers and the evaluation
  library (co-play labels, graded NDCG, wishlist recall, bootstrap/FDR). Methodology:
  [evaluation](evaluation.md).
- **Experiments** — `experiments/p4_sweep/` (the P4 sweep, leaderboard, pre-registration, and the
  Korean append-only journals that serve as evidence).
- **Docs** — `docs/` (this English wiki). Behavioral code: `../CLAUDE.md`.

## The pivot (why the repo looks bimodal)
The project began as a **review-CSV + tag-embedding + LangGraph/Streamlit "vibe" recommender**
(`st_app/`, and the old `docs/pipeline` / `docs/intent` trees now in [archive](archive/)). That
stack's strength was anonymous vibe-matching — but on that framing an **LLM given the user's library
beat it**, so it was retired. The project pivoted to **behavioral data + collaborative filtering**,
where it holds a scoped moat (personalized-from-history). Full argument: [results](results.md).

## Current vs legacy
| | Current (active) | Legacy (archived) |
|---|---|---|
| Data | behavioral SQLite (playtime/ownership/wishlist) | review CSV + tag vocab |
| Model | co-play CF / EASE | tag-vector similarity + FAISS |
| Serving | offline shortlist → P6 confirmation | LangGraph + Streamlit "vibe" app |
| Verdict | scoped moat, validated | lost to LLM baseline, retired |

Where things stand now: [status](status.md). What's next: [roadmap](roadmap.md).
