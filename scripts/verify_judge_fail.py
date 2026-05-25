"""Check if Judge-fail cases are due to (a) LLM ignorance or (b) real mismatch.

For each system rec that Judge said 'no', check:
  1. Real tags in our pool (objective ground truth)
  2. LLM's own knowledge of the game ("Do you know this game? What genre?")
"""
import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
from langchain_google_genai import ChatGoogleGenerativeAI

GAMES = [
    "Unalive",
    "Fancy Skulls",
    "Not The Robots",
    "Star Chronicles: Delta Quadrant",
    "Never Split the Party",
]

df = pd.read_csv("serving/data/steam_games_tags.csv")
print("=== 1) 우리 풀의 실제 태그 ===")
for g in GAMES:
    row = df[df["game_title"] == g]
    if not row.empty:
        tags = [t.strip() for t in str(row.iloc[0]["tags"]).split(",")[:10]]
        print(f"  {g}: {tags}")
    else:
        print(f"  {g}: NOT IN POOL")

print()
print("=== 2) LLM(Gemini Flash)의 인식 ===")
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ["GEMINI_API_KEY"],
    temperature=0.0,
)
for g in GAMES:
    prompt = (
        f'"{g}"라는 Steam 게임을 알고 있어? '
        "안다면 장르(roguelike/action/puzzle 등)를 한 줄로, 모르면 'unknown'만 답해."
    )
    resp = llm.invoke(prompt)
    txt = (resp.content if hasattr(resp, "content") else str(resp)).strip()
    print(f"  {g}: {txt[:200]}")
