"""Streamlit UI for the recommendation agent.

All Streamlit calls live here. `app.py` is a thin entry point that wires
the recommender + LLM + compiled graph into these renderers.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from langchain.schema.messages import HumanMessage, SystemMessage, AIMessage


def render_sidebar() -> dict:
    """Sidebar weight sliders (3 axes) + preset buttons.

    Returns the dict consumed by rerank_candidates / rerank_node:
    {"relevance", "diversity", "novelty"} each 0-10.

    Note: Serendipity slider was removed (M11) — it was redundant with
    Novelty (both popularity-based). Relevance + Novelty combination
    already covers the "niche but relevant" effect naturally.
    """
    from pipeline.game_rec.config import load_config
    presets = load_config()["rerank"]["presets"]

    # session_state holds the live slider values; presets just update them
    defaults = presets["beginner"]
    for k in ("relevance", "diversity", "novelty"):
        st.session_state.setdefault(f"w_{k}", defaults.get(k, 5))

    with st.sidebar:
        st.header("재정렬 가중치")
        st.caption("0-10 점수. 3개 신호 (관련도/다양성/새로움) 를 어떻게 균형 잡을지 정합니다. Diversity/Novelty는 5가 중립.")

        st.markdown("**프리셋**")
        c1, c2, c3 = st.columns(3)
        if c1.button("입문자", use_container_width=True):
            _apply_preset(presets["beginner"])
        if c2.button("균형", use_container_width=True):
            _apply_preset(presets["balanced"])
        if c3.button("헤비", use_container_width=True):
            _apply_preset(presets["heavy"])

        st.markdown("---")
        weights = {
            "relevance":   st.slider("Relevance — 쿼리 일치", 0, 10, key="w_relevance"),
            "diversity":   st.slider("Diversity — 다양성",     0, 10, key="w_diversity"),
            "novelty":     st.slider("Novelty — 새로움",       0, 10, key="w_novelty"),
        }
        return weights


def _apply_preset(preset: dict) -> None:
    """Sync session state with a preset's values, then rerun for redraw."""
    for k in ("relevance", "diversity", "novelty"):
        if k in preset:
            st.session_state[f"w_{k}"] = preset[k]
    st.rerun()


def render_history(messages: list) -> None:
    """Replay prior conversation turns."""
    for msg in messages:
        if isinstance(msg, AIMessage):
            st.chat_message("assistant").write(msg.content)
        elif isinstance(msg, HumanMessage):
            st.chat_message("user").write(msg.content)
        elif isinstance(msg, SystemMessage):
            st.chat_message("assistant").write(msg.content)


def _render_node_event(node_name: str, node_state: dict, latest_state: dict | None, recommender) -> None:
    """Inside the per-node expander, show the most useful debug surface."""
    if node_name == "parser_node":
        st.markdown("LLM이 사용자의 쿼리를 분석하여 추천 모드와 키워드를 추출합니다.")
        st.json(node_state.get('parsed_json', {}))

    elif node_name == "normalizer_node":
        st.markdown("쿼리에 포함된 게임 이름이 데이터베이스에 있는지 확인하고 표준화합니다.")
        if latest_state:
            st.write("**:red[변경 전]**", latest_state.get('parsed_json', {}))
        st.write("**:blue[변경 후]**", node_state.get('parsed_json', {}))

    elif node_name in ("similar_node", "vibe_node", "hybrid_node"):
        st.markdown(f"`{node_name}`에 따라 후보 게임 목록을 생성합니다.")
        expanded_tags = node_state.get('parsed_json', {}).get('target_tags', [])
        if expanded_tags:
            st.markdown("**확장된 타겟 태그 (name, weight)**")
            st.json(expanded_tags)
        else:
            st.caption("확장된 태그 없음")

        candidate_ids = node_state.get('candidate_appids', [])
        st.write("후보 AppIDs:", candidate_ids)
        if candidate_ids:
            df = recommender.games_df.loc[candidate_ids]
            st.dataframe(df[['game_title', 'tags']])

    elif node_name == "rerank_node":
        st.markdown("후보 게임 목록을 사용자가 설정한 가중치에 따라 재정렬하여 최종 5개 게임을 선택합니다.")
        st.dataframe(node_state.get('final_results'))

    elif node_name == "response_generator_node":
        st.markdown("최종 추천 목록을 바탕으로 자연스러운 추천사를 생성합니다.")
        st.info(node_state.get('final_results'))

    elif node_name == "general_node":
        st.markdown("일반적인 대화형 응답을 생성합니다.")
        st.info(node_state.get('final_results'))


def stream_and_render(app_graph, graph_input: dict, recommender) -> dict | None:
    """Stream the graph, render each node's trace, return final state."""
    executed_nodes: list[str] = []
    latest_state: dict | None = None

    with st.status("추천 파이프라인 실행 중...", expanded=True) as status_container:
        for event in app_graph.stream(graph_input):
            for node_name, node_state in event.items():
                executed_nodes.append(node_name)
                path_str = " -> ".join(f"`{node}`" for node in executed_nodes)
                st.markdown(f"**현재 실행 노드:** `{node_name}`")
                st.markdown(f"**전체 실행 경로:** {path_str}")

                with st.expander(f"`{node_name}` 실행 결과 보기"):
                    _render_node_event(node_name, node_state, latest_state, recommender)

                latest_state = node_state
                st.markdown("---")

        status_container.update(label="추천 완료!", state="complete", expanded=False)

    return latest_state


def render_final_response(final_state: dict | None) -> None:
    """Append the assistant's final message to session history and render it."""
    if final_state is None:
        with st.chat_message("assistant"):
            st.error("추천을 생성하지 못했습니다 (그래프가 완료되지 않음).")
        return

    response_content = final_state.get('final_results', "오류: 최종 응답을 생성하지 못했습니다.")

    with st.chat_message("assistant"):
        if isinstance(response_content, pd.DataFrame):
            st.markdown("### 최종 추천 게임 목록")
            st.dataframe(response_content)
            st.session_state.messages.append(
                AIMessage(content=response_content.to_markdown(index=False))
            )
        else:
            if isinstance(response_content, list):
                response_content = '\n'.join(map(str, response_content))
            st.markdown(response_content)
            st.session_state.messages.append(AIMessage(content=str(response_content)))
