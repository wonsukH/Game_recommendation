# Architecture

> type: overview · status: active · updated: 2026-07-20

**What it is**: a personalized Steam recommender. Input = a user's play history (owned games +
playtime); output = a ranked list of games they don't own. The confirmed engine is **EASE (λ=100)
over playtime-percentile preferences** — P6-confirmed on an unbiased OOD panel, both axes
([results](results.md)) — served live inside a LangGraph + Streamlit agent (P5, 2026-07-20).

## Current stack (live)
```
Steam Web API ──crawl──▶ steam.db ──behavioral_extract──▶ outputs/p5 snapshot
                                        │
             build_ease_artifact ◀──────┴──────▶ build_catalog_db
                    │                                   │
        serving/data/ease/ (sparse top-K B)   serving/data/ (catalog artifacts)
                    └────────────┬──────────────────────┘
                                 ▼
        serving/main_agent.py (Streamlit) ─ serving/agent_graph.py (LangGraph)
        routes: library · seed · multi · explore(steer) · constraint · anonymous(LLM)
```

- **Data layer** — `data_collection/` (crawler + SQLite schema): [data-layer](data-layer.md).
- **Builders (P5, steam.db-native)** — `pipeline/game_rec/data/build_ease_artifact.py`
  (EASE fit → exact B rows → top-K sparsify; gated by `pipeline/orchestration/p5_validate.py`) and
  `build_catalog_db.py` (tags/quality/popularity/constraints/titles). Build steps:
  [operations](operations.md) §7.
- **Serving** — `serving/main_agent.py` + `agent_graph.py`; ranker adapter
  `pipeline/game_rec/agent/ease_recommender.py` (contract: `score/recommend/col/inv_col/
  game_avg_pt`; **no score≤0 truncation** — EASE's negative tail is signal). Steering/cold-fill:
  `content.py` + `hybrid.py`; constraints/quality: `tools.CatalogMeta`.
- **Evaluation** — `pipeline/orchestration/` harnesses + `pipeline/game_rec/evaluation/`:
  [evaluation](evaluation.md).

## Runtime artifact map (all steam.db-derived; zero runtime CSV reads*)
| Artifact (`serving/data/`) | Producer | Consumer |
|---|---|---|
| `ease/B_topk.npz` + `items/avg_pt/pt_ecdf/meta` | build_ease_artifact | EASERecommender |
| `index_maps.json`, `X_game_tag_csr.npz` | build_catalog_db | ContentLayer (steer/cold-fill) |
| `game_popularity.npy` (unbiased ownership rates) | build_catalog_db ← E2 re-estimate | CatalogMeta |
| `game_quality.json` (SteamSpy shrunk) | build_catalog_db | CatalogMeta.quality_gate |
| `catalog.json` (constraints) | build_catalog_db | CatalogMeta.constraint_filter |
| `steam_games_tags.csv` (titles; tracked) | build_catalog_db | title maps |

*`steam_games_tags.csv` remains as a tracked title map — regenerated from the DB, not crawled CSV.

## The pivot (why the repo looks bimodal)
The project began as a review-CSV + tag-embedding **anonymous "vibe" recommender**. On that framing
an LLM-with-library baseline won, so the vibe stack was retired ([archive](archive/)); the
LangGraph/Streamlit **app shell survived** and was progressively re-engined: behavioral data (P2),
co-play CF moat (P3), preference definition (P4), unbiased OOD confirmation (P6), and finally the
EASE rewire (P5). The validated F-steering (novelty/aspect) rides the rebuilt tag matrix.

## Current vs legacy
| | Current (live) | Legacy (archived) |
|---|---|---|
| Data | behavioral SQLite (playtime/ownership/wishlist) | review CSV + tag vocab |
| Ranker | **EASE λ100 × pctl_game** (sparse-B artifact) | tag-vector FAISS · condcos CF |
| Catalog signals | SteamSpy quality · unbiased popularity · DB constraints | review-score quality · CSV metadata |
| Serving | LangGraph agent, all routes on EASE | same shell on the vibe engines |

Where things stand now: [status](status.md). What's next: [roadmap](roadmap.md).
