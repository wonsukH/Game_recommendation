"""Streamlit page: 3D force-directed tag graph (Obsidian 3D-style).

Uses vasturiano's `3d-force-graph` (three.js) embedded via streamlit
components. Same data as the 2D page; force layout runs in 3D.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "serving"))
from graph_data import load_graph  # noqa: E402


st.set_page_config(page_title="태그 그래프 (3D)", layout="wide")
st.title("태그 그래프 — 3D (force-directed)")
st.caption(
    "PPMI+SVD 128d 임베딩의 k-NN을 3D force-graph로. "
    "마우스 드래그로 회전, 휠 줌, 노드 hover 시 인기 게임 Top 5 표시."
)


@st.cache_data(show_spinner=False)
def get_graph():
    return load_graph(top_k_games=5, neighbor_k=5)


graph = get_graph()


# Build JS-friendly data
def _hover_html(node: dict) -> str:
    top = node["top_games"]
    if top:
        games = "<br>".join(f"&nbsp;&nbsp;{i+1}. {t}" for i, t in enumerate(top))
    else:
        games = "<i>인기 게임 데이터 없음</i>"
    return (
        f"<div style='background:#1a1a1a;color:#eee;padding:10px 14px;"
        f"border-radius:6px;font-family:sans-serif;font-size:13px;"
        f"max-width:280px;box-shadow:0 4px 12px rgba(0,0,0,0.4)'>"
        f"<b style='font-size:14px'>{node['id']}</b><br>"
        f"<span style='color:#888'>게임 수 {node['n_games']:,} · 클러스터 {node['cluster']}</span>"
        f"<br><br><b>인기 게임 Top 5</b><br>{games}"
        f"</div>"
    )


js_nodes = [
    {
        "id": n["id"],
        "name": n["id"],
        "color": n["color"],
        "val": 1 + n["size"] * 20,
        "hover": _hover_html(n),
        "cluster": n["cluster"],
    }
    for n in graph["nodes"]
]
js_links = [{"source": e["source"], "target": e["target"]} for e in graph["edges"]]

data_json = json.dumps({"nodes": js_nodes, "links": js_links})

st.markdown(
    f"**노드** {len(js_nodes)} · **엣지** {len(js_links)} — "
    "드래그=회전, 휠=줌, 노드 hover=정보, 노드 클릭=중심 이동"
)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; background: #0e1117; }
  #3d-graph { width: 100%; height: 720px; }
  .node-tooltip {
    position: absolute;
    pointer-events: none;
    z-index: 999;
  }
</style>
<script src="https://unpkg.com/three@0.160.1/build/three.min.js"></script>
<script src="https://unpkg.com/3d-force-graph@1.74.4/dist/3d-force-graph.min.js"></script>
</head>
<body>
<div id="3d-graph"></div>
<script>
  const graphData = __DATA__;

  const elem = document.getElementById('3d-graph');
  const Graph = ForceGraph3D()(elem)
    .backgroundColor('#0e1117')
    .graphData(graphData)
    .nodeLabel(node => node.hover)
    .nodeColor(node => node.color)
    .nodeVal(node => node.val)
    .nodeRelSize(4)
    .linkColor(() => 'rgba(180,180,180,0.25)')
    .linkOpacity(0.4)
    .linkWidth(0.5)
    .onNodeClick(node => {
      // Aim camera at node
      const distance = 120;
      const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);
      Graph.cameraPosition(
        { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
        node,
        1500
      );
    })
    .enableNodeDrag(true)
    .showNavInfo(false);

  // Light tweak
  Graph.d3Force('charge').strength(-120);
</script>
</body>
</html>
"""

html = HTML_TEMPLATE.replace("__DATA__", data_json)
components.html(html, height=740, scrolling=False)
