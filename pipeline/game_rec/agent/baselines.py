"""Pure-numpy retrieval variants for the experiment ladder (similar mode).

These intentionally do NOT import faiss / langchain / the production
recommender. Each variant exposes the same contract so the experiment
driver and the metrics can treat them uniformly:

    retriever.similar(seed_appid, top_k) -> list[appid]   # ranked, seed+franchise excluded

The ladder this supports (similar mode = "ask by game"):
- RandomRetriever        V0  floor anchor
- PopularityRetriever    V1  popularity prior
- TagSetRetriever        Jaccard over raw binary tags (rawest content signal)
- TagCosineRetriever     Vb  vote-weighted tag cosine, NO SVD / NO W_align
- VecSimilarRetriever    Vc/Vd  cosine over a game-vector matrix (game_vecs_ppmi
                         = PPMI+SVD only; game_vecs = shipped ensemble). FAISS
                         IndexFlatL2 over unit vectors == this argsort, so this
                         is an exact pure-numpy stand-in (no faiss needed).

All row<->appid indexing goes through index_maps.json (the canonical build
order that X_game_tag_*.npz and game_vecs*.npy were written against).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.preprocessing import normalize

from pipeline.game_rec.io import load_csr, load_index_maps, load_vectors

_SERIES_SUFFIX_RE = re.compile(r"\s+(?:[ivx]+|\d+)(?:\s|:|$)|\s*:\s*")


def _series_prefix(title: str) -> str:
    t = str(title).lower().strip()
    parts = _SERIES_SUFFIX_RE.split(t, maxsplit=1)
    return parts[0].strip() if parts else t


class Catalog:
    """Shared row<->appid maps, titles, popularity, franchise lookup.

    Built once and passed to every retriever so they index identically.
    """

    def __init__(self, data_dir: str | Path):
        data_dir = Path(data_dir)
        maps = load_index_maps(data_dir / "index_maps.json")
        self.appid2row = {int(a): int(r) for a, r in maps["appid2row"].items()}
        self.row2appid = {int(r): int(a) for r, a in maps["row2appid"].items()}
        self.n = len(self.row2appid)
        self.rows = np.array([self.row2appid[i] for i in range(self.n)])  # appid per row

        df = pd.read_csv(data_dir / "steam_games_tags.csv")
        self.appid2title = dict(zip(df["appid"].astype(int), df["game_title"].astype(str)))
        self._title_lower = np.array(
            [str(self.appid2title.get(self.row2appid[i], "")).lower() for i in range(self.n)]
        )

        pop_path = data_dir / "game_popularity.npy"
        if pop_path.exists():
            self.popularity = np.load(pop_path).astype(np.float64)
        else:
            self.popularity = np.ones(self.n, dtype=np.float64)

    def excluded_rows(self, seed_appid: int) -> np.ndarray:
        """Row indices to drop for a seed: the seed itself + its franchise.

        Mirrors retriever's substring franchise filter (prefix in title).
        """
        ex = np.zeros(self.n, dtype=bool)
        if seed_appid in self.appid2row:
            ex[self.appid2row[seed_appid]] = True
        pref = _series_prefix(self.appid2title.get(seed_appid, ""))
        if len(pref) >= 4:
            ex |= np.char.find(self._title_lower, pref) >= 0
        return ex

    def topk_from_scores(self, scores: np.ndarray, excluded: np.ndarray, top_k: int) -> list[int]:
        """Return top_k appids by score, with excluded rows removed."""
        s = scores.astype(np.float64).copy()
        s[excluded] = -np.inf
        s[~np.isfinite(s)] = -np.inf
        k = min(top_k, int(np.isfinite(s).sum()))
        if k <= 0:
            return []
        top = np.argpartition(-s, k - 1)[:k]
        top = top[np.argsort(-s[top])]
        return [int(self.row2appid[int(r)]) for r in top]


class _Base:
    name = "base"

    def __init__(self, catalog: Catalog):
        self.cat = catalog

    def similar(self, seed_appid: int, top_k: int = 200) -> list[int]:
        raise NotImplementedError


class RandomRetriever(_Base):
    name = "V0_random"

    def __init__(self, catalog: Catalog, seed: int = 42):
        super().__init__(catalog)
        self.rng = np.random.default_rng(seed)

    def similar(self, seed_appid: int, top_k: int = 200) -> list[int]:
        scores = self.rng.random(self.cat.n)
        return self.cat.topk_from_scores(scores, self.cat.excluded_rows(seed_appid), top_k)


class PopularityRetriever(_Base):
    name = "V1_popularity"

    def similar(self, seed_appid: int, top_k: int = 200) -> list[int]:
        return self.cat.topk_from_scores(self.cat.popularity, self.cat.excluded_rows(seed_appid), top_k)


class TagSetRetriever(_Base):
    """Jaccard over raw binary tags — the rawest possible content signal."""

    name = "tagset_jaccard"

    def __init__(self, catalog: Catalog, csr_path: str | Path):
        super().__init__(catalog)
        X = load_csr(csr_path)
        self.B = (X > 0).astype(np.float64).tocsr()  # binary
        self.sizes = np.asarray(self.B.sum(axis=1)).ravel()  # |tags| per game

    def similar(self, seed_appid: int, top_k: int = 200) -> list[int]:
        if seed_appid not in self.cat.appid2row:
            return []
        row = self.cat.appid2row[seed_appid]
        seed_vec = self.B.getrow(row)
        inter = np.asarray(self.B.dot(seed_vec.T).todense()).ravel()
        union = self.sizes + self.sizes[row] - inter
        jacc = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
        return self.cat.topk_from_scores(jacc, self.cat.excluded_rows(seed_appid), top_k)


class TagCosineRetriever(_Base):
    """Vb: vote-weighted tag cosine. NO SVD, NO W_align. The key baseline.

    If the PPMI+SVD embedding can't beat this on co-play recall, the SVD adds
    no value for similar mode.
    """

    name = "Vb_tagcosine"

    def __init__(self, catalog: Catalog, csr_path: str | Path):
        super().__init__(catalog)
        X = load_csr(csr_path).astype(np.float64)
        self.Xn = normalize(X, norm="l2", axis=1).tocsr()  # row-normalized for cosine

    def similar(self, seed_appid: int, top_k: int = 200) -> list[int]:
        if seed_appid not in self.cat.appid2row:
            return []
        row = self.cat.appid2row[seed_appid]
        q = self.Xn.getrow(row)
        scores = np.asarray(self.Xn.dot(q.T).todense()).ravel()
        return self.cat.topk_from_scores(scores, self.cat.excluded_rows(seed_appid), top_k)


class VecSimilarRetriever(_Base):
    """Vc/Vd: cosine over a dense game-vector matrix.

    game_vecs_ppmi.npy -> Vc (PPMI+SVD only). game_vecs.npy -> shipped
    ensemble. Exact pure-numpy equivalent of the production FAISS IndexFlatL2
    search over L2-normalized vectors.
    """

    def __init__(self, catalog: Catalog, vecs_path: str | Path, name: str):
        super().__init__(catalog)
        V = load_vectors(vecs_path, dtype="float64")
        self.Vn = normalize(V, norm="l2", axis=1)
        self.name = name

    def similar(self, seed_appid: int, top_k: int = 200) -> list[int]:
        if seed_appid not in self.cat.appid2row:
            return []
        q = self.Vn[self.cat.appid2row[seed_appid]]
        scores = self.Vn @ q
        return self.cat.topk_from_scores(scores, self.cat.excluded_rows(seed_appid), top_k)
