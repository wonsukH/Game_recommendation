"""Personalized collaborative-filtering recommender — the validated moat, as a
production tool.

Experiment (experiments/05_personalization/) showed playtime-weighted item-item
CF over the 1.2M-user co-occurrence beats "give the LLM your library" on
behavioral hold-out (recall@20 0.293 vs 0.173, Δ+0.120 [+0.049,+0.192], sig).
This packages that exact method for the agent to call as the `cf_rank` tool.

Method (identical to the validated experiment):
  - "liked" = s_round10_rec >= 7, restricted to the recommendable pool.
  - co-occurrence C[i,j] = #users who liked both; deg[i] = #users who liked i.
  - similarity = conditional cosine  C[i,j]/sqrt(deg[i]·deg[j])  with support
    floor C[i,j] >= min_cooc.
  - personalized score(g) = Σ_{p in library} w_p · sim(g,p),
    w_p = log(1 + playtime_p / game_avg_playtime[p])   (longer-than-average play
    = stronger taste signal).

PRODUCTION uses ALL crawled users to build C (recommending for a NEW user).
The leave-user-out variant lived only in the evaluation harness.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix, save_npz, load_npz

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.evaluation.coplay_labels import build_cooccurrence, load_liked  # noqa: E402
from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("game_rec.agent.cf_recommender")

DEFAULT_ARTIFACT_DIR = REPO_ROOT / "serving" / "data" / "cf"


def pt_weight(playtime: float, avg: float) -> float:
    """log(1 + playtime/game_avg). Falls back to 1.0 when avg unknown."""
    if avg and avg > 0:
        return math.log1p(playtime / avg)
    return 1.0


def build_artifact(scores_path: Path, data_dir: Path, out_dir: Path,
                   like_threshold: float = 7.0) -> dict:
    """Build co-occurrence + game_avg_playtime from ALL users; save to out_dir."""
    import csv, collections
    maps = load_index_maps(data_dir / "index_maps.json")
    pool = set(int(a) for a in maps["appid2row"].keys())

    user_liked = load_liked(scores_path, pool, like_threshold)  # {steamid:{appids}}
    C, deg, col = build_cooccurrence(user_liked)

    # game average playtime over all in-pool interactions (for taste weighting)
    pt_sum = collections.defaultdict(float)
    pt_cnt = collections.defaultdict(int)
    with open(scores_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                a = int(row["appid"])
            except (TypeError, ValueError):
                continue
            if a not in pool:
                continue
            try:
                pt_sum[a] += float(row["playtime_forever"]); pt_cnt[a] += 1
            except (TypeError, ValueError):
                pass
    game_avg_pt = {a: pt_sum[a] / pt_cnt[a] for a in pt_sum if pt_cnt[a] > 0}

    out_dir.mkdir(parents=True, exist_ok=True)
    save_npz(out_dir / "cooccurrence.npz", C.tocsr())
    np.save(out_dir / "deg.npy", deg)
    (out_dir / "col_appid2idx.json").write_text(
        json.dumps({str(a): int(j) for a, j in col.items()}), encoding="utf-8")
    (out_dir / "game_avg_playtime.json").write_text(
        json.dumps({str(a): float(v) for a, v in game_avg_pt.items()}), encoding="utf-8")
    stats = {"n_users": len(user_liked), "n_items": len(col), "C_nnz": int(C.nnz),
             "like_threshold": like_threshold}
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    log.info("CF artifact saved -> %s | %s", out_dir, stats)
    return stats


class CFRecommender:
    """Loads the CF artifact; ranks the catalog for a user's library."""

    def __init__(self, artifact_dir: str | Path = DEFAULT_ARTIFACT_DIR, min_cooc: int = 3):
        d = Path(artifact_dir)
        self.C = load_npz(d / "cooccurrence.npz").tocsr()
        self.deg = np.load(d / "deg.npy")
        self.col = {int(a): int(j) for a, j in json.loads((d / "col_appid2idx.json").read_text(encoding="utf-8")).items()}
        self.inv_col = {j: a for a, j in self.col.items()}
        self.game_avg_pt = {int(a): float(v) for a, v in json.loads((d / "game_avg_playtime.json").read_text(encoding="utf-8")).items()}
        self.min_cooc = min_cooc

    def score(self, library_pt: dict[int, float]) -> np.ndarray:
        """score(g) = Σ_p w_p·condcos(g,p) over library games present in C."""
        acc = np.zeros(self.C.shape[0], dtype=np.float64)
        for appid, pt in library_pt.items():
            j = self.col.get(int(appid))
            if j is None:
                continue
            w = pt_weight(pt, self.game_avg_pt.get(int(appid), 0.0))
            row = self.C.getrow(j).tocoo()
            dj = self.deg[j]
            for g, c in zip(row.col, row.data):
                if c < self.min_cooc or g == j:
                    continue
                denom = math.sqrt(dj * self.deg[g])
                if denom > 0:
                    acc[g] += w * (c / denom)
        return acc

    def recommend(self, library_pt: dict[int, float], k: int = 20,
                  exclude: set[int] | None = None) -> list[tuple[int, float]]:
        """Return [(appid, score)] top-k, excluding the library + `exclude`."""
        exclude = (exclude or set()) | set(int(a) for a in library_pt)
        scores = self.score(library_pt)
        order = np.argsort(-scores)
        out = []
        for j in order:
            if scores[j] <= 0:
                break
            a = self.inv_col.get(int(j))
            if a is not None and a not in exclude:
                out.append((a, float(scores[j])))
            if len(out) >= k:
                break
        return out


def _selftest(artifact_dir: Path, scores_path: Path, data_dir: Path,
              n_users: int = 60, seed: int = 42) -> None:
    """Quick hold-out sanity: recall@20 on real users (should match ~experiment)."""
    from pipeline.game_rec.evaluation.metrics import recall_at_k
    maps = load_index_maps(data_dir / "index_maps.json")
    pool = set(int(a) for a in maps["appid2row"].keys())
    user_liked = load_liked(scores_path, pool, 7.0)
    rec = CFRecommender(artifact_dir)
    # need playtime per (user,game): re-read minimal
    import csv, collections
    upt = collections.defaultdict(dict)
    elig = [u for u, g in user_liked.items() if len(g) >= 8]
    rng = np.random.default_rng(seed)
    test = set(rng.choice(np.array(elig, dtype=object), size=min(n_users, len(elig)), replace=False).tolist())
    with open(scores_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["steamid"] in test:
                try:
                    a = int(row["appid"])
                    if a in pool and float(row["s_round10_rec"]) >= 7.0:
                        upt[row["steamid"]][a] = float(row["playtime_forever"])
                except (TypeError, ValueError):
                    pass
    recalls = []
    for u in test:
        appids = list(upt[u].keys())
        if len(appids) < 4:
            continue
        rng2 = np.random.default_rng(hash(u) % (2**32))
        rng2.shuffle(appids)
        n_prof = max(1, int(round(len(appids) * 0.7)))
        profile = {a: upt[u][a] for a in appids[:n_prof]}
        holdout = set(appids[n_prof:])
        recs = [a for a, _ in rec.recommend(profile, k=20)]
        recalls.append(recall_at_k(holdout, recs, 20))
    log.info("SELFTEST recall@20 over %d users = %.3f (experiment full-build ~0.29; "
             "this uses ALL users incl. test, so leakage makes it >= experiment)", len(recalls), float(np.mean(recalls)))
    print(f"selftest recall@20 = {np.mean(recalls):.3f} (n={len(recalls)})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    b.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    b.add_argument("--out", type=Path, default=DEFAULT_ARTIFACT_DIR)
    s = sub.add_parser("selftest")
    s.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT_DIR)
    s.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    s.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    a = ap.parse_args()
    if a.cmd == "build":
        build_artifact(a.scores, a.data_dir, a.out)
    else:
        _selftest(a.artifact, a.scores, a.data_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
