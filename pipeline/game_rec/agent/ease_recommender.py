"""EASE serving recommender — the P6-confirmed ranker as a drop-in for the
agent graph (same contract as CFRecommender: score / recommend / col / inv_col
/ game_avg_pt).

Loads the sparse top-K B artifact built by data/build_ease_artifact.py.
score(library) = Σ_i w_i · B[i, :]  (sparse row combination, milliseconds).

Profile weights implement the confirmed `pctl_game` preference for NEW users:
the artifact carries each game's playtime-quantile grid (21 points), and the
user's raw playtime is interpolated into a per-game engagement percentile —
the serving-time equivalent of behavioral_scores.pctl_game.

IMPORTANT: recommend() ranks the FULL score vector and never truncates at
score <= 0 — EASE's negative tail is legitimate signal (the T33/T35 cutoff bug
and the T-a ablation both proved it). Do not "optimize" a break back in.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import sparse

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("game_rec.agent.ease_recommender")

DEFAULT_ARTIFACT_DIR = REPO_ROOT / "serving" / "data" / "ease"


class EASERecommender:
    """Loads the EASE artifact; ranks the catalog for a user's library."""

    def __init__(self, artifact_dir: str | Path = DEFAULT_ARTIFACT_DIR):
        d = Path(artifact_dir)
        self.B = sparse.load_npz(d / "B_topk.npz").tocsr()
        self.items = np.load(d / "items.npy")
        self.col = {int(a): j for j, a in enumerate(self.items)}
        self.inv_col = {j: int(a) for a, j in self.col.items()}
        ec = np.load(d / "pt_ecdf.npz")
        self._ecdf_grid = ec["grid"]          # (n_items, 21) playtime quantiles
        self._ecdf_qs = ec["qs"]              # (21,) percentile levels
        avg = np.load(d / "avg_pt.npy")
        self.game_avg_pt = {int(a): float(v) for a, v in zip(self.items, avg)}
        self.meta = json.loads((d / "meta.json").read_text())
        log.info("EASE artifact: %d items, B nnz=%d (lam=%s, graph=%s users)",
                 len(self.items), self.B.nnz, self.meta.get("lam"),
                 self.meta.get("n_graph_users"))

    # ---- profile weighting (serving-time pctl_game) ------------------------
    def profile_weight(self, appid: int, playtime: float) -> float:
        """Interpolated per-game engagement percentile of `playtime` minutes."""
        j = self.col.get(int(appid))
        if j is None or playtime is None or playtime <= 0:
            return 0.0
        grid = self._ecdf_grid[j]
        if grid[-1] <= 0:
            return 0.5
        return float(np.interp(playtime, grid, self._ecdf_qs))

    # ---- scoring -----------------------------------------------------------
    def score_with_weights(self, weights: dict[int, float]) -> np.ndarray:
        """Raw EASE scores from explicit per-item weights (validation entry)."""
        x = np.zeros(len(self.items), dtype=np.float32)
        hit = 0
        for appid, w in weights.items():
            j = self.col.get(int(appid))
            if j is not None and w > 0:
                x[j] = w
                hit += 1
        if hit == 0:
            return x.astype(np.float64)
        return np.asarray((sparse.csr_matrix(x) @ self.B).todense(),
                          dtype=np.float64).ravel()

    def score(self, library_pt: dict[int, float]) -> np.ndarray:
        """CFRecommender-contract scorer: raw playtimes in, catalog scores out."""
        return self.score_with_weights(
            {int(a): self.profile_weight(a, pt) for a, pt in library_pt.items()})

    def recommend(self, library_pt: dict[int, float], k: int = 20,
                  exclude: set[int] | None = None) -> list[tuple[int, float]]:
        """Top-k (appid, score), excluding the library + `exclude`.
        Full-vector ranking — NO score<=0 break (see module docstring)."""
        exclude = (exclude or set()) | {int(a) for a in library_pt}
        scores = self.score(library_pt)
        for a in library_pt:
            j = self.col.get(int(a))
            if j is not None:
                scores[j] = -np.inf
        out = []
        for j in np.argsort(-scores):
            if not np.isfinite(scores[j]):
                break
            a = self.inv_col.get(int(j))
            if a is not None and a not in exclude:
                out.append((a, float(scores[j])))
            if len(out) >= k:
                break
        return out
