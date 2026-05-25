"""LangGraph workflow for the game recommendation agent.

Defines `GraphState` plus `build_graph(recommender, llm)` which returns a
compiled `StateGraph`. Resource injection (recommender, llm) happens via
closure rather than global state so the graph stays testable in
isolation from the Streamlit runtime.
"""

from __future__ import annotations

from typing import Any, TypedDict, List

import numpy as np
from langgraph.graph import StateGraph, END

from pipeline.game_rec.agent.nodes import (
    llm_parser_node,
    similar_node,
    vibe_node,
    hybrid_node,
    general_node,
    route_by_mode,
    generate_response_node,
    game_name_normalizer_node,
)


class GraphState(TypedDict, total=False):
    user_query: str
    parsed_json: dict
    rerank_weights: dict
    candidate_appids: List[int]
    query_vector: np.ndarray
    vibe_vector: np.ndarray   # hybrid 모드에서만 채워짐
    final_results: Any  # Can be DataFrame or final string


def build_graph(recommender, llm, top_n_rerank: int = 5):
    """Build and compile the LangGraph workflow.

    Args:
        recommender: VectorBasedRecommender with FAISS index ready.
        llm: ChatUpstage (or compatible) chat model.
        top_n_rerank: how many candidates the rerank node returns.

    Returns:
        A compiled CompiledGraph ready for `.stream(...)` / `.invoke(...)`.
    """

    def parser_node(state):
        return llm_parser_node(state, llm)

    def normalizer_node(state):
        return game_name_normalizer_node(state, recommender)

    def sim_node(state):
        return similar_node(state, recommender)

    def vib_node(state):
        return vibe_node(state, recommender)

    def hyb_node(state):
        return hybrid_node(state, recommender)

    def response_node(state):
        return generate_response_node(state, llm)

    def rerank_node(state: GraphState):
        appids = state['candidate_appids']
        query_vec = state['query_vector']
        weights = state['rerank_weights']
        vibe_vec = state.get('vibe_vector')   # hybrid에만 존재
        state['final_results'] = recommender.rerank_candidates(
            appids, query_vec, weights, top_n=top_n_rerank,
            vibe_vector=vibe_vec,
        )
        return state

    workflow = StateGraph(GraphState)
    workflow.add_node("parser_node", parser_node)
    workflow.add_node("normalizer_node", normalizer_node)
    workflow.add_node("similar_node", sim_node)
    workflow.add_node("vibe_node", vib_node)
    workflow.add_node("hybrid_node", hyb_node)
    workflow.add_node("rerank_node", rerank_node)
    workflow.add_node("general_node", general_node)
    workflow.add_node("response_generator_node", response_node)

    workflow.set_entry_point("parser_node")
    workflow.add_edge("parser_node", "normalizer_node")
    workflow.add_conditional_edges(
        "normalizer_node",
        route_by_mode,
        {
            "similar_node": "similar_node",
            "vibe_node": "vibe_node",
            "hybrid_node": "hybrid_node",
            "general_node": "general_node",
        },
    )
    workflow.add_edge('similar_node', 'rerank_node')
    workflow.add_edge('vibe_node', 'rerank_node')
    workflow.add_edge('hybrid_node', 'rerank_node')
    workflow.add_edge('rerank_node', 'response_generator_node')
    workflow.add_edge('general_node', END)
    workflow.add_edge('response_generator_node', END)

    return workflow.compile()
