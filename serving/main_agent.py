"""Streamlit entry — hybrid game-recommendation AGENT.

Run:  streamlit run serving/main_agent.py

Product framing (user directive 2026-07-22): visitors bring their own Steam ID
(or just chat); recommendations come back as CARDS with honest provenance —
which of YOUR games drove each pick (EASE linear decomposition) and the traits
they share. No tech-stack manual, no internal route jargon in the UI.
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
# Streamlit Community Cloud exposes secrets via st.secrets — mirror into env
# so the whole stack keeps reading os.environ (no-op locally / on other hosts)
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str) and _k not in os.environ:
            os.environ[_k] = _v
except Exception:
    pass

from pipeline.game_rec.agent.ease_recommender import EASERecommender  # noqa: E402
from pipeline.game_rec.agent.tools import CatalogMeta  # noqa: E402
from pipeline.game_rec.agent.steam_library import get_owned_games, proxy_library  # noqa: E402
from serving.agent_graph import build_agentic_graph  # noqa: E402
from serving.bootstrap import ensure_ease_artifact  # noqa: E402
from serving.llm_guard import build_guarded_llm  # noqa: E402

DATA = str(ROOT / "serving" / "data")
# demo-user picker needs the local crawl DB — absent on cloud deploys,
# where visitors bring their own Steam ID instead (ToU: user data never ships)
HAS_LOCAL_DB = (ROOT / "data_collection" / "steam.db").exists()

# 5 real routes (+constraints woven into the phrasing, not a fake 6th route)
EXAMPLES = [
    "내게 맞는 게임 추천해줘",
    "엘든링 같은 게임",
    "안 해본 새로운 장르로 색다른 거",
    "나랑 친구 둘 다 좋아할 게임",
    "2만원 이하 협동 게임",
    "차분하고 분위기 좋은 인디 게임",
]
DEMO_SEEDS = [0, 1, 2, 3, 5, 7]
ROUTE_LABEL = {
    "library": "내 라이브러리 개인화", "seed": "비슷한 게임 찾기",
    "multi_entity": "나 + 친구 함께", "explore": "새로운 취향 탐색",
    "anonymous": "취향 설명 추천", "general": "일반 대화",
}
CONS_LABEL = {"coop": "협동", "multiplayer": "멀티플레이", "single_player": "싱글플레이",
              "korean": "한국어", "free": "무료", "max_price": "가격 상한",
              "released_after": "출시 시기"}

st.set_page_config(page_title="게임 추천 에이전트", page_icon="🎮", layout="centered")


@st.cache_resource(show_spinner="추천 엔진 로딩 중... (첫 기동은 모델 다운로드로 1~2분 걸립니다)")
def _load():
    ensure_ease_artifact(DATA)  # cloud boot: 345MB tensor from the HF model repo
    cf = EASERecommender()  # P6-confirmed serving ranker (EASE l100 x pctl_game)
    meta = CatalogMeta(DATA)
    llm = build_guarded_llm(DATA)  # key optional: without it the graph degrades, not dies
    graph = build_agentic_graph(cf, meta, llm, DATA)
    import pandas as pd
    df = pd.read_csv(f"{DATA}/steam_games_tags.csv")
    titles = dict(zip(df["appid"].astype(int), df["game_title"].astype(str)))
    tags = dict(zip(df["appid"].astype(int), df["tags"].astype(str)))
    return graph, titles, tags, llm


@st.cache_data(show_spinner=False)
def _demo_lib(seed: int) -> dict:
    return proxy_library(seed=int(seed))


graph, appid2title, appid2tags, llm_guard = _load()
ss = st.session_state
ss.setdefault("library", {})
ss.setdefault("friend_library", {})
ss.setdefault("played", set())
ss.setdefault("messages", [])
ss.setdefault("pending", None)


def _titles(lib, n=6):
    return ", ".join(appid2title.get(a, str(a)) for a in list(lib)[:n])


# no-LLM policy (user decision 2026-07-22): without NL understanding the app
# serves ONLY Steam-ID library personalization — everything else is guided off
llm_off = (not llm_guard.has_llm) or llm_guard.exhausted()

# ---------------- sidebar: my library ----------------
with st.sidebar:
    st.header("🎮 내 취향 불러오기")
    if llm_off:
        st.info("🔇 AI 자연어 이해가 꺼져 있습니다 (무료 쿼터 소진 또는 미설정). "
                "지금은 **Steam ID 라이브러리 기반 개인화 추천만** 동작합니다.")
    if HAS_LOCAL_DB:  # local dev only: the crawl DB never ships with the deployed app
        st.caption("데모 유저 선택 — 여러 명이면 첫 번째=나, 나머지=친구(다중주체).")
        picked = st.multiselect("데모 유저", DEMO_SEEDS,
                                format_func=lambda s: f"유저 #{s}", default=[])
        if st.button("선택 유저 불러오기", use_container_width=True, type="primary"):
            libs = [_demo_lib(s) for s in picked] if picked else []
            if not libs:
                ss.library, ss.friend_library = {}, {}
                st.warning("유저를 1명 이상 선택하세요.")
            elif len(libs) == 1:
                ss.library, ss.friend_library = dict(libs[0]), {}
                st.success(f"라이브러리 {len(ss.library)}개 게임 로드")
            else:
                ss.library = dict(libs[0])
                fr = {}
                for L in libs[1:]:
                    fr.update(L)
                ss.friend_library = fr
                st.success(f"나 {len(ss.library)} + 친구 {len(ss.friend_library)} 게임")
    else:
        st.caption("**Steam ID를 입력하면 내 플레이 기록 기반 개인화 추천**을 받습니다. "
                   "공개 프로필이어야 하며, 서버에 저장되지 않습니다.")

    with st.expander("🔑 Steam ID로 불러오기", expanded=not HAS_LOCAL_DB):
        sid = st.text_input("내 Steam ID (17자리 숫자)")
        if st.button("내 라이브러리 불러오기", use_container_width=True,
                     type="primary" if not HAS_LOCAL_DB else "secondary") and sid:
            try:
                ss.library = get_owned_games(sid.strip(), DATA)
                st.success(f"{len(ss.library)}개 게임 로드")
            except Exception as e:
                st.error(f"실패: {e}")
        fid = st.text_input("친구 Steam ID (함께 할 게임 찾기)")
        if st.button("친구 라이브러리 불러오기", use_container_width=True) and fid:
            try:
                ss.friend_library = get_owned_games(fid.strip(), DATA)
                st.success(f"친구 {len(ss.friend_library)}개 게임 로드")
            except Exception as e:
                st.error(f"실패: {e}")

    if ss.library:
        st.caption("🧑 내 라이브러리: " + _titles(ss.library) + " …")
    if ss.friend_library:
        st.caption("👤 친구: " + _titles(ss.friend_library) + " …")
    k = st.slider("추천 개수", 3, 10, 5)
    if ss.played:
        st.caption(f"🚫 제외 목록: {len(ss.played)}개 게임")


# ---------------- main ----------------
st.title("🎮 게임 추천 에이전트")
st.caption("2만 명의 실제 Steam 플레이 데이터로 학습한 엔진이 당신의 라이브러리를 읽고 "
           "다음 게임을 찾아드립니다. 각 추천에는 **어떤 게임 때문에 추천됐는지** 근거가 붙습니다.")

if not ss.messages:
    with st.container(border=True):
        st.markdown("**이렇게 물어보세요** — 눌러서 바로 실행")
        cols = st.columns(2)
        for i, p in enumerate(EXAMPLES):
            if cols[i % 2].button(p, key=f"ex_{i}", use_container_width=True):
                ss.pending = p


def _card(a: int, prov: dict | None):
    title = appid2title.get(a, str(a))
    tag_str = " · ".join(t.strip() for t in (appid2tags.get(a) or "").split(",")[:4] if t.strip())
    with st.container(border=True):
        head = f"**{title}**"
        if tag_str:
            head += f"  \n:gray[{tag_str}]"
        st.markdown(head)
        if prov and prov.get("by"):
            why = "🧩 **" + " · ".join(prov["by"]) + "** 를 플레이한 취향에서 나온 추천"
            if prov.get("tags"):
                why += f" — 공통 결: {', '.join(prov['tags'])}"
            st.caption(why)


# render conversation (recs live IN history so button clicks don't erase them)
last_rec_idx = max((i for i, m in enumerate(ss.messages) if m.get("recs")), default=None)
for i, m in enumerate(ss.messages):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] != "assistant":
            continue
        if m.get("meta"):
            st.caption(m["meta"])
        recs = m.get("recs") or []
        prov = m.get("prov") or {}
        for a in recs:
            _card(a, prov.get(a) or prov.get(str(a)))
        if recs and i == last_rec_idx:
            opts = {appid2title.get(a, str(a)): a for a in recs}
            sel = st.multiselect("이미 해봤거나 빼고 싶은 게임 (여러 개 선택 가능)",
                                 list(opts), key=f"skip_{i}")
            if sel and st.button("선택한 게임을 다음 추천에서 제외", key=f"skip_btn_{i}"):
                for t in sel:
                    ss.played.add(opts[t])
                st.toast(f"{len(sel)}개 게임을 다음 추천부터 제외합니다 ✅")


# ---------------- run (typed input or example chip) ----------------
typed = st.chat_input("예: 협동되고 한국어 지원 / 엘든링 같은 거 / 새로운 장르 추천")
query = ss.pending or typed
ss.pending = None

if query and llm_off and not ss.library:
    # no-LLM + no library: nothing meaningful can run — guide, don't pretend
    ss.messages.append({"role": "user", "content": query})
    ss.messages.append({"role": "assistant", "content":
                        "🔇 지금은 AI 자연어 이해가 꺼져 있어 채팅 요청을 해석할 수 없습니다. "
                        "왼쪽에서 **Steam ID로 라이브러리를 불러오면** 플레이 기록 기반 "
                        "개인화 추천은 정상 동작합니다."})
    st.rerun()
elif query:
    ss.messages.append({"role": "user", "content": query})
    with st.spinner("취향 분석 중..."):
        state = {"user_query": query, "k": int(k), "played": list(ss.played),
                 "library": dict(ss.library), "friend_library": dict(ss.friend_library)}
        res = graph.invoke(state)
    rt = res.get("request_type")
    steer = res.get("steer") or {}
    bits = [ROUTE_LABEL.get(rt, "")]
    if steer.get("novelty_beta"):
        bits.append("평소 취향에서 의도적으로 벗어난 탐색")
    if steer.get("aspect_tags"):
        bits.append("강조 요소: " + ", ".join(t for t in steer["aspect_tags"] if t))
    relaxed = res.get("relaxed") or []
    if relaxed:
        bits.append("조건 완화: " + ", ".join(CONS_LABEL.get(r, str(r)) for r in relaxed))
    if llm_off:
        bits.append("🔇 무-LLM 모드 — 라이브러리 개인화로 처리")
    ss.messages.append({
        "role": "assistant",
        "content": res.get("response", "추천을 생성하지 못했습니다."),
        "recs": (res.get("filtered") or res.get("candidates") or [])[:int(k)],
        "prov": res.get("provenance") or {},
        "meta": " · ".join(b for b in bits if b),
    })
    st.rerun()
