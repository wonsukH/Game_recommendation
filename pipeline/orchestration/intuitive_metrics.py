"""Intuitive evaluation metrics — built on top of llm_vs_system.csv results.

Two metrics designed for portfolio-friendly intuition:

A. LLM-as-Judge (Query Intent Match Rate)
   For each (query, recommended_game), ask Gemini Pro "is this game a good
   match for the query?" yes/no. Aggregate the yes-rate per system.
   Output: e.g. "시스템 87% 적합 / LLM 단독 73% 적합"

B. Genre / Tag Precision
   Each eval query has a category like `similar-soulslike`. Map the category
   to its canonical pool tag(s) and measure: of the 5 recs per query, what
   fraction actually carries one of those tags?
   System only — LLM 단독 추천은 풀 외부 게임이 포함되어 태그 정보가 없음.

Requires:
  - outputs/llm_vs_system.csv (run pipeline.orchestration.llm_vs_system first)
  - serving/data/steam_games_tags.csv
  - GEMINI_API_KEY in .env
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = REPO_ROOT / "outputs"
DATA = REPO_ROOT / "serving" / "data"

# ---- B: category -> canonical pool tags --------------------------------
# Built from eval_queries.json categories + observed tag vocab in
# serving/data/steam_games_tags.csv (normalized: lower, '-' separated).
# Multiple tags = ANY-of match (any one satisfies precision).
CATEGORY_TAG_MAP: dict[str, list[str]] = {
    # similar-*
    "soulslike":          ["souls-like"],
    "metroidvania":       ["metroidvania"],
    "jrpg":               ["jrpg"],
    "deckbuilder":        ["deckbuilding", "card-game"],
    "fps":                ["fps", "first-person-shooter"],
    "management":         ["management"],
    # vibe-*
    "cozy":               ["cozy", "casual"],
    "cute-farming":       ["farming-sim", "farming", "cute"],
    "detective-mystery":  ["detective", "mystery"],
    "horror-mystery":     ["horror", "mystery"],
    "narrative-walking":  ["walking-simulator", "story-rich"],
    "open-world-explore": ["open-world", "exploration"],
    "pixel-rpg":          ["pixel-graphics", "rpg"],
    "puzzle-relaxing":    ["puzzle", "relaxing"],
    "rhythm":             ["rhythm"],
    "roguelike":          ["rogue-like", "roguelike", "rogue-lite"],
    "short-emotional":    ["emotional", "short"],
    "stealth":            ["stealth"],
    "story-rich":         ["story-rich"],
    "survival-craft":     ["survival", "crafting"],
    "base-building":      ["base-building", "building"],
    # beginner-* (mainstream-friendly target genre)
    "dark-rpg":           ["dark", "rpg"],
    "platformer":         ["platformer", "2d-platformer"],
    "city-builder":       ["city-builder"],
    "strategy":           ["strategy"],
    "coop":               ["co-op", "multiplayer"],
    # heavy-*
    "grand-strategy":     ["grand-strategy"],
    "hardcore-action":    ["action", "difficult"],
    # hybrid-*
    "dark-action":        ["dark", "action"],
    "soulslike-relaxed":  ["souls-like"],
}


def category_tags(category: str) -> list[str]:
    """`hybrid-dark-action` -> ['dark', 'action']  via CATEGORY_TAG_MAP."""
    if not category or "-" not in category:
        return []
    rest = category.split("-", 1)[1]
    if rest in CATEGORY_TAG_MAP:
        return CATEGORY_TAG_MAP[rest]
    return []


def _norm_tag(t: str) -> str:
    return t.strip().lower().replace("/", "-").replace(" ", "-")


def genre_precision(games_df: pd.DataFrame, rec_titles: list[str],
                    targets: list[str]) -> float | None:
    """Of `rec_titles`, fraction that carry at least one of `targets`."""
    if not rec_titles or not targets:
        return None
    targets_n = {_norm_tag(t) for t in targets}
    hit = 0
    eligible = 0
    title_to_tags = dict(zip(games_df["game_title"], games_df["tags"]))
    for title in rec_titles:
        tags_str = title_to_tags.get(title)
        if not isinstance(tags_str, str):
            continue
        eligible += 1
        rec_tags = {_norm_tag(t) for t in tags_str.split(",") if t.strip()}
        if rec_tags & targets_n:
            hit += 1
    return (hit / eligible) if eligible > 0 else None


# ---- A: LLM-as-Judge ---------------------------------------------------
JUDGE_PROMPT = """\
당신은 게임 추천 평가자입니다. 한국어 쿼리에 대한 추천이 적합한지 판단해주세요.

쿼리: "{query}"
추천된 게임: "{game}"

이 게임이 쿼리의 핵심 의도(분위기·장르·취향)에 적합한지 한 단어로만 답하세요.
적합하면 yes, 적합하지 않으면 no.
다른 설명은 하지 마세요.
"""


def llm_judge(llm: ChatGoogleGenerativeAI, query: str, game: str) -> int:
    """Returns 1 if Gemini judges 'yes', else 0."""
    try:
        resp = llm.invoke(JUDGE_PROMPT.format(query=query, game=game))
        txt = (resp.content if hasattr(resp, "content") else str(resp)).strip().lower()
        return 1 if txt.startswith("y") else 0
    except Exception as e:
        print(f"  [judge error] q='{query[:30]}...' game='{game}': {e}", file=sys.stderr)
        return 0


# ---- main -------------------------------------------------------------
def _split_titles(s: str) -> list[str]:
    if not isinstance(s, str) or not s.strip():
        return []
    return [t.strip() for t in s.split("|") if t.strip() and t.strip() != "nan"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(OUTPUTS / "llm_vs_system.csv"))
    ap.add_argument("--output-md", default=str(OUTPUTS / "intuitive_metrics.md"))
    ap.add_argument("--judge-model", default=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"))
    ap.add_argument("--skip-judge", action="store_true",
                    help="B만 계산하고 A(LLM-as-Judge) 건너뛰기 (rate-limit 우회용)")
    args = ap.parse_args()

    load_dotenv()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found. Run llm_vs_system.py first.", file=sys.stderr)
        sys.exit(1)
    df = pd.read_csv(csv_path)
    games_df = pd.read_csv(DATA / "steam_games_tags.csv")
    print(f"Loaded {len(df)} eval rows from {csv_path.name}")
    print(f"Loaded {len(games_df)} games from steam_games_tags.csv")

    llm = None
    if not args.skip_judge:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("ERROR: GEMINI_API_KEY not set in .env", file=sys.stderr)
            sys.exit(1)
        llm = ChatGoogleGenerativeAI(
            model=args.judge_model,
            google_api_key=api_key,
            temperature=0.0,
        )

    judge_rows = []
    genre_rows = []

    for i, row in df.iterrows():
        qid = row["query_id"]
        query = row["query"]
        cat = row["category"]
        target_tags = category_tags(cat)
        our_recs = _split_titles(row.get("our_top5_titles", ""))
        llm_recs_raw = _split_titles(row.get("llm_top5_raw", ""))

        # A: LLM-as-Judge on both systems
        if llm is not None:
            print(f"  [{i+1}/{len(df)}] {qid} judge ...")
            for g in our_recs[:5]:
                judge_rows.append({
                    "query_id": qid, "system": "ours",
                    "game": g, "fit": llm_judge(llm, query, g),
                })
            for g in llm_recs_raw[:5]:
                judge_rows.append({
                    "query_id": qid, "system": "llm_alone",
                    "game": g, "fit": llm_judge(llm, query, g),
                })

        # B: Genre precision (system only — LLM 추천은 풀 외부 포함)
        prec = genre_precision(games_df, our_recs, target_tags)
        genre_rows.append({
            "query_id": qid, "category": cat,
            "target_tags": ",".join(target_tags),
            "system_precision": prec,
        })

    # Save raw
    g_df = pd.DataFrame(genre_rows)
    g_df.to_csv(OUTPUTS / "intuitive_genre.csv", index=False)
    print(f"\nSaved: {OUTPUTS / 'intuitive_genre.csv'}")

    if judge_rows:
        j_df = pd.DataFrame(judge_rows)
        j_df.to_csv(OUTPUTS / "intuitive_judge.csv", index=False)
        print(f"Saved: {OUTPUTS / 'intuitive_judge.csv'}")
    else:
        j_df = pd.DataFrame()

    # Aggregate
    lines = ["# Intuitive Metrics — Portfolio-friendly Evaluation\n"]

    lines.append("## A. LLM-as-Judge — 쿼리 정합도\n")
    if not j_df.empty:
        agg = j_df.groupby("system").agg(
            n_recs=("fit", "count"),
            n_fit=("fit", "sum"),
        ).reset_index()
        agg["rate"] = agg["n_fit"] / agg["n_recs"]
        lines.append(agg.to_markdown(index=False, floatfmt=".3f") + "\n")
        for _, r in agg.iterrows():
            lines.append(f"- **{r['system']}**: {int(r['n_fit'])} / {int(r['n_recs'])} = **{r['rate']*100:.1f}%**\n")
        lines.append("")
    else:
        lines.append("(A 건너뜀 — `--skip-judge`)\n")

    lines.append("## B. Genre / Tag Precision — 시스템 추천\n")
    valid = g_df[g_df["system_precision"].notna()]
    overall = valid["system_precision"].mean() if len(valid) else float("nan")
    lines.append(f"- 전체 평균 정밀도: **{overall*100:.1f}%** ({len(valid)} queries)\n")
    lines.append("- 카테고리별:\n")
    by_cat = valid.groupby("category")["system_precision"].mean().reset_index()
    by_cat["precision_pct"] = (by_cat["system_precision"] * 100).round(1)
    lines.append(by_cat[["category", "precision_pct"]].to_markdown(index=False, floatfmt=".1f") + "\n")

    out_md = Path(args.output_md)
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {out_md}")

    print("\n=== Summary ===")
    if not j_df.empty:
        print("A. LLM-as-Judge:")
        print(j_df.groupby("system")["fit"].mean().mul(100).round(1).to_string())
    print(f"B. Genre Precision (system overall): {overall*100:.1f}%")


if __name__ == "__main__":
    main()
