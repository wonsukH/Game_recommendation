"""#12 — informed-negative BPR: does the 'dropped' signal exist?

Science question, not a leader contender (BPR absolute ~0.19 << leaders):
train two identical BPRs (same seed/epochs), one sampling negatives uniformly,
one mixing 50% negatives from the user's own DROPPED set
(plan def: pt >= trial 10min AND per-game lower pctl < 0.25 AND no completion
trajectory AND stale 2weeks). A significant paired NDCG gap = the negative
signal is real (input for future 10k-scale learned rankers), regardless of
absolute level.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.evaluation.stats import bootstrap_ci  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    P4, build_relevance, get_panels, graded_ndcg, load_artifacts,
    split_profile_holdout)

log = get_logger("orchestration.bpr_informed_neg")

D, EPOCHS, B, LR, REG, SEED = 64, 20, 8192, 0.05, 0.002, 42
TRIAL_MIN, DROP_PCTL = 10.0, 0.25


def dropped_pairs(inter: pd.DataFrame) -> pd.DataFrame:
    pos = inter[inter["playtime_forever"] > 0].copy()
    r = pos.groupby("appid")["playtime_forever"].rank(method="average")
    n = pos.groupby("appid")["playtime_forever"].transform("size")
    pctl = (r - 0.5) / n
    stale = pos["playtime_2weeks"].fillna(0) == 0
    no_comp = pos["completion"].fillna(0) == 0
    m = (pos["playtime_forever"] >= TRIAL_MIN) & (pctl < DROP_PCTL) & stale & no_comp
    return pos.loc[m, ["steamid", "appid"]]


def fit_bpr(r, c, n_u, n_i, neg_lists: dict[int, np.ndarray] | None, seed=SEED):
    rng = np.random.default_rng(seed)
    U = rng.normal(0, 0.05, (n_u, D)).astype(np.float32)
    V = rng.normal(0, 0.05, (n_i, D)).astype(np.float32)
    n_pos = len(r)
    for ep in range(EPOCHS):
        perm = rng.permutation(n_pos)
        for s0 in range(0, n_pos, B):
            idx = perm[s0:s0 + B]
            uu, ii = r[idx], c[idx]
            jj = rng.integers(0, n_i, size=len(idx))
            if neg_lists is not None:
                coin = rng.random(len(idx)) < 0.5
                for t in np.where(coin)[0]:
                    lst = neg_lists.get(uu[t])
                    if lst is not None and len(lst):
                        jj[t] = lst[rng.integers(0, len(lst))]
            x = np.einsum("bd,bd->b", U[uu], V[ii] - V[jj])
            g = 1.0 / (1.0 + np.exp(x))
            gu = g[:, None] * (V[ii] - V[jj]) - REG * U[uu]
            gi = g[:, None] * U[uu] - REG * V[ii]
            gj = -g[:, None] * U[uu] - REG * V[jj]
            np.add.at(U, uu, LR * gu)
            np.add.at(V, ii, LR * gi)
            np.add.at(V, jj, LR * gj)
    return V.astype(np.float64)


def main() -> int:
    inter, game_stats, user_stats, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    scores = bs.compute("pvalue_lognorm_eb", inter, game_stats, user_stats)

    dd = scores[(scores["s"] > 0) & scores["appid"].isin(pool)]
    dd = dd[dd["steamid"].isin(set(panels["train"]))]
    items = np.array(sorted(dd["appid"].unique()))
    col = {a: j for j, a in enumerate(items)}
    urow = {u: i for i, u in enumerate(sorted(dd["steamid"].unique()))}
    r = dd["steamid"].map(urow).values
    c = dd["appid"].map(col).values

    drops = dropped_pairs(inter)
    drops = drops[drops["steamid"].isin(urow) & drops["appid"].isin(col)]
    neg_lists = {urow[u]: g["appid"].map(col).values
                 for u, g in drops.groupby("steamid")}
    log.info("dropped pairs in-matrix: %d rows, %d users", len(drops), len(neg_lists))

    splits = split_profile_holdout(rel, panels["dev"], seed=42)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            dd[["steamid", "appid", "s"]].values}

    def eval_V(V):
        ndcgs = []
        for u, sp in splits.items():
            prof = {a: smap.get((u, a), 0.0) for a in sp["profile"]}
            prof = {a: w for a, w in prof.items() if w > 0} or dict(sp["profile"])
            rows_, w_ = [], []
            for a, wv in prof.items():
                j = col.get(a)
                if j is not None:
                    rows_.append(j)
                    w_.append(wv)
            if not rows_:
                continue
            Vp = V[rows_]
            A = Vp.T @ (np.asarray(w_)[:, None] * Vp) + 10.0 * np.eye(D)
            uvec = np.linalg.solve(A, Vp.T @ np.asarray(w_))
            sc = V @ uvec
            for a in prof:
                j = col.get(a)
                if j is not None:
                    sc[j] = -np.inf
            top = [int(items[j]) for j in np.argsort(-sc)[:20]]
            ndcgs.append(graded_ndcg(sp["holdout"], top, k=20))
        return np.array(ndcgs)

    t0 = time.time()
    V_rand = fit_bpr(r, c, len(urow), len(items), None)
    nd_rand = eval_V(V_rand)
    V_inf = fit_bpr(r, c, len(urow), len(items), neg_lists)
    nd_inf = eval_V(V_inf)
    diff = nd_inf - nd_rand
    ci = bootstrap_ci(diff)
    res = pd.DataFrame([
        {"variant": "bpr_random_neg", "ndcg": round(float(nd_rand.mean()), 4)},
        {"variant": "bpr_informed_neg", "ndcg": round(float(nd_inf.mean()), 4)},
        {"variant": "paired_diff", "ndcg": round(ci["mean"], 4),
         "ci": f"[{ci['lo']:.4f},{ci['hi']:.4f}]"},
    ])
    out = P4 / "bpr_informed_neg"
    out.mkdir(exist_ok=True)
    res.to_csv(out / "leaderboard.csv", index=False)
    print(res.to_string(index=False))
    print(f"({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
