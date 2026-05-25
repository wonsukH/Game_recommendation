"""Dump parser input/output + final top-5 recommendation for 3 mode examples.

Picks one representative query per mode (similar/vibe/hybrid) from the eval
set and shows: user query → parsed_json (what each node receives) →
top-5 titles (what the system returns). Useful for portfolio I/O examples.
"""
import json, os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
from langchain_google_genai import ChatGoogleGenerativeAI
from pipeline.game_rec.agent.nodes.parser import llm_parser_node

CSV = "outputs/llm_vs_system.csv"

CASES = [
    ("ad-hoc-sim", "similar", "Hollow Knight 같은 게임 추천해줘"),
    ("q05",        "vibe",    "한 판 한 판 짧게 즐길 수 있는 로그라이크"),
    ("q02",        "hybrid",  "다크 소울 비슷한데 좀 더 가볍게 즐길 수 있는 게임"),
]

df = pd.read_csv(CSV)
llm = ChatGoogleGenerativeAI(
    model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"),
    google_api_key=os.environ["GEMINI_API_KEY"],
    temperature=0.0,
)

import sys, os as _os
_os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, ".")

from pipeline.game_rec.agent.retriever import VectorBasedRecommender
from pipeline.game_rec.agent.nodes.normalizer import game_name_normalizer_node

REC = VectorBasedRecommender(data_path="serving/data")

def run_full(query):
    parsed = llm_parser_node({"user_query": query}, llm).get("parsed_json", {})
    # normalize
    state = game_name_normalizer_node({"parsed_json": parsed}, REC)
    parsed = state.get("parsed_json", parsed)
    mode = parsed.get("mode")
    if mode == "similar":
        result = REC.recommend_similar(parsed)
    elif mode == "vibe":
        result = REC.recommend_vibe(parsed)
    elif mode == "hybrid":
        result = REC.recommend_hybrid(parsed)
    else:
        return parsed, []
    candidates = result.get("candidates", [])[:5]
    titles = []
    for appid in candidates:
        row = REC.games_df.loc[appid]
        titles.append(str(row["game_title"]))
    return parsed, titles


for qid, expected_mode, query in CASES:
    print("=" * 70)
    print(f"### {qid} (expected mode: {expected_mode})")
    print(f"USER QUERY: {query}")
    print()
    parsed, titles = run_full(query)
    print("PARSER OUTPUT (what each node receives):")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    print()
    print(f"SYSTEM TOP 5 (live, this run):")
    print(f"  {' | '.join(titles)}")
    print()
