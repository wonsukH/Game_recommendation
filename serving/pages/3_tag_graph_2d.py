"""Streamlit page: 2D force-directed tag graph (Obsidian-style).

Nodes = tags, edges = top-k semantic neighbors (cosine sim in 128d PPMI
space). Force physics by vis.js (via streamlit-agraph). Drag nodes, zoom,
click for highlight. Hover shows tag name + top 5 popular games.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "serving"))
from graph_data import load_graph  # noqa: E402


st.set_page_config(page_title="태그 그래프 (2D)", layout="wide")
st.title("태그 그래프 — 2D (force-directed)")
st.caption(
    "PPMI+SVD 128d 임베딩에서 각 태그의 k-NN 이웃으로 그래프 구성. "
    "노드 위치는 force physics가 결정 (UMAP 좌표 사용 안 함). "
    "노드 크기 = 해당 태그를 가진 게임 수(log scale)."
)


@st.cache_data(show_spinner=False)
def get_graph():
    return load_graph(top_k_games=5, neighbor_k=5)


col_a, col_b, col_c = st.columns([1, 1, 1])
with col_a:
    physics_on = st.checkbox(
        "Physics 활성화 (force-directed)",
        value=True,
        help="기본 ON. 끄면 정적 circular layout으로 배치됨.",
    )
with col_b:
    show_labels = st.checkbox("라벨 항상 표시", value=False)
with col_c:
    min_neighbors = st.slider("노드 최소 연결 수 필터", 0, 5, 0,
                              help="고립 노드 숨기기")

graph = get_graph()


# Filter isolated nodes if user wants
node_degrees: dict[str, int] = {n["id"]: 0 for n in graph["nodes"]}
for e in graph["edges"]:
    node_degrees[e["source"]] = node_degrees.get(e["source"], 0) + 1
    node_degrees[e["target"]] = node_degrees.get(e["target"], 0) + 1

visible_ids = {n["id"] for n in graph["nodes"] if node_degrees[n["id"]] >= min_neighbors}


def _format_hover(node: dict) -> str:
    top = node["top_games"]
    if top:
        games_html = "<br>".join(f"&nbsp;&nbsp;{i+1}. {t}" for i, t in enumerate(top))
    else:
        games_html = "<i>인기 게임 데이터 없음</i>"
    return (
        f"<b>{node['id']}</b><br>"
        f"<span style='color:#888'>게임 수: {node['n_games']:,} · 클러스터: {node['cluster']}</span>"
        f"<br><br><b>인기 게임 Top 5</b><br>{games_html}"
    )


nodes_ag = []
for n in graph["nodes"]:
    if n["id"] not in visible_ids:
        continue
    # vis.js node sizing: 8 to 40
    size = 8 + n["size"] * 32
    nodes_ag.append(Node(
        id=n["id"],
        label=n["id"] if show_labels else "",
        size=size,
        color=n["color"],
        title=_format_hover(n),
        font={"size": 12, "color": "#eee"},
    ))

edges_ag = []
for e in graph["edges"]:
    if e["source"] in visible_ids and e["target"] in visible_ids:
        edges_ag.append(Edge(source=e["source"], target=e["target"], color="#444"))

config = Config(
    width="100%",
    height=720,
    directed=False,
    # Physics ON = force-directed simulation (Obsidian-style)
    # Physics OFF = freeze layout but allow drag (still draggable)
    staticGraph=False,
    staticGraphWithDragAndDrop=not physics_on,
    physics=physics_on,
    hierarchical=False,
    nodeHighlightBehavior=True,
    highlightColor="#F7A7A6",
    collapsible=False,
    node={"labelProperty": "label", "renderLabel": True},
    link={"highlightColor": "#666"},
    # D3 force params tuned to converge quickly into stable clusters
    d3={
        "gravity": -200,           # repulsion between nodes (more negative = spread out)
        "linkLength": 80,          # ideal edge length
        "linkStrength": 2,         # how strictly to honor link length
        "alphaTarget": 0,          # 0 = simulation will cool to rest
        "disableLinkForce": False,
    },
)

st.markdown(
    f"**노드** {len(nodes_ag)} · **엣지** {len(edges_ag)} — "
    "노드 클릭/드래그, 휠 줌, hover로 인기 게임 확인"
)

agraph(nodes=nodes_ag, edges=edges_ag, config=config)
