"""Benchmark runner: compare recommendation modes on a labelled eval set.

Reads a JSON eval file:
  [
    {"query": "처음 RPG 해보고 싶은데 어두운 분위기",
     "relevant_appids": [105600, 1145360, ...]},
    ...
  ]

Loads the offline pipeline artifacts (game_vecs, popularity, index_maps)
and runs each configured "mode" against every query, then prints a
Markdown table averaged across queries.

Modes registered out of the box:
- popularity        : top-k by popularity, ignores query
- content-ppmi      : query-vec similarity against game_vecs_ppmi (ablation)
- content-ensemble  : query-vec similarity against game_vecs (PPMI+Item2Vec ensemble)
- mmr-beginner      : ensemble + MMR rerank with beginner-preset weights
- mmr-heavy         : ensemble + MMR rerank with heavy-preset weights

Query → vec uses the existing W_align (Solar-embedding -> tag space)
through the same VectorBasedRecommender used by the Streamlit app.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.io import load_index_maps, load_vectors  # noqa: E402
from pipeline.game_rec.config import load_config  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.game_rec.evaluation.metrics import evaluate_recommendation  # noqa: E402

log = get_logger("orchestration.benchmark")


# ----- Mode implementations ---------------------------------------------------

def _embed_query(query: str, recommender) -> np.ndarray:
    """Use the live recommender's text -> tag-space embedding."""
    emb = recommender.embeddings.embed_query(query)
    proj = np.asarray(emb, dtype=np.float32) @ recommender.W_align
    n = float(np.linalg.norm(proj))
    return proj / n if n > 0 else proj


def rec_popularity(query: str, ctx: "BenchCtx", k: int) -> list[int]:
    """Top-k by popularity. Query ignored."""
    top = np.argsort(-ctx.popularity)[:k]
    return [ctx.row2appid[int(i)] for i in top]


def rec_content(query: str, ctx: "BenchCtx", k: int, vecs: np.ndarray) -> list[int]:
    """Cosine similarity against `vecs`. Picks top-k."""
    qv = _embed_query(query, ctx.recommender)
    if np.linalg.norm(qv) == 0:
        return []
    sims = vecs @ qv
    top = np.argsort(-sims)[:k]
    return [ctx.row2appid[int(i)] for i in top]


def rec_content_ensemble(query: str, ctx: "BenchCtx", k: int) -> list[int]:
    return rec_content(query, ctx, k, ctx.game_vecs)


def rec_content_ppmi(query: str, ctx: "BenchCtx", k: int) -> list[int]:
    return rec_content(query, ctx, k, ctx.game_vecs_ppmi)


def _mmr_rerank(candidates: list[int], qv: np.ndarray, ctx: "BenchCtx",
                weights: dict, k: int, mmr_lambda: float = 0.5) -> list[int]:
    """Reorder candidates using a weighted 4-axis MMR.

    Each item's base score is `w_rel·relevance + w_nov·novelty +
    w_ser·serendipity_proxy`. MMR enforces diversity at selection time.
    """
    if not candidates:
        return []
    cand_rows = [ctx.appid2row[a] for a in candidates if a in ctx.appid2row]
    if not cand_rows:
        return []
    V = ctx.game_vecs[cand_rows]
    # Relevance: cosine sim to query (normalize qv already)
    rel = V @ qv
    rel = (rel - rel.min()) / (rel.max() - rel.min() + 1e-9)
    # Novelty: -log2(P) normalized
    pop = ctx.popularity[cand_rows]
    prob = np.maximum(pop / ctx.popularity.sum(), 1e-12)
    nov = -np.log2(prob)
    nov = (nov - nov.min()) / (nov.max() - nov.min() + 1e-9)
    # Serendipity proxy: relevance * (1 - popularity_percentile)
    pct = np.argsort(np.argsort(pop)) / max(len(pop) - 1, 1)
    ser = rel * (1 - pct)
    if ser.max() > 0:
        ser = (ser - ser.min()) / (ser.max() - ser.min() + 1e-9)

    w_rel = weights.get("relevance", 5) / 10.0
    w_nov = weights.get("novelty", 5) / 10.0
    w_ser = weights.get("serendipity", 5) / 10.0
    w_div = weights.get("diversity", 5) / 10.0
    base = w_rel * rel + w_nov * nov + w_ser * ser

    selected: list[int] = []  # row idx in V
    remaining = list(range(len(cand_rows)))
    while remaining and len(selected) < k:
        if not selected:
            best = max(remaining, key=lambda i: base[i])
        else:
            sel_V = V[selected]
            # max similarity of remaining to already-selected
            sim_to_sel = (V[remaining] @ sel_V.T).max(axis=1)
            mmr = mmr_lambda * base[remaining] - (1 - mmr_lambda) * w_div * sim_to_sel
            best_local = int(np.argmax(mmr))
            best = remaining[best_local]
        selected.append(best)
        remaining.remove(best)

    return [candidates[ctx_idx] for ctx_idx in selected]


def rec_mmr_preset(query: str, ctx: "BenchCtx", k: int, preset_name: str,
                   pool_k: int = 200) -> list[int]:
    qv = _embed_query(query, ctx.recommender)
    if np.linalg.norm(qv) == 0:
        return []
    sims = ctx.game_vecs @ qv
    pool_rows = np.argsort(-sims)[:pool_k]
    candidates = [ctx.row2appid[int(i)] for i in pool_rows]
    weights = ctx.config["rerank"]["presets"][preset_name]
    mmr_lambda = ctx.config["rerank"].get("mmr_lambda", 0.5)
    return _mmr_rerank(candidates, qv, ctx, weights, k, mmr_lambda)


# ----- Context ---------------------------------------------------------------

@dataclass
class BenchCtx:
    game_vecs: np.ndarray
    game_vecs_ppmi: np.ndarray
    popularity: np.ndarray
    row2appid: dict
    appid2row: dict
    config: dict
    recommender: "VectorBasedRecommender"
    popularity_baseline_top: dict[int, set] = field(default_factory=dict)

    def baseline_top_rows(self, k: int) -> set:
        """Row indices (not appids) of the top-k by popularity."""
        if k not in self.popularity_baseline_top:
            top = np.argsort(-self.popularity)[:k]
            self.popularity_baseline_top[k] = {int(i) for i in top}
        return self.popularity_baseline_top[k]

    def appids_to_rows(self, appids) -> list[int]:
        return [self.appid2row[a] for a in appids if a in self.appid2row]


def load_context(data_dir: Path) -> BenchCtx:
    log.info("loading bench context from %s", data_dir)
    game_vecs = load_vectors(data_dir / "game_vecs.npy")
    ppmi_path = data_dir / "game_vecs_ppmi.npy"
    game_vecs_ppmi = load_vectors(ppmi_path) if ppmi_path.exists() else game_vecs

    pop_path = data_dir / "game_popularity.npy"
    popularity = np.load(pop_path).astype(np.float64) if pop_path.exists() else (
        np.ones(len(game_vecs), dtype=np.float64)
    )

    index_maps = load_index_maps(data_dir / "index_maps.json")

    config = load_config()

    # Lazy import to avoid pulling LangChain unless really needed
    from pipeline.game_rec.agent.retriever import VectorBasedRecommender
    recommender = VectorBasedRecommender(data_path=str(data_dir))

    return BenchCtx(
        game_vecs=game_vecs.astype(np.float32),
        game_vecs_ppmi=game_vecs_ppmi.astype(np.float32),
        popularity=popularity,
        row2appid=index_maps["row2appid"],
        appid2row=index_maps["appid2row"],
        config=config,
        recommender=recommender,
    )


# ----- Runner -----------------------------------------------------------------

MODES = {
    "popularity":       rec_popularity,
    "content-ppmi":     rec_content_ppmi,
    "content-ensemble": rec_content_ensemble,
    "mmr-beginner":     lambda q, ctx, k: rec_mmr_preset(q, ctx, k, "beginner"),
    "mmr-balanced":     lambda q, ctx, k: rec_mmr_preset(q, ctx, k, "balanced"),
    "mmr-heavy":        lambda q, ctx, k: rec_mmr_preset(q, ctx, k, "heavy"),
}


def run_benchmark(eval_path: Path, data_dir: Path, k: int, out_csv: Path) -> pd.DataFrame:
    with open(eval_path, "r", encoding="utf-8") as f:
        eval_set = json.load(f)
    log.info("loaded %d queries from %s", len(eval_set), eval_path)

    ctx = load_context(data_dir)

    rows: list[dict] = []
    for mode_name, fn in MODES.items():
        log.info("evaluating mode=%s", mode_name)
        per_q: list[dict] = []
        for entry in eval_set:
            query = entry["query"]
            true_appids = set(entry["relevant_appids"])
            rec_appids = fn(query, ctx, k)

            # Metrics operate on row indices so embedding/popularity
            # indexing is consistent.
            rec_rows = ctx.appids_to_rows(rec_appids)
            true_rows = set(ctx.appids_to_rows(true_appids))

            metrics = evaluate_recommendation(
                rec_indices=rec_rows,
                true_set=true_rows,
                item_embeddings=ctx.game_vecs,
                popularity=ctx.popularity,
                popularity_baseline_top=ctx.baseline_top_rows(k),
                k=k,
            )
            per_q.append(metrics)

        agg = {k_: float(np.mean([d[k_] for d in per_q])) for k_ in per_q[0]}
        agg["mode"] = mode_name
        rows.append(agg)

    df = pd.DataFrame(rows).set_index("mode")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv)
    log.info("saved CSV to %s", out_csv)

    # Markdown table to stdout
    print(df.round(4).to_markdown())
    return df


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-set", type=Path, default=REPO_ROOT / "tests" / "evaluation_set.json")
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    parser.add_argument("-k", type=int, default=10)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "outputs" / "benchmark.csv")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_benchmark(args.eval_set, args.data_dir, args.k, args.output)


if __name__ == "__main__":
    main()
