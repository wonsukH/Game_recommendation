"""Build NON-CIRCULAR co-play relevance labels from user reviews.

Why this exists
---------------
Every existing quality metric in this repo is tag-derived: the system
retrieves games near a tag-built query vector and Genre Precision then
checks whether those games carry the same tag. That is a self-consistency
check, not an independent measure — and a plain tag-cosine baseline scores
*higher* on it. To answer "does the SVD / embedding actually add value",
we need a ground truth that does NOT come from tags or from an LLM.

Co-play does exactly that: two games are "related" if the *same users*
liked both. This signal is independent of the tag vocabulary and of any
LLM, so it is a clean (non-circular) yardstick for **similar mode**
(game -> game). It is the gold standard for item-item recommendation eval.

Caveats (reported honestly in the stats)
-----------------------------------------
- The review crawl is capped at ~10 liked games per user (pagination bug),
  so the signal is sparse and head-skewed. We normalize with conditional
  cosine + a co-occurrence support floor and stratify seeds by support so
  the tail is represented, but co-play is strongest for the head.
- These same reviews were *not* used to train the PPMI/SVD embeddings
  (Item2Vec is OFF, ensemble_alpha=1.0), so co-play is a clean test for
  the shipped system. It would be CONTAMINATED for evaluating an Item2Vec
  variant — guard against that in the driver.

Output
------
`tests/coplay_eval_set.json`: list of
  {query, games, seed_appid, seed_title, relevant_appids, category, mode,
   n_relevant, seed_support}
in the same schema `benchmark.py` consumes (query + relevant_appids), plus
seed fields so the driver can call recommend_similar directly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.io import load_index_maps, save_stats  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("evaluation.coplay_labels")

# Mirrors retriever._series_prefix (duplicated to avoid importing faiss /
# langchain from a data-only module). Keep in sync if that regex changes.
_SERIES_SUFFIX_RE = re.compile(r"\s+(?:[ivx]+|\d+)(?:\s|:|$)|\s*:\s*")


def _series_prefix(title: str) -> str:
    t = str(title).lower().strip()
    parts = _SERIES_SUFFIX_RE.split(t, maxsplit=1)
    return parts[0].strip() if parts else t


def load_liked(
    scores_path: Path, pool: set[int], like_threshold: float
) -> dict[str, set[int]]:
    """Read user_game_scores.csv -> {steamid: {liked in-pool appids}}.

    "liked" = s_round10_rec >= like_threshold. Restricts to the recommendable
    pool before co-occurrence so out-of-pool games never enter the labels.
    """
    log.info("reading %s", scores_path)
    df = pd.read_csv(
        scores_path,
        usecols=["appid", "steamid", "s_round10_rec"],
        encoding="utf-8-sig",
    )
    df = df[df["s_round10_rec"] >= like_threshold]
    df = df[df["appid"].isin(pool)]
    log.info("liked in-pool interactions: %d", len(df))
    user_liked: dict[str, set[int]] = {}
    for steamid, grp in df.groupby("steamid"):
        s = set(int(a) for a in grp["appid"].tolist())
        if len(s) >= 2:  # need >=2 to contribute any co-occurrence
            user_liked[str(steamid)] = s
    log.info("users with >=2 in-pool liked: %d", len(user_liked))
    return user_liked


def build_cooccurrence(
    user_liked: dict[str, set[int]],
) -> tuple[csr_matrix, np.ndarray, dict[int, int]]:
    """Return (C item x item co-occurrence counts, deg, appid->col).

    C[i,j] = number of users who liked BOTH i and j.
    deg[i]  = C[i,i] = number of users who liked i (co-play support).
    """
    appids = sorted({a for s in user_liked.values() for a in s})
    col = {a: j for j, a in enumerate(appids)}
    rows, cols = [], []
    for u_i, (_, liked) in enumerate(user_liked.items()):
        for a in liked:
            rows.append(u_i)
            cols.append(col[a])
    data = np.ones(len(rows), dtype=np.float32)
    X = csr_matrix((data, (rows, cols)), shape=(len(user_liked), len(appids)))
    C = (X.T @ X).tocsr()
    deg = np.asarray(C.diagonal()).ravel()
    log.info("co-occurrence: %d items, C nnz=%d", len(appids), C.nnz)
    return C, deg, col


def seed_neighbors(
    seed_col: int,
    C: csr_matrix,
    deg: np.ndarray,
    min_cooc: int,
    top_n: int,
) -> list[tuple[int, float]]:
    """Top-n co-play neighbors of a seed by conditional cosine.

    assoc(i,j) = C[i,j] / sqrt(deg[i]*deg[j]), requiring C[i,j] >= min_cooc
    (support floor) and j != i. Conditional cosine debiases raw popularity
    so a blockbuster doesn't dominate every seed's neighbor list.
    """
    row = C.getrow(seed_col).tocoo()
    di = deg[seed_col]
    out = []
    for j, c in zip(row.col, row.data):
        if j == seed_col or c < min_cooc:
            continue
        denom = np.sqrt(di * deg[j])
        if denom <= 0:
            continue
        out.append((j, float(c / denom)))
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:top_n]


def build_coplay_labels(
    scores_path: Path,
    data_dir: Path,
    like_threshold: float = 7.0,
    min_support: int = 30,
    min_cooc: int = 3,
    top_n: int = 50,
    n_seeds: int = 600,
    n_strata: int = 3,
    min_relevant: int = 5,
    seed: int = 42,
) -> tuple[list[dict], dict]:
    """Construct the co-play eval set. Deterministic given `seed`.

    Defaults (min_support=30, min_cooc=3) were chosen empirically: they
    yield ~410 robust seeds each with ~25 co-play neighbors. Lower support
    seeds are skipped because <30 likers cannot form a trustworthy relevant
    set under the support floor — co-play is reliable only for the
    sufficiently-reviewed head/mid catalog, NOT the deep long tail.
    """
    maps = load_index_maps(data_dir / "index_maps.json")
    pool = set(int(a) for a in maps["appid2row"].keys())
    titles_df = pd.read_csv(data_dir / "steam_games_tags.csv")
    appid_to_title = dict(zip(titles_df["appid"].astype(int), titles_df["game_title"].astype(str)))

    user_liked = load_liked(scores_path, pool, like_threshold)
    C, deg, col = build_cooccurrence(user_liked)
    inv_col = {j: a for a, j in col.items()}

    # Candidate seeds: enough co-play support to trust the neighbor list.
    cand_cols = np.where(deg >= min_support)[0]
    log.info("candidate seeds (support>=%d): %d", min_support, len(cand_cols))

    # Stratify by support (deg) into terciles so the long tail is represented,
    # not just blockbusters. Sample evenly from each stratum.
    rng = np.random.default_rng(seed)
    order = cand_cols[np.argsort(deg[cand_cols])]
    strata = np.array_split(order, n_strata)
    per = max(1, n_seeds // n_strata)
    picked: list[int] = []
    for st in strata:
        if len(st) == 0:
            continue
        take = min(per, len(st))
        picked.extend(rng.choice(st, size=take, replace=False).tolist())

    labels: list[dict] = []
    skipped = 0
    for sc in picked:
        seed_appid = inv_col[int(sc)]
        seed_title = appid_to_title.get(seed_appid, str(seed_appid))
        prefix = _series_prefix(seed_title)
        nbrs = seed_neighbors(int(sc), C, deg, min_cooc, top_n * 2)
        rel = []
        for j, _score in nbrs:
            a = inv_col[j]
            t = appid_to_title.get(a, "")
            # franchise exclusion (same as retriever): drop sequels/remasters
            if len(prefix) >= 4 and prefix in str(t).lower():
                continue
            rel.append(a)
            if len(rel) >= top_n:
                break
        if len(rel) < min_relevant:
            skipped += 1
            continue
        labels.append({
            "query": f"{seed_title} 같은 게임 추천해줘",
            "games": [seed_title],
            "seed_appid": int(seed_appid),
            "seed_title": seed_title,
            "relevant_appids": rel,
            "category": "coplay-similar",
            "mode": "similar",
            "n_relevant": len(rel),
            "seed_support": int(deg[sc]),
        })

    stats = {
        "n_users_used": len(user_liked),
        "n_items": len(col),
        "like_threshold": like_threshold,
        "min_support": min_support,
        "min_cooc": min_cooc,
        "top_n": top_n,
        "n_candidate_seeds": int(len(cand_cols)),
        "n_seeds_picked": len(picked),
        "n_labels_emitted": len(labels),
        "n_seeds_skipped_too_few_neighbors": skipped,
        "avg_relevant": round(float(np.mean([l["n_relevant"] for l in labels])), 2) if labels else 0.0,
        "support_quartiles": [int(x) for x in np.quantile(deg[cand_cols], [0, .25, .5, .75, 1.0])] if len(cand_cols) else [],
        "seed": seed,
        "caveat": "User reviews capped ~10/user (pagination bug): co-play is head-skewed; conditional-cosine + support floor mitigate. NOT for evaluating Item2Vec variants (trained on same reviews).",
    }
    return labels, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "tests" / "coplay_eval_set.json")
    ap.add_argument("--stats-out", type=Path, default=REPO_ROOT / "experiments" / "coplay_labels_stats.json")
    ap.add_argument("--like-threshold", type=float, default=7.0)
    ap.add_argument("--min-support", type=int, default=30)
    ap.add_argument("--min-cooc", type=int, default=3)
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--n-seeds", type=int, default=600)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    labels, stats = build_coplay_labels(
        scores_path=args.scores,
        data_dir=args.data_dir,
        like_threshold=args.like_threshold,
        min_support=args.min_support,
        min_cooc=args.min_cooc,
        top_n=args.top_n,
        n_seeds=args.n_seeds,
        seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    save_stats(stats, args.stats_out)
    log.info("wrote %d co-play labels -> %s", len(labels), args.output)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
