"""Compare our recommender against pure-LLM recommendation on a fixed query set.

For each query:
  1. Run our system: parser → normalizer → {similar/vibe/hybrid}_node → rerank → top 5
  2. Run pure LLM: Gemini Pro with prompt asking for 5 Steam games
  3. Compute LABEL-FREE comparison metrics between the two top-5 sets

No ground-truth labels needed. Useful when you don't know all 10K games
but still want to quantify how the system differs from naive LLM output.

Metrics:
  - overlap@5            : |A ∩ B| / 5
  - llm_existence_rate   : fraction of LLM titles that actually exist in our pool
  - our_avg_pop          : popularity of our top-5
  - llm_avg_pop          : popularity of LLM's top-5 (matched games only)
  - our_ild              : intra-list diversity (1 - mean pairwise cosine)
  - llm_ild              : same for LLM picks

Usage:
    python -m pipeline.orchestration.llm_vs_system
    python -m pipeline.orchestration.llm_vs_system --queries tests/eval_queries.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from langchain.schema.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.agent.nodes.normalizer import (  # noqa: E402
    find_best_match,
    game_name_normalizer_node,
)
from pipeline.game_rec.agent.nodes.parser import llm_parser_node  # noqa: E402
from pipeline.game_rec.agent.retriever import VectorBasedRecommender  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.llm_vs_system")

DATA_DIR = REPO_ROOT / "serving" / "data"


# ---------------------------------------------------------------------------

def run_our_system(
    query: str,
    recommender: VectorBasedRecommender,
    llm: ChatGoogleGenerativeAI,
    weights: dict,
) -> list[int]:
    """Run our full pipeline (sans graph framework) and return top-5 appids."""
    state: dict[str, Any] = {"user_query": query}
    state = llm_parser_node(state, llm)
    parsed = state.get("parsed_json", {})

    mode = parsed.get("mode", "general")
    if mode == "general" or not parsed.get("games") and not parsed.get("phrases"):
        return []

    state = game_name_normalizer_node({"parsed_json": parsed}, recommender)
    parsed = state.get("parsed_json", parsed)

    if mode == "similar":
        result = recommender.recommend_similar(parsed)
    elif mode == "vibe":
        result = recommender.recommend_vibe(parsed)
    elif mode == "hybrid":
        result = recommender.recommend_hybrid(parsed)
    else:
        return []

    if not isinstance(result, dict) or "candidates" not in result:
        return []
    candidates = result["candidates"]
    qv = result["query_vector"]
    final = recommender.rerank_candidates(candidates, qv, weights, top_n=5)
    if final.empty:
        return []
    return [int(a) for a in final.index.tolist()]


def run_pure_llm(query: str, llm: ChatGoogleGenerativeAI) -> list[str]:
    """Pure LLM recommendation: ask for 5 Steam game titles, no system context."""
    prompt = (
        "You are a game recommendation assistant. The user gives a Korean query.\n"
        "Recommend exactly 5 real Steam games that match the query.\n"
        "Output ONLY the official English Steam title of each game, one per line.\n"
        "No descriptions, no numbering, no extra text.\n\n"
        f"User query: {query}\n\n"
        "5 Steam game titles:"
    )
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        log.exception("LLM call failed: %s", e)
        return []

    lines = []
    for raw in text.split("\n"):
        cleaned = raw.strip()
        # Strip common list markers
        for prefix in ("- ", "* ", "• "):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        # Strip leading "1. ", "2. " etc.
        if len(cleaned) > 2 and cleaned[0].isdigit() and cleaned[1] in (".", ")"):
            cleaned = cleaned[2:].strip()
        if cleaned:
            lines.append(cleaned)
    return lines[:5]


def map_titles_to_appids(
    titles: list[str], games_df: pd.DataFrame, threshold: float = 0.5
) -> list[int]:
    """Fuzzy-match LLM titles to canonical games_df titles. -1 if no match."""
    canonical = games_df["game_title"].tolist()
    title_to_appid = dict(zip(games_df["game_title"], games_df["appid"]))
    out: list[int] = []
    for t in titles:
        match = find_best_match(t, canonical, threshold=threshold)
        # find_best_match returns query unchanged if no match clears threshold
        if match in title_to_appid:
            out.append(int(title_to_appid[match]))
        else:
            out.append(-1)
    return out


def _ild(appids: list[int], recommender: VectorBasedRecommender) -> float:
    """Intra-list diversity = 1 - mean pairwise cosine."""
    rows = [
        recommender.appid_to_idx[a]
        for a in appids
        if a in recommender.appid_to_idx
    ]
    if len(rows) < 2:
        return 0.0
    V = recommender.game_vecs[rows].astype(np.float32)
    norms = np.linalg.norm(V, axis=1, keepdims=True).clip(min=1e-12)
    V = V / norms
    sim = V @ V.T
    n = len(rows)
    upper = sim[np.triu_indices(n, k=1)]
    return float(1.0 - upper.mean())


def compute_metrics(
    our: list[int],
    llm_appids: list[int],
    recommender: VectorBasedRecommender,
) -> dict:
    our_set = set(our)
    llm_valid = [a for a in llm_appids if a != -1]
    llm_set = set(llm_valid)

    metrics = {
        "overlap@5": len(our_set & llm_set) / 5.0,
        "llm_existence_rate": (sum(1 for a in llm_appids if a != -1) / max(len(llm_appids), 1)),
    }

    pop = recommender.popularity
    if pop is not None:
        our_rows = [recommender.appid_to_idx[a] for a in our if a in recommender.appid_to_idx]
        llm_rows = [recommender.appid_to_idx[a] for a in llm_valid if a in recommender.appid_to_idx]
        metrics["our_avg_pop"] = float(np.mean(pop[our_rows])) if our_rows else 0.0
        metrics["llm_avg_pop"] = float(np.mean(pop[llm_rows])) if llm_rows else 0.0
    else:
        metrics["our_avg_pop"] = 0.0
        metrics["llm_avg_pop"] = 0.0

    metrics["our_ild"] = _ild(our, recommender)
    metrics["llm_ild"] = _ild(llm_valid, recommender)
    return metrics


def _titles_from_appids(appids: list[int], games_df: pd.DataFrame) -> list[str]:
    by_appid = dict(zip(games_df["appid"], games_df["game_title"]))
    return [by_appid.get(a, f"appid={a}") for a in appids]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queries", type=Path,
        default=REPO_ROOT / "tests" / "eval_queries.json",
    )
    parser.add_argument(
        "--output-csv", type=Path,
        default=REPO_ROOT / "outputs" / "llm_vs_system.csv",
    )
    parser.add_argument(
        "--output-md", type=Path,
        default=REPO_ROOT / "outputs" / "llm_vs_system.md",
    )
    parser.add_argument(
        "--preset", choices=["beginner", "balanced", "heavy"], default="beginner",
        help="Rerank preset to use for our system.",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limit to first N queries (0 = all)",
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY not set in .env")
        return 1

    chat_model = os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro")
    llm = ChatGoogleGenerativeAI(model=chat_model, google_api_key=api_key, temperature=0.2)

    log.info("loading recommender from %s", DATA_DIR)
    recommender = VectorBasedRecommender(data_path=str(DATA_DIR))
    games_df = recommender.games_df.reset_index()

    # Preset weights — same as config/default.yaml's rerank.presets
    PRESETS = {
        "beginner":  {"relevance": 9, "diversity": 4, "novelty": 2, "serendipity": 1},
        "balanced":  {"relevance": 5, "diversity": 5, "novelty": 5, "serendipity": 5},
        "heavy":     {"relevance": 5, "diversity": 7, "novelty": 8, "serendipity": 8},
    }
    weights = PRESETS[args.preset]
    log.info("using preset=%s weights=%s", args.preset, weights)

    queries = json.loads(args.queries.read_text(encoding="utf-8"))
    if args.limit > 0:
        queries = queries[: args.limit]

    rows = []
    for i, q in enumerate(queries):
        log.info("[%d/%d] %s", i + 1, len(queries), q["query"])
        try:
            our = run_our_system(q["query"], recommender, llm, weights)
        except Exception as e:
            log.exception("our system failed on q=%s: %s", q.get("id"), e)
            our = []
        try:
            llm_titles = run_pure_llm(q["query"], llm)
        except Exception as e:
            log.exception("pure LLM failed on q=%s: %s", q.get("id"), e)
            llm_titles = []
        llm_appids = map_titles_to_appids(llm_titles, games_df)
        m = compute_metrics(our, llm_appids, recommender)

        rows.append({
            "query_id": q.get("id", f"q{i:02d}"),
            "category": q.get("category", ""),
            "query": q["query"],
            "our_top5_titles": " | ".join(_titles_from_appids(our, games_df)),
            "llm_top5_raw": " | ".join(llm_titles),
            "llm_top5_matched": " | ".join(
                _titles_from_appids([a for a in llm_appids if a != -1], games_df)
            ),
            **m,
        })

    df = pd.DataFrame(rows)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output_csv, index=False, encoding="utf-8")
    log.info("saved CSV: %s", args.output_csv)

    # Aggregate summary
    metric_cols = [
        "overlap@5", "llm_existence_rate", "our_avg_pop", "llm_avg_pop",
        "our_ild", "llm_ild",
    ]
    summary = df[metric_cols].mean()

    # Write markdown summary
    md_lines = [
        f"# LLM vs Our System — preset `{args.preset}`",
        "",
        f"Queries evaluated: **{len(df)}**",
        "",
        "## Aggregate metrics (averaged across queries)",
        "",
        "| Metric | Value | Meaning |",
        "|---|---|---|",
        f"| `overlap@5` | {summary['overlap@5']:.3f} | Fraction of top-5 games shared by both systems |",
        f"| `llm_existence_rate` | {summary['llm_existence_rate']:.3f} | LLM titles that actually exist in our 10K pool (1.0 = no hallucination) |",
        f"| `our_avg_pop` | {summary['our_avg_pop']:,.0f} | Mean popularity of our picks |",
        f"| `llm_avg_pop` | {summary['llm_avg_pop']:,.0f} | Mean popularity of LLM picks |",
        f"| `our_ild` | {summary['our_ild']:.3f} | Our top-5 diversity (1 - mean pairwise cosine) |",
        f"| `llm_ild` | {summary['llm_ild']:.3f} | LLM top-5 diversity |",
        "",
        "## Interpretation",
        "",
        "- Low `overlap@5` + high `llm_existence_rate` = systems disagree on real games (our system adds value beyond what LLM recalls)",
        "- `llm_existence_rate < 1.0` = LLM hallucinates titles not in our pool",
        "- `our_avg_pop < llm_avg_pop` = we surface less-popular games (long-tail coverage)",
        "- `our_ild > llm_ild` = our results are more diverse (MMR rerank effect)",
        "",
        "## Per-query results",
        "",
        df.to_markdown(index=False),
    ]
    args.output_md.write_text("\n".join(md_lines), encoding="utf-8")
    log.info("saved MD: %s", args.output_md)

    print("\n=== Summary ===")
    print(summary.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
