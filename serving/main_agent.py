"""Streamlit entry — hybrid game-recommendation AGENT.

Run:  streamlit run serving/main_agent.py

Personalized: load your Steam library (owned + playtime) by Steam ID, or pick demo
users (multi-select = "covariate" = me+friend multi-entity). The agent routes each
request to the proven-best engine (library/seed/multi-entity -> CF moat; explore ->
CF + content steering; anonymous vibe -> LLM), verifies hard constraints, refines on
under-fill, and explains its picks. Right panel: the technical manual. Above the
input: routing-grouped example prompts (click to run). Played-memory persists.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: E402
from pipeline.game_rec.agent.ease_recommender import EASERecommender  # noqa: E402
from pipeline.game_rec.agent.tools import CatalogMeta  # noqa: E402
from pipeline.game_rec.agent.steam_library import get_owned_games, proxy_library  # noqa: E402
from serving.agent_graph import build_agentic_graph  # noqa: E402

DATA = str(ROOT / "serving" / "data")
MANUAL = ROOT / "docs" / "technical_reference.html"

# routing-grouped example prompts (click -> runs immediately)
EXAMPLES = {
    "🎯 library · 개인화": ["나한테 맞는 게임 추천해줘", "내 라이브러리 기반으로 골라줘"],
    "🔁 seed · 비슷한": ["다크소울 같은 거", "엘든링이랑 비슷한 게임"],
    "🧭 explore · 탐색": ["안 해본 새로운 장르로 색다른 거", "전투는 좋았는데 다른 분위기로"],
    "👥 multi · 나+친구": ["나랑 친구 둘 다 좋아할 게임"],
    "🔒 constraint · 제약": ["협동 가능하고 한국어 되는 게임", "2만원 이하 협동 게임"],
    "💬 anonymous · LLM": ["차분하고 분위기 좋은 인디 게임"],
}
DEMO_SEEDS = [0, 1, 2, 3, 5, 7]

st.set_page_config(page_title="게임 추천 에이전트", page_icon="🎮", layout="wide")


@st.cache_resource(show_spinner="모델·인덱스 로딩...")
def _load():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        st.stop()
    cf = EASERecommender()  # P6-confirmed serving ranker (EASE l100 x pctl_game)
    meta = CatalogMeta(DATA)
    llm = ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"),
                                 google_api_key=key, temperature=0.3)
    graph = build_agentic_graph(cf, meta, llm, DATA)
    import pandas as pd
    df = pd.read_csv(f"{DATA}/steam_games_tags.csv")
    return graph, dict(zip(df["appid"].astype(int), df["game_title"].astype(str)))


@st.cache_data(show_spinner=False)
def _demo_lib(seed: int) -> dict:
    return proxy_library(seed=int(seed))


graph, appid2title = _load()
ss = st.session_state
ss.setdefault("library", {})
ss.setdefault("friend_library", {})
ss.setdefault("played", set())
ss.setdefault("messages", [])
ss.setdefault("show_manual", False)
ss.setdefault("pending", None)


def _titles(lib, n=8):
    return ", ".join(appid2title.get(a, str(a)) for a in list(lib)[:n])


# ---------------- sidebar: users (single=library, multi=covariate/multi_entity) ----------------
with st.sidebar:
    st.header("🎮 내 취향")
    st.caption("데모 유저를 고르세요. **여러 명 선택 = 공변량(나+친구) → 다중주체 추천**.")
    picked = st.multiselect("데모 유저 (클릭)", DEMO_SEEDS,
                            format_func=lambda s: f"유저 #{s}", default=[])
    if st.button("선택 유저 불러오기", use_container_width=True, type="primary"):
        libs = [_demo_lib(s) for s in picked] if picked else []
        if not libs:
            ss.library, ss.friend_library = {}, {}
            st.warning("유저를 1명 이상 선택하세요.")
        elif len(libs) == 1:
            ss.library, ss.friend_library = dict(libs[0]), {}
            st.success(f"개인화 모드 · 라이브러리 {len(ss.library)}개")
        else:  # >=2 -> covariate: first=me, rest merged=friend -> multi_entity
            ss.library = dict(libs[0])
            fr = {}
            for L in libs[1:]:
                fr.update(L)
            ss.friend_library = fr
            st.success(f"공변량(다중주체) · 나 {len(ss.library)} + 친구 {len(ss.friend_library)}")

    with st.expander("🔑 실제 Steam ID로 불러오기"):
        sid = st.text_input("내 Steam ID (17자리, 공개)")
        if st.button("내 라이브러리", use_container_width=True) and sid:
            try:
                ss.library = get_owned_games(sid.strip(), DATA); st.success(f"{len(ss.library)}개 로드")
            except Exception as e:
                st.error(f"실패: {e}")
        fid = st.text_input("친구 Steam ID (다중주체)")
        if st.button("친구 라이브러리", use_container_width=True) and fid:
            try:
                ss.friend_library = get_owned_games(fid.strip(), DATA); st.success(f"친구 {len(ss.friend_library)}개")
            except Exception as e:
                st.error(f"실패: {e}")

    if ss.library:
        st.caption("🧑 나: " + _titles(ss.library) + " …")
    if ss.friend_library:
        st.caption("👤 친구: " + _titles(ss.friend_library) + " …")
    k = st.slider("추천 개수", 3, 10, 5)
    st.caption(f"이미 본/한 게임: {len(ss.played)}개 (추천서 제외)")
    ss.show_manual = st.toggle("📖 설명서 (오른쪽)", value=ss.show_manual)


# ---------------- layout: chat (left) + manual (right, optional) ----------------
main_col, manual_col = (st.columns([3, 2]) if ss.show_manual else (st.container(), None))

with main_col:
    st.title("게임 추천 에이전트")
    st.caption("라이브러리 개인화(CF) + 제약 검증 + **방향성 탐색** + 자연어. 요청 유형별로 검증된 엔진에 라우팅.")

    # routing-grouped example chips (click = run)
    with st.container(border=True):
        st.caption("💡 예시 프롬프트 — 클릭하면 바로 실행 (라우팅별)")
        for label, prompts in EXAMPLES.items():
            cols = st.columns([1.4] + [1] * len(prompts))
            cols[0].markdown(f"<div style='padding-top:6px;font-size:12.5px;color:#888'>{label}</div>",
                             unsafe_allow_html=True)
            for j, p in enumerate(prompts):
                if cols[j + 1].button(p, key=f"ex_{label}_{j}", use_container_width=True):
                    ss.pending = p

    for m in ss.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

if manual_col is not None:
    with manual_col:
        if MANUAL.exists():
            components.html(MANUAL.read_text(encoding="utf-8"), height=820, scrolling=True)
        else:
            st.info("docs/technical_reference.html 없음")


# ---------------- run (typed input or clicked chip) ----------------
typed = st.chat_input("예: 협동·한국어 / 다크소울 같은 거 / 나랑 친구 둘 다 / 안 해본 장르로 / 전투 좋았는데 다른 분위기")
query = ss.pending or typed
ss.pending = None

if query:
    ss.messages.append({"role": "user", "content": query})
    with main_col:
        with st.chat_message("user"):
            st.markdown(query)
        with st.chat_message("assistant"):
            with st.spinner("에이전트 추론 중 (router → CF/LLM → 제약·refine → 설명)..."):
                state = {"user_query": query, "k": int(k), "played": list(ss.played),
                         "library": dict(ss.library), "friend_library": dict(ss.friend_library)}
                res = graph.invoke(state)
            resp = res.get("response", "추천을 생성하지 못했습니다.")
            st.markdown(resp)
            rt, relaxed = res.get("request_type"), res.get("relaxed")
            steer = res.get("steer") or {}
            bits = []
            if steer.get("novelty_beta"):
                bits.append("새 장르 탐색")
            if steer.get("aspect_tags"):
                bits.append("요소:" + ",".join(t for t in steer["aspect_tags"] if t))
            meta_line = (f"🧭 route: **{rt}**" + (f" · 🧭 {' / '.join(bits)}" if bits else "")
                         + (f" · 제약완화: {relaxed}" if relaxed else ""))
            st.caption(meta_line)
            recs = (res.get("filtered") or res.get("candidates") or [])[:int(k)]
            if recs:
                with st.expander("추천 목록 + '봤어요'(메모리)"):
                    for a in recs:
                        c1, c2 = st.columns([4, 1])
                        c1.write(appid2title.get(a, str(a)))
                        if c2.button("봤어요", key=f"seen_{len(ss.messages)}_{a}"):
                            ss.played.add(a)
            ss.messages.append({"role": "assistant", "content": resp + "\n\n" + meta_line})
