"""Interactive 3D tag graph with bloom, dark gradient, search, and side panel.

Self-contained HTML/JS — Streamlit only embeds. All interactions (search,
cluster filter, click → side panel) happen inside the iframe so we avoid
Streamlit ↔ JS round-trips.
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


st.set_page_config(page_title="태그 그래프 3D", layout="wide")


@st.cache_data(show_spinner=False)
def get_graph():
    return load_graph(top_k_games=10, neighbor_k=6)


graph = get_graph()


# Build JS payload — embed top_games + n_games + cluster directly
js_nodes = [
    {
        "id": n["id"],
        "color": n["color"],
        "cluster": int(n["cluster"]),
        "cluster_name": n.get("cluster_name", f"Cluster {n['cluster']}"),
        "size": float(n["size"]),
        "n_games": int(n["n_games"]),
        "top_games": list(n["top_games"]),
    }
    for n in graph["nodes"]
]
js_links = [
    {
        "source": e["source"],
        "target": e["target"],
        "weight": float(e.get("weight", 0.5)),
    }
    for e in graph["edges"]
]

unique_clusters = sorted({n["cluster"] for n in js_nodes})
cluster_meta = {}
for n in js_nodes:
    cluster_meta.setdefault(n["cluster"], {"color": n["color"], "name": n["cluster_name"]})

data_json = json.dumps({
    "nodes": js_nodes,
    "links": js_links,
    "clusters": [
        {
            "id": c,
            "color": cluster_meta.get(c, {}).get("color", "#888"),
            "name": cluster_meta.get(c, {}).get("name", f"Cluster {c}"),
        }
        for c in unique_clusters
    ],
})


HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {
    margin: 0; padding: 0; overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Pretendard, Roboto, sans-serif;
    color: #e8eaf0;
    background: #05070d;
  }
  #graph-wrap {
    position: relative;
    width: 100%; height: 780px;
    background:
      radial-gradient(ellipse at 50% 40%, #0d1530 0%, #06080f 55%, #02030a 100%);
    overflow: hidden;
  }
  #graph { width: 100%; height: 100%; }

  /* Search bar — top-left */
  #search-box {
    position: absolute;
    top: 18px; left: 18px;
    background: rgba(15, 20, 35, 0.78);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 8px 10px;
    z-index: 10;
    display: flex; align-items: center; gap: 8px;
    box-shadow: 0 6px 22px rgba(0,0,0,0.45);
  }
  #search-input {
    background: transparent;
    border: none; outline: none;
    color: #e8eaf0;
    font-size: 13px;
    width: 220px;
  }
  #search-input::placeholder { color: rgba(232,234,240,0.4); }
  #search-icon {
    width: 14px; height: 14px;
    opacity: 0.55;
  }

  /* Controls — top-right */
  #controls {
    position: absolute;
    top: 18px; right: 18px;
    background: rgba(15, 20, 35, 0.78);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 10px 12px;
    z-index: 10;
    display: flex; flex-direction: column; gap: 8px;
    font-size: 12px;
    box-shadow: 0 6px 22px rgba(0,0,0,0.45);
  }
  .ctl-row {
    display: flex; align-items: center; gap: 8px;
    cursor: pointer; user-select: none;
  }
  .ctl-row input { accent-color: #6ea8ff; }
  .ctl-divider { height: 1px; background: rgba(255,255,255,0.06); margin: 4px 0; }
  .cluster-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 11px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
    cursor: pointer; user-select: none;
    transition: opacity 0.15s;
  }
  .cluster-dot {
    width: 8px; height: 8px; border-radius: 50%;
    box-shadow: 0 0 6px currentColor;
  }
  .cluster-pill.off { opacity: 0.35; }

  /* Side panel — right */
  #side-panel {
    position: absolute;
    top: 18px; right: 18px;
    width: 320px;
    max-height: 720px;
    overflow-y: auto;
    background: rgba(10, 14, 26, 0.92);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
    padding: 18px;
    z-index: 20;
    display: none;
    box-shadow: 0 12px 40px rgba(0,0,0,0.6);
  }
  #side-panel.open { display: block; }
  #side-close {
    position: absolute; top: 10px; right: 12px;
    background: transparent; border: none; color: rgba(255,255,255,0.55);
    cursor: pointer; font-size: 18px;
  }
  #side-close:hover { color: #fff; }
  #side-panel h3 {
    margin: 0 0 4px; font-size: 18px; letter-spacing: 0.3px;
  }
  .cluster-tag {
    display: inline-flex; align-items: center; gap: 6px;
    margin-top: 4px; padding: 3px 10px;
    border-radius: 12px;
    background: rgba(255,255,255,0.05);
    font-size: 11px;
    color: rgba(232,234,240,0.85);
  }
  #side-stats { margin: 12px 0; font-size: 12px; color: rgba(232,234,240,0.6); }
  .panel-section { margin-top: 16px; }
  .panel-section h4 {
    margin: 0 0 8px;
    font-size: 11px; text-transform: uppercase; letter-spacing: 1.2px;
    color: rgba(232,234,240,0.5);
    font-weight: 600;
  }
  .game-item, .neigh-item {
    padding: 6px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    font-size: 13px;
    color: rgba(232,234,240,0.92);
  }
  .game-item:last-child, .neigh-item:last-child { border-bottom: none; }
  .neigh-item {
    cursor: pointer;
    transition: color 0.12s;
  }
  .neigh-item:hover { color: #6ea8ff; }
  .neigh-rank {
    display: inline-block; width: 18px;
    color: rgba(232,234,240,0.4); font-size: 11px;
  }

  /* Tooltip — node hover */
  #tooltip {
    position: absolute;
    pointer-events: none;
    background: rgba(10, 14, 26, 0.95);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
    color: #e8eaf0;
    z-index: 30;
    display: none;
    box-shadow: 0 6px 22px rgba(0,0,0,0.5);
    max-width: 260px;
  }
  #tooltip b { color: #fff; font-size: 13px; }
  #tooltip .sub { color: rgba(232,234,240,0.55); font-size: 11px; margin-top: 2px; }

  /* Caption */
  #caption {
    position: absolute;
    bottom: 12px; left: 18px;
    font-size: 11px;
    color: rgba(232,234,240,0.4);
    z-index: 5;
  }
</style>
<script src="https://unpkg.com/three@0.160.1/build/three.min.js"></script>
<script src="https://unpkg.com/three@0.160.1/examples/js/postprocessing/EffectComposer.js"></script>
<script src="https://unpkg.com/three@0.160.1/examples/js/postprocessing/RenderPass.js"></script>
<script src="https://unpkg.com/three@0.160.1/examples/js/postprocessing/ShaderPass.js"></script>
<script src="https://unpkg.com/three@0.160.1/examples/js/postprocessing/UnrealBloomPass.js"></script>
<script src="https://unpkg.com/three@0.160.1/examples/js/shaders/LuminosityHighPassShader.js"></script>
<script src="https://unpkg.com/three@0.160.1/examples/js/shaders/CopyShader.js"></script>
<script src="https://unpkg.com/3d-force-graph@1.74.4/dist/3d-force-graph.min.js"></script>
</head>
<body>
<div id="graph-wrap">
  <!-- Starfield canvas overlay (cheap, behind graph) -->
  <canvas id="stars" width="1600" height="800"
          style="position:absolute;inset:0;pointer-events:none;opacity:0.55;"></canvas>

  <div id="graph"></div>

  <div id="search-box">
    <svg id="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="11" cy="11" r="7"/>
      <line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
    <input id="search-input" placeholder="태그 검색 (e.g. souls-like)" />
  </div>

  <div id="controls">
    <label class="ctl-row"><input type="checkbox" id="opt-rotate"/> 자동 회전</label>
    <label class="ctl-row"><input type="checkbox" id="opt-labels"/> 항상 레이블</label>
    <div class="ctl-divider"></div>
    <div style="font-size:10px;color:rgba(232,234,240,0.5);text-transform:uppercase;letter-spacing:1px;">클러스터</div>
    <div id="cluster-filters" style="display:flex;flex-wrap:wrap;gap:5px;max-width:240px;"></div>
  </div>

  <div id="side-panel">
    <button id="side-close">&times;</button>
    <h3 id="side-title">tag</h3>
    <div class="cluster-tag" id="side-cluster"></div>
    <div id="side-stats"></div>
    <div class="panel-section">
      <h4>인기 게임 Top 10</h4>
      <div id="side-games"></div>
    </div>
    <div class="panel-section">
      <h4>가까운 이웃 태그</h4>
      <div id="side-neighbors"></div>
    </div>
  </div>

  <div id="tooltip"></div>
  <div id="caption">PPMI + Truncated SVD 128차원 임베딩 · k-NN 그래프 · drag · scroll · click</div>
</div>

<script>
  const RAW = __DATA__;

  // -------- Starfield background --------
  (function drawStars() {
    const c = document.getElementById('stars');
    const ctx = c.getContext('2d');
    function resize() {
      c.width = c.clientWidth || window.innerWidth;
      c.height = c.clientHeight || 800;
      ctx.fillStyle = 'transparent';
      ctx.clearRect(0,0,c.width,c.height);
      for (let i=0;i<260;i++) {
        const x = Math.random()*c.width;
        const y = Math.random()*c.height;
        const r = Math.random()*1.1 + 0.2;
        const a = Math.random()*0.55 + 0.2;
        ctx.fillStyle = `rgba(180,200,255,${a})`;
        ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2); ctx.fill();
      }
    }
    resize();
    window.addEventListener('resize', resize);
  })();

  // -------- Build adjacency (for side panel neighbors) --------
  const adj = {};
  RAW.links.forEach(l => {
    const s = (typeof l.source === 'object') ? l.source.id : l.source;
    const t = (typeof l.target === 'object') ? l.target.id : l.target;
    (adj[s] = adj[s] || []).push({tag: t, w: l.weight});
    (adj[t] = adj[t] || []).push({tag: s, w: l.weight});
  });
  for (const k in adj) adj[k].sort((a,b) => b.w - a.w);

  // -------- Active filter state --------
  const activeClusters = new Set(RAW.clusters.map(c => c.id));
  let searchHit = null;  // node id
  let hoverNode = null;  // node currently hovered

  const clusterNameMap = {};
  RAW.clusters.forEach(c => { clusterNameMap[c.id] = c.name; });

  // -------- 3D Force Graph --------
  const el = document.getElementById('graph');
  const Graph = ForceGraph3D()(el)
    .backgroundColor('rgba(0,0,0,0)')   // transparent (let CSS gradient + stars show)
    .graphData(RAW)
    .nodeId('id')
    .nodeColor(n => {
      if (!activeClusters.has(n.cluster)) return 'rgba(80,80,90,0.15)';
      // Hover takes priority — bright self + neighbors, dim the rest
      if (hoverNode) {
        if (n.id === hoverNode.id) return n.color;
        const isNeighbor = adj[hoverNode.id]?.some(x => x.tag === n.id);
        return isNeighbor ? n.color : n.color + '22';
      }
      if (searchHit && n.id !== searchHit && !adj[searchHit]?.some(x=>x.tag===n.id)) {
        return n.color + '40';
      }
      return n.color;
    })
    .nodeOpacity(0.95)
    .nodeRelSize(3.2)
    .nodeVal(n => 1.0 + (n.size || 0) * 12)
    .linkColor(l => {
      const sId = (typeof l.source==='object') ? l.source.id : l.source;
      const tId = (typeof l.target==='object') ? l.target.id : l.target;
      const sN = nodeById(sId), tN = nodeById(tId);
      if (!sN || !tN) return 'rgba(120,140,200,0.10)';
      if (!activeClusters.has(sN.cluster) || !activeClusters.has(tN.cluster))
        return 'rgba(120,140,200,0.04)';
      // Hover takes priority: only links touching hoverNode are bright
      if (hoverNode) {
        const connected = sId === hoverNode.id || tId === hoverNode.id;
        if (!connected) return 'rgba(120,140,200,0.04)';
        return `rgba(255,210,210,${(0.5 + l.weight*0.5).toFixed(3)})`;
      }
      const alpha = 0.10 + l.weight * 0.55;
      return `rgba(130,170,240,${alpha.toFixed(3)})`;
    })
    .linkWidth(l => {
      if (hoverNode) {
        const sId = (typeof l.source==='object') ? l.source.id : l.source;
        const tId = (typeof l.target==='object') ? l.target.id : l.target;
        if (sId === hoverNode.id || tId === hoverNode.id) return 1.5 + l.weight * 1.8;
      }
      return 0.25 + (l.weight || 0.5) * 1.4;
    })
    .linkCurvature(0.18)
    .linkDirectionalParticles(0)
    .nodeThreeObject(n => {
      // Sphere with subtle emissive glow (drives bloom)
      const geo = new THREE.SphereGeometry(1.6 + (n.size||0)*1.4, 14, 14);
      const mat = new THREE.MeshBasicMaterial({
        color: new THREE.Color(n.color),
        transparent: true,
        opacity: 0.95,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.userData.baseColor = n.color;
      return mesh;
    })
    .nodeThreeObjectExtend(false)
    .enableNodeDrag(true)
    .showNavInfo(false)
    .onNodeHover(node => {
      el.style.cursor = node ? 'pointer' : 'grab';
      hoverNode = node || null;
      if (node) showTooltip(node);
      else hideTooltip();
      // trigger redraw of colors/widths to reflect hover
      Graph.nodeColor(Graph.nodeColor());
      Graph.linkColor(Graph.linkColor());
      Graph.linkWidth(Graph.linkWidth());
    })
    .onNodeClick(node => {
      flyTo(node);
      openPanel(node);
    });

  // Charge tweak — looser layout for breathing
  Graph.d3Force('charge').strength(-160);
  Graph.d3Force('link').distance(34);

  // -------- Bloom postprocessing --------
  setTimeout(() => {
    try {
      const renderer = Graph.renderer();
      const scene = Graph.scene();
      const camera = Graph.camera();
      const w = el.clientWidth, h = el.clientHeight;
      const bloom = new THREE.UnrealBloomPass(
        new THREE.Vector2(w, h), 0.85, 0.55, 0.18
      );
      const composer = new THREE.EffectComposer(renderer);
      composer.addPass(new THREE.RenderPass(scene, camera));
      composer.addPass(bloom);
      Graph.postProcessingComposer().addPass(bloom);
    } catch (e) { console.warn('bloom init failed', e); }
  }, 200);

  // -------- Node lookup --------
  let nodeMap = null;
  function nodeById(id) {
    if (!nodeMap) {
      nodeMap = {};
      RAW.nodes.forEach(n => { nodeMap[n.id] = n; });
    }
    return nodeMap[id];
  }

  // -------- Camera fly --------
  function flyTo(node) {
    const dist = 90;
    const r = 1 + dist / Math.hypot(node.x||1, node.y||1, node.z||1);
    Graph.cameraPosition(
      { x: node.x*r, y: node.y*r, z: node.z*r }, node, 1400
    );
  }

  // -------- Tooltip --------
  const tip = document.getElementById('tooltip');
  function showTooltip(node) {
    const cname = node.cluster_name || `Cluster ${node.cluster}`;
    const nbs = (adj[node.id] || []).slice(0, 5).map(n => n.tag);
    const nbsHtml = nbs.length
      ? `<div style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.10);font-size:11px;color:rgba(255,210,210,0.85);">↳ ${nbs.join(' · ')}</div>`
      : '';
    tip.innerHTML =
      `<b>${node.id}</b>` +
      `<div class="sub">게임 ${node.n_games?.toLocaleString()||0} · ${cname}</div>` +
      nbsHtml;
    tip.style.display = 'block';
  }
  function hideTooltip() { tip.style.display = 'none'; }
  document.addEventListener('mousemove', e => {
    const rect = el.getBoundingClientRect();
    tip.style.left = (e.clientX - rect.left + 14) + 'px';
    tip.style.top  = (e.clientY - rect.top  + 14) + 'px';
  });

  // -------- Side panel --------
  const panel = document.getElementById('side-panel');
  document.getElementById('side-close').addEventListener('click', () => {
    panel.classList.remove('open');
    document.getElementById('controls').style.display = 'flex';
  });
  function openPanel(node) {
    document.getElementById('side-title').textContent = node.id;
    const ct = document.getElementById('side-cluster');
    const cname = node.cluster_name || clusterNameMap[node.cluster] || `Cluster ${node.cluster}`;
    ct.innerHTML =
      `<span class="cluster-dot" style="background:${node.color};color:${node.color};"></span>` +
      cname;
    document.getElementById('side-stats').textContent =
      `이 태그를 가진 게임: ${(node.n_games||0).toLocaleString()}개`;

    const gamesEl = document.getElementById('side-games');
    if (node.top_games && node.top_games.length) {
      gamesEl.innerHTML = node.top_games.map((g,i) =>
        `<div class="game-item"><span class="neigh-rank">${i+1}</span>${g}</div>`
      ).join('');
    } else {
      gamesEl.innerHTML = '<div class="game-item" style="opacity:0.5;">데이터 없음</div>';
    }

    const nbEl = document.getElementById('side-neighbors');
    const nbs = (adj[node.id] || []).slice(0, 6);
    if (nbs.length) {
      nbEl.innerHTML = nbs.map((nb,i) => {
        const n2 = nodeById(nb.tag);
        const c = n2 ? n2.color : '#888';
        return `<div class="neigh-item" data-id="${nb.tag}">` +
               `<span class="neigh-rank">${i+1}</span>` +
               `<span class="cluster-dot" style="background:${c};color:${c};margin-right:8px;display:inline-block;vertical-align:middle;"></span>` +
               `${nb.tag} <span style="color:rgba(232,234,240,0.4);font-size:10px;margin-left:6px;">${(nb.w*100).toFixed(0)}%</span>` +
               `</div>`;
      }).join('');
      nbEl.querySelectorAll('.neigh-item').forEach(el2 => {
        el2.addEventListener('click', () => {
          const id = el2.dataset.id;
          const n2 = nodeById(id);
          if (n2) { flyTo(n2); openPanel(n2); }
        });
      });
    } else {
      nbEl.innerHTML = '<div class="neigh-item" style="opacity:0.5;">데이터 없음</div>';
    }

    panel.classList.add('open');
    document.getElementById('controls').style.display = 'none';
  }

  // -------- Cluster filter pills --------
  const cf = document.getElementById('cluster-filters');
  RAW.clusters.forEach(c => {
    const p = document.createElement('span');
    p.className = 'cluster-pill';
    p.dataset.cluster = c.id;
    p.title = c.name;
    p.innerHTML = `<span class="cluster-dot" style="background:${c.color};color:${c.color}"></span>${c.name}`;
    p.addEventListener('click', () => {
      if (activeClusters.has(c.id)) { activeClusters.delete(c.id); p.classList.add('off'); }
      else { activeClusters.add(c.id); p.classList.remove('off'); }
      Graph.nodeColor(Graph.nodeColor());
      Graph.linkColor(Graph.linkColor());
    });
    cf.appendChild(p);
  });

  // -------- Auto rotate toggle --------
  let rotate = false; let rotAngle = 0;
  document.getElementById('opt-rotate').addEventListener('change', e => {
    rotate = e.target.checked;
  });
  setInterval(() => {
    if (!rotate) return;
    rotAngle += 0.002;
    const r = 320;
    Graph.cameraPosition({
      x: r * Math.cos(rotAngle),
      y: 40,
      z: r * Math.sin(rotAngle),
    });
  }, 30);

  // -------- Label toggle --------
  document.getElementById('opt-labels').addEventListener('change', e => {
    if (e.target.checked) {
      Graph.nodeThreeObject(n => {
        const sprite = makeSprite(n.id, '#ffffff');
        const grp = new THREE.Group();
        const geo = new THREE.SphereGeometry(1.6 + (n.size||0)*1.4, 14, 14);
        const mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(n.color), transparent: true, opacity: 0.95 });
        grp.add(new THREE.Mesh(geo, mat));
        sprite.position.set(0, 4 + (n.size||0)*2.5, 0);
        grp.add(sprite);
        return grp;
      });
    } else {
      Graph.nodeThreeObject(n => {
        const geo = new THREE.SphereGeometry(1.6 + (n.size||0)*1.4, 14, 14);
        const mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(n.color), transparent: true, opacity: 0.95 });
        return new THREE.Mesh(geo, mat);
      });
    }
  });

  function makeSprite(text, color) {
    const cv = document.createElement('canvas');
    cv.width = 256; cv.height = 64;
    const cx = cv.getContext('2d');
    cx.font = '500 22px -apple-system, Segoe UI, Pretendard';
    cx.textAlign = 'center'; cx.textBaseline = 'middle';
    cx.shadowColor = 'rgba(0,0,0,0.85)'; cx.shadowBlur = 6;
    cx.fillStyle = color;
    cx.fillText(text, 128, 32);
    const tex = new THREE.CanvasTexture(cv);
    const mat = new THREE.SpriteMaterial({ map: tex, depthWrite: false });
    const sp = new THREE.Sprite(mat);
    sp.scale.set(28, 7, 1);
    return sp;
  }

  // -------- Search --------
  const si = document.getElementById('search-input');
  si.addEventListener('input', () => {
    const q = si.value.trim().toLowerCase();
    if (!q) { searchHit = null; Graph.nodeColor(Graph.nodeColor()); Graph.linkColor(Graph.linkColor()); return; }
    const hit = RAW.nodes.find(n => n.id.toLowerCase().includes(q));
    if (hit) { searchHit = hit.id; flyTo(hit); openPanel(hit); }
    Graph.nodeColor(Graph.nodeColor());
    Graph.linkColor(Graph.linkColor());
  });
</script>
</body>
</html>
"""

html = HTML_TEMPLATE.replace("__DATA__", data_json)
components.html(html, height=800, scrolling=False)
