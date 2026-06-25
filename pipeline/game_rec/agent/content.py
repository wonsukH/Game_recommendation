"""Content layer over the catalog (game×tag) — the shared base for cold-start
fallback (D1) and directional steering (the new feature).

It reuses the *validated* content signal: binary game×tag vectors, L2-normalized,
cosine — i.e. the `Vb` tag-cosine that beat PPMI+SVD on co-play (experiments/
01_similar_eval). NOT W_align embedding projection, which lost (P2b/F1). The only
generalization here is from a single seed game to a playtime-weighted *library*
tag profile, so it can (a) score the 1,506 CF-cold games (X covers 100% of the
pool) and (b) measure genre-novelty / aspect strength for steering.

All artifacts already live in serving/data/: X_game_tag_csr.npz (9956×447 binary),
tag_vocab.json, index_maps.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.sparse import load_npz
from sklearn.preprocessing import normalize

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.agent.cf_recommender import pt_weight  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("game_rec.agent.content")

DEFAULT_DATA_DIR = REPO_ROOT / "serving" / "data"


class ContentLayer:
    """Tag-cosine content scoring + novelty/aspect signals over the full pool."""

    def __init__(self, data_dir: str | Path = DEFAULT_DATA_DIR):
        d = Path(data_dir)
        maps = load_index_maps(d / "index_maps.json")
        self.appid2row = {int(a): int(r) for a, r in maps["appid2row"].items()}
        self.row2appid = {int(r): int(a) for r, a in maps["row2appid"].items()}
        self.n = len(self.row2appid)
        self.appids = np.array([self.row2appid[i] for i in range(self.n)])

        X = load_npz(d / "X_game_tag_csr.npz").astype(np.float64)
        self.B = (X > 0).astype(np.float64).tocsr()          # binary game×tag
        self.Xn = normalize(self.B, norm="l2", axis=1).tocsr()  # row-normalized (Vb)
        self.tag_sizes = np.asarray(self.B.sum(axis=1)).ravel()  # |tags| per game

        # tag name <-> column index (canonical names from index_maps.tag2idx)
        self.tag2idx = {str(t): int(j) for t, j in maps["tag2idx"].items()}
        self.idx2tag = {int(j): str(t) for t, j in self.tag2idx.items()}
        self.n_tags = self.B.shape[1]

    # ---------- user-side profile ----------
    def tag_profile(self, library_pt: dict[int, float],
                    game_avg_pt: dict[int, float] | None = None) -> np.ndarray:
        """Playtime-weighted, L2-normalized tag vector for a user's library.

        Sum of each owned game's normalized tag row, weighted by pt_weight
        (longer-than-average play = stronger taste). Mirrors the CF taste weight.
        """
        prof = np.zeros(self.n_tags, dtype=np.float64)
        for appid, pt in library_pt.items():
            r = self.appid2row.get(int(appid))
            if r is None:
                continue
            w = pt_weight(pt, (game_avg_pt or {}).get(int(appid), 0.0))
            prof += w * self.Xn.getrow(r).toarray().ravel()
        nrm = np.linalg.norm(prof)
        return prof / nrm if nrm > 0 else prof

    def content_scores(self, library_pt: dict[int, float],
                       game_avg_pt: dict[int, float] | None = None) -> np.ndarray:
        """Tag-cosine of EVERY pool game to the user's tag profile (n_games,).

        Covers all 9,956 games incl. the CF-cold ones -> the cold-start fallback.
        """
        prof = self.tag_profile(library_pt, game_avg_pt)
        if not np.any(prof):
            return np.zeros(self.n, dtype=np.float64)
        return np.asarray(self.Xn.dot(prof)).ravel()

    def played_tag_centrality(self, library: dict[int, float] | set[int]) -> np.ndarray:
        """How central each tag is to the user's taste: fraction of library games
        that carry the tag (n_tags,), in [0,1]. Basis for genre-novelty."""
        rows = [self.appid2row[int(a)] for a in library if int(a) in self.appid2row]
        if not rows:
            return np.zeros(self.n_tags, dtype=np.float64)
        sub = self.B[rows]
        return np.asarray(sub.sum(axis=0)).ravel() / len(rows)

    # ---------- steering signals ----------
    def novelty_scores(self, library: dict[int, float] | set[int]) -> np.ndarray:
        """Genre-novelty per game (n_games,): 1 - avg centrality of its tags to the
        user's taste. A game built from tags the user has never played -> ~1; a game
        of the user's core genres -> ~0. Used to steer toward UNEXPLORED genres."""
        pw = self.played_tag_centrality(library)         # (n_tags,)
        fam_sum = np.asarray(self.B.dot(pw)).ravel()     # sum of centrality over a game's tags
        sizes = np.where(self.tag_sizes > 0, self.tag_sizes, 1.0)
        familiarity = fam_sum / sizes                    # avg centrality of the game's tags
        return 1.0 - familiarity

    def resolve_tags(self, names: list[str]) -> list[int]:
        """Map (already canonical-ish) tag names -> column indices, lenient."""
        out = []
        for nm in names or []:
            key = str(nm).strip().lower().replace(" ", "-").replace("/", "-")
            if key in self.tag2idx:
                out.append(self.tag2idx[key])
        return out

    def aspect_scores(self, tag_idxs: list[int]) -> np.ndarray:
        """Per-game strength on a set of aspect tags (n_games,): fraction of the
        requested aspect tags the game carries. Used to steer toward a liked aspect
        (e.g. combat, story, atmosphere)."""
        if not tag_idxs:
            return np.zeros(self.n, dtype=np.float64)
        cols = self.B[:, tag_idxs]
        return np.asarray(cols.sum(axis=1)).ravel() / float(len(tag_idxs))

    # ---------- helpers ----------
    def cold_appids(self, cf_col: set[int]) -> list[int]:
        """Pool games not covered by the CF co-occurrence columns."""
        return [int(a) for a in self.appids if int(a) not in cf_col]


if __name__ == "__main__":
    cl = ContentLayer()
    print(f"ContentLayer: {cl.n} games x {cl.n_tags} tags")
    # smoke: a tiny library should produce a finite content ranking over ALL games
    import json
    cf_col = set(int(a) for a in json.loads((DEFAULT_DATA_DIR / "cf" / "col_appid2idx.json").read_text(encoding="utf-8")).keys())
    cold = cl.cold_appids(cf_col)
    lib = {cl.appids[0]: 100.0, cl.appids[5]: 500.0}
    cs = cl.content_scores(lib)
    nov = cl.novelty_scores(lib)
    print(f"content_scores finite={np.isfinite(cs).all()} nonzero={int((cs>0).sum())}/{cl.n} "
          f"(covers cold? {int(sum(cs[cl.appid2row[a]]>0 for a in cold[:200]))}/200 cold sampled)")
    print(f"novelty range [{nov.min():.2f},{nov.max():.2f}] mean {nov.mean():.2f}")
    asp = cl.resolve_tags(["combat", "story-rich", "atmospheric"])
    print(f"resolve_tags(combat,story-rich,atmospheric) -> {asp} ({[cl.idx2tag.get(i) for i in asp]})")
