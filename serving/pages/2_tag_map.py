"""Streamlit page: interactive tag semantic map.

Shows the 393+ Steam user-tags in 2D (UMAP projection of PPMI+SVD
embeddings). Hover for tag name + top-k semantic neighbors. Search a
game to highlight which tags it has.

This is the visual surface of what the recommender's "태그 의미" actually
captured. A beginner who's never heard of "Soulslike" can see it
clustered near Hardcore, Dark Fantasy, Difficult.

Generated artifacts come from
`pipeline.game_rec.index.tag_projection` (M6.1):
- outputs/tag_2d.npy
- outputs/tag_clusters.npy
- outputs/tag_neighbors.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
from scipy.sparse import load_npz

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from pipeline.game_rec.io import load_tag_vocab  # noqa: E402

DATA_DIR = REPO_ROOT / "serving" / "data"


st.set_page_config(page_title="태그 의미 지도", page_icon=None, layout="wide")
st.title("태그 의미 지도")
st.caption("Steam user-tag를 PPMI+SVD 임베딩(128d) + UMAP으로 2D 투영. 클러스터별로 색칠. 점에 hover 시 해당 태그의 의미적 이웃 (가까운 태그) Top 5 표시.")


@st.cache_data(show_spinner=False)
def load_projection():
    """Read pre-computed projection artifacts."""
    coords_path = DATA_DIR / "tag_2d.npy"
    clusters_path = DATA_DIR / "tag_clusters.npy"
    neighbors_path = DATA_DIR / "tag_neighbors.json"
    vocab_path = DATA_DIR / "tag_vocab.json"

    if not coords_path.exists():
        return None

    coords = np.load(coords_path)
    clusters = np.load(clusters_path) if clusters_path.exists() else np.zeros(len(coords), dtype=int)
    neighbors = (
        json.loads(neighbors_path.read_text(encoding="utf-8"))
        if neighbors_path.exists() else {}
    )
    tag_names = load_tag_vocab(vocab_path) if vocab_path.exists() else [str(i) for i in range(len(coords))]

    df = pd.DataFrame({
        "tag": tag_names,
        "x": coords[:, 0],
        "y": coords[:, 1],
        "cluster": clusters,
    })
    return df, neighbors


@st.cache_data(show_spinner=False)
def load_games_df():
    path = DATA_DIR / "steam_games_tags.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def load_top_games_per_tag(k: int = 5) -> dict[str, list[str]]:
    """Per tag, find top-k popular games that carry it.

    Uses X_game_tag_csr (binary game x tag) + game_popularity to rank,
    then maps row indices to game_title via index_maps + steam_games_tags.
    """
    x_path = DATA_DIR / "X_game_tag_csr.npz"
    pop_path = DATA_DIR / "game_popularity.npy"
    imap_path = DATA_DIR / "index_maps.json"
    games_path = DATA_DIR / "steam_games_tags.csv"

    if not all(p.exists() for p in [x_path, pop_path, imap_path, games_path]):
        return {}

    X = load_npz(x_path).tocsc()
    pop = np.load(pop_path).astype(float)
    imap = json.loads(imap_path.read_text(encoding="utf-8"))
    games = pd.read_csv(games_path)

    row2appid = imap.get("row2appid", {})
    if isinstance(row2appid, dict):
        ordered_appids = [
            v for _, v in sorted(((int(k_), v) for k_, v in row2appid.items()), key=lambda x: x[0])
        ]
    else:
        ordered_appids = list(row2appid)

    appid_to_title = dict(zip(games["appid"].astype(int), games["game_title"]))
    tag2idx = imap.get("tag2idx", {})

    out: dict[str, list[str]] = {}
    for tag_name, col_idx in tag2idx.items():
        col_idx = int(col_idx)
        if col_idx >= X.shape[1]:
            out[tag_name] = []
            continue
        game_rows = X[:, col_idx].indices
        if len(game_rows) == 0:
            out[tag_name] = []
            continue
        # Guard against popularity length mismatch
        valid_rows = game_rows[game_rows < len(pop)]
        if len(valid_rows) == 0:
            out[tag_name] = []
            continue
        order = np.argsort(pop[valid_rows])[::-1][:k]
        titles: list[str] = []
        for r in valid_rows[order]:
            if r < len(ordered_appids):
                appid = int(ordered_appids[r])
                titles.append(appid_to_title.get(appid, f"appid={appid}"))
        out[tag_name] = titles
    return out


data = load_projection()
if data is None:
    st.warning(
        "투영 데이터가 없습니다. 먼저 아래 명령으로 생성해주세요:\n\n"
        "```\npython -m pipeline.game_rec.index.tag_projection\n"
        "python scripts/sync_data.py\n```"
    )
    st.stop()

tag_df, neighbors = data
games_df = load_games_df()


def _format_neighbors(tag_name: str, k: int = 5) -> str:
    """Format top-k semantic-neighbor tags as a hover HTML snippet.

    Accepts both [(name, score), ...] and [{name/tag, score/cosine_similarity}, ...] forms.
    """
    raw = neighbors.get(tag_name, [])
    if not raw:
        return "<i>이웃 태그 데이터 없음</i>"
    pairs: list[tuple[str, float]] = []
    for nb in raw[:k]:
        if isinstance(nb, (list, tuple)) and len(nb) >= 2:
            pairs.append((str(nb[0]), float(nb[1])))
        elif isinstance(nb, dict):
            name = nb.get("tag") or nb.get("name") or ""
            sim = nb.get("cosine_similarity") or nb.get("score") or 0.0
            if name:
                pairs.append((str(name), float(sim)))
    if not pairs:
        return "<i>이웃 태그 데이터 없음</i>"
    return "<br>".join(
        f"&nbsp;{i+1}. {name} <span style='opacity:0.55'>({sim:.2f})</span>"
        for i, (name, sim) in enumerate(pairs)
    )


tag_df["neighbors_str"] = tag_df["tag"].apply(_format_neighbors)


# ----- Controls --------------------------------------------------------------

col_search, col_filter = st.columns([2, 1])
with col_search:
    query = st.text_input(
        "검색 (태그 이름 또는 게임 이름)",
        placeholder="예: roguelike  /  Hades",
    ).strip().lower()
with col_filter:
    show_labels = st.checkbox("점에 라벨 표시 (느려질 수 있음)", value=False)


# ----- Resolve search target -------------------------------------------------

highlight_tags: set[str] = set()
matched_tag = None
matched_game = None

if query:
    # Exact-or-substring match against tag names first
    tag_hits = [t for t in tag_df["tag"] if query in t.lower()]
    if tag_hits:
        matched_tag = tag_hits[0]
        highlight_tags = {matched_tag}
    elif games_df is not None:
        # Try game name substring match
        gmask = games_df["game_title"].str.lower().str.contains(query, na=False)
        if gmask.any():
            row = games_df[gmask].iloc[0]
            matched_game = row["game_title"]
            raw_tags = str(row["tags"]).split(",")
            normalized = [
                t.strip().lower().replace("/", "-").replace(" ", "-")
                for t in raw_tags if t.strip()
            ]
            highlight_tags = set(normalized) & set(tag_df["tag"])


# ----- Plot ------------------------------------------------------------------

plot_df = tag_df.copy()
plot_df["highlighted"] = plot_df["tag"].isin(highlight_tags)
plot_df["color"] = plot_df["cluster"].astype(str)

HOVER_TEMPLATE = (
    "<b>%{customdata[0]}</b>"
    "<br><br><b>가까운 태그 Top 5</b><br>%{customdata[1]}"
    "<extra></extra>"
)

fig = px.scatter(
    plot_df,
    x="x", y="y",
    color="color",
    custom_data=["tag", "neighbors_str"],
    text="tag" if show_labels else None,
    labels={"color": "Cluster"},
    height=720,
    title=None,
)
fig.update_traces(
    marker=dict(size=8, opacity=0.65),
    hovertemplate=HOVER_TEMPLATE,
)

# Layer the highlighted points on top in bigger red markers
if highlight_tags:
    sub = plot_df[plot_df["highlighted"]]
    fig.add_scatter(
        x=sub["x"], y=sub["y"],
        mode="markers+text",
        marker=dict(size=18, color="#E53935", line=dict(width=2, color="white")),
        text=sub["tag"],
        textposition="top center",
        name="강조",
        customdata=np.column_stack([sub["tag"].values, sub["neighbors_str"].values]),
        hovertemplate=HOVER_TEMPLATE,
    )

fig.update_layout(
    xaxis=dict(showgrid=False, zeroline=False, visible=False),
    yaxis=dict(showgrid=False, zeroline=False, visible=False),
    plot_bgcolor="#0e1117",
    paper_bgcolor="#0e1117",
)
st.plotly_chart(fig, use_container_width=True)


# ----- Side panels -----------------------------------------------------------

if matched_tag:
    st.subheader(f"`{matched_tag}` 의미적 이웃")
    nbrs = neighbors.get(matched_tag, [])
    if nbrs:
        nb_df = pd.DataFrame(nbrs, columns=["tag", "cosine_similarity"])
        nb_df["cosine_similarity"] = nb_df["cosine_similarity"].round(4)
        st.dataframe(nb_df, use_container_width=True, hide_index=True)
    else:
        st.caption("이웃 데이터가 없습니다 (tag_neighbors.json 누락?)")

elif matched_game:
    st.subheader(f"`{matched_game}`의 태그가 지도에서 강조됨")
    st.caption(f"해당 게임 태그 {len(highlight_tags)}개")

else:
    st.caption(
        "팁: 검색창에 게임 이름이나 태그를 입력하면 지도에 강조됩니다. "
        "예: 'roguelike', 'Hades', 'cozy'"
    )
