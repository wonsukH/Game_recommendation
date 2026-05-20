"""Streamlit entry point for the game recommendation agent.

Thin wiring: load env, init recommender + LLM, build the LangGraph, then
hand off to the UI module for all rendering.
"""

import os

import streamlit as st
from dotenv import load_dotenv
from langchain_upstage import ChatUpstage
from langchain.schema.messages import HumanMessage, AIMessage

from rag.retriever import VectorBasedRecommender
from graph import build_graph
from ui import render_sidebar, render_history, stream_and_render, render_final_response


load_dotenv()

UPSTAGE_API_KEY = os.environ.get("UPSTAGE_API_KEY")
if not UPSTAGE_API_KEY:
    st.error("Upstage API 키가 필요합니다. .env 파일에 UPSTAGE_API_KEY를 설정해주세요.")
    st.stop()


@st.cache_resource
def init_recommender() -> VectorBasedRecommender:
    data_path = os.path.join(os.path.dirname(__file__), 'data')
    embedding_model = os.environ.get("UPSTAGE_EMBEDDING_MODEL", "solar-embedding-1-large")
    return VectorBasedRecommender(data_path=data_path, embedding_model=embedding_model)


@st.cache_resource
def init_llm() -> ChatUpstage:
    return ChatUpstage(api_key=UPSTAGE_API_KEY)


@st.cache_resource
def init_graph(_recommender: VectorBasedRecommender, _llm: ChatUpstage):
    # Underscored args tell Streamlit not to try hashing them.
    return build_graph(_recommender, _llm)


recommender = init_recommender()
llm = init_llm()
app_graph = init_graph(recommender, llm)

st.title("✨ 게임 추천 서비스")

user_weights = render_sidebar()

if "messages" not in st.session_state:
    st.session_state.messages = [AIMessage(content="안녕하세요! 어떤 게임을 추천해드릴까요?")]

render_history(st.session_state.messages)

if prompt := st.chat_input("질문을 입력하세요."):
    st.session_state.messages.append(HumanMessage(content=prompt))
    st.chat_message("user").write(prompt)

    with st.spinner("추천 중..."):
        try:
            graph_input = {"user_query": prompt, "rerank_weights": user_weights}
            final_state = stream_and_render(app_graph, graph_input, recommender)
            render_final_response(final_state)
        except Exception as e:
            st.error("그래프 실행 중 오류가 발생했습니다.")
            st.exception(e)
            st.session_state.messages.append(AIMessage(content=f"오류가 발생했습니다: {e}"))
