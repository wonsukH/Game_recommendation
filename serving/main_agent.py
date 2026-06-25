"""Streamlit entry — hybrid game-recommendation AGENT (validated redesign).

Run:  streamlit run serving/main_agent.py

Personalized: load your Steam library (owned games + playtime) by Steam ID, or use
a demo library. The agent routes each request to the proven-best engine
(library/seed/multi-entity -> CF moat; anonymous vibe -> LLM), verifies hard
constraints, refines on under-fill, and explains its picks. Memory of
played/disliked games persists across the chat (session).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: E402
from pipeline.game_rec.agent.cf_recommender import CFRecommender  # noqa: E402
from pipeline.game_rec.agent.tools import CatalogMeta  # noqa: E402
from pipeline.game_rec.agent.steam_library import get_owned_games, proxy_library  # noqa: E402
from serving.agent_graph import build_agentic_graph  # noqa: E402

DATA = str(ROOT / "serving" / "data")

st.set_page_config(page_title="게임 추천 에이전트", page_icon="🎮", layout="centered")


@st.cache_resource(show_spinner="모델·인덱스 로딩...")
def _load():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        st.stop()
    cf = CFRecommender()
    meta = CatalogMeta(DATA)
    llm = ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"),
                                 google_api_key=key, temperature=0.3)
    graph = build_agentic_graph(cf, meta, llm, DATA)
    import pandas as pd
    df = pd.read_csv(f"{DATA}/steam_games_tags.csv")
    return graph, dict(zip(df["appid"].astype(int), df["game_title"].astype(str)))


graph, appid2title = _load()
ss = st.session_state
ss.setdefault("library", {})
ss.setdefault("friend_library", {})
ss.setdefault("played", set())
ss.setdefault("messages", [])

with st.sidebar:
    st.header("🎮 내 취향")
    src = st.radio("라이브러리 소스", ["데모 라이브러리", "Steam ID로 불러오기"], index=0)
    if src == "데모 라이브러리":
        seed = st.number_input("데모 유저 #", 0, 1000, 0)
        if st.button("불러오기", use_container_width=True):
            ss.library = proxy_library(seed=int(seed))
            st.success(f"데모 라이브러리 {len(ss.library)}개 로드")
    else:
        sid = st.text_input("내 Steam ID (17자리, 공개 프로필)")
        if st.button("불러오기", use_container_width=True) and sid:
            try:
                ss.library = get_owned_games(sid.strip(), DATA)
                st.success(f"{len(ss.library)}개 보유게임 로드")
            except Exception as e:
                st.error(f"실패: {e}. 데모 라이브러리로 대체.")
                ss.library = proxy_library()
        fid = st.text_input("친구 Steam ID (선택, '나+친구')")
        if st.button("친구 불러오기", use_container_width=True) and fid:
            try:
                ss.friend_library = get_owned_games(fid.strip(), DATA)
                st.success(f"친구 {len(ss.friend_library)}개")
            except Exception as e:
                st.error(f"실패: {e}")
    if ss.library:
        st.caption("내 라이브러리: " + ", ".join(appid2title.get(a, str(a)) for a in list(ss.library)[:8]) + " …")
    if st.button("친구(데모) 추가", use_container_width=True):
        ss.friend_library = proxy_library(seed=7)
        st.success(f"친구 데모 {len(ss.friend_library)}개")
    k = st.slider("추천 개수", 3, 10, 5)
    st.caption(f"이미 본/한 게임: {len(ss.played)}개 (추천서 제외)")

st.title("게임 추천 에이전트")
st.caption("라이브러리 기반 개인화(CF) + 제약 검증 + 방향성 탐색 + 자연어. 요청 유형별로 검증된 엔진에 라우팅합니다.")
st.caption("💡 '안 해본 새로운 장르로', '전투는 좋았는데 다른 분위기로' 처럼 **취향에서 벗어나는 방향**도 요청할 수 있어요(탐색 모드).")

for m in ss.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if q := st.chat_input("예: 협동·한국어 게임 / 다크소울 같은 거 / 나랑 친구 둘 다 / 안 해본 장르로 / 전투 좋았는데 다른 분위기"):
    ss.messages.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"):
        with st.spinner("에이전트 추론 중 (router → CF/LLM → 제약·refine → 설명)..."):
            state = {"user_query": q, "k": int(k), "played": list(ss.played),
                     "library": dict(ss.library), "friend_library": dict(ss.friend_library)}
            res = graph.invoke(state)
        resp = res.get("response", "추천을 생성하지 못했습니다.")
        st.markdown(resp)
        rt, relaxed = res.get("request_type"), res.get("relaxed")
        steer = res.get("steer") or {}
        steer_bits = []
        if steer.get("novelty_beta"):
            steer_bits.append("새 장르 탐색")
        if steer.get("aspect_tags"):
            steer_bits.append("요소:" + ",".join(t for t in steer["aspect_tags"] if t))
        meta_line = (f"🧭 route: **{rt}**"
                     + (f" · 🧭 {' / '.join(steer_bits)}" if steer_bits else "")
                     + (f" · 제약완화: {relaxed}" if relaxed else ""))
        st.caption(meta_line)
        recs = (res.get("filtered") or res.get("candidates") or [])[:int(k)]
        if recs:
            ss.played |= set(recs[:0])  # no-op placeholder; explicit mark below
            with st.expander("추천 목록 + '봤어요' 표시(메모리)"):
                for a in recs:
                    c1, c2 = st.columns([4, 1])
                    c1.write(appid2title.get(a, str(a)))
                    if c2.button("봤어요", key=f"seen_{len(ss.messages)}_{a}"):
                        ss.played.add(a)
        ss.messages.append({"role": "assistant", "content": resp + "\n\n" + meta_line})
