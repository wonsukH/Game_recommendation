"""E5 — EASE fine-tuning + challengers (exploration pool ONLY; serving change
requires mini-prereg + the reserve panel).

Baseline: EASE(l100) on the deployment-like G2 graph (train + all exploration
increment, eval users held out). Challengers:
  grid    EASE lambda in {30,50,70,100,140,200,300}
  T-a     EASE-nonneg: clip NEGATIVE entries of B to 0 (chunked exact rows of
          B for profile items). Tests the negative-weight justification: if
          performance falls toward condcos, negative relations carry signal.
  EDLAE   full-rank denoising EASE (Steck 2020): ridge proportional to
          diag(G) — P = (G + a*diagMat(diag G))^-1 via generalized Woodbury.
          a in {0.1, 0.5, 1.0}.
  fusion  z-score blend EASE+userknn (alpha 0.3/0.5/0.7) and RRF(k=60).
SLIM is DEFERRED: same regularization family as EDLAE at 10-100x the compute;
run it only if EDLAE separates from EASE (recorded decision).

Metrics: NDCG@20 + wishlist recall@20 (A5 snapshot targets), paired bootstrap
vs the EASE(l100) baseline on identical users.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.evaluation.stats import paired_bootstrap_diff  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.p6_common import (  # noqa: E402
    K, P4_DIR, P6_DIR, assert_firewall, build_relevance, build_wl_targets,
    graded_profile, load_artifacts, load_panels, load_wishlist_snapshot,
    split_profile_holdout)
from pipeline.orchestration.preference_sweep import graded_ndcg  # noqa: E402
from pipeline.orchestration.ranker_gauntlet import EaseRanker, UserKNN  # noqa: E402

log = get_logger("orchestration.p6_e5")
OUT = P6_DIR / "e5_challengers"
EVAL_N, EVAL_SEED = 400, 888


# --------------------------------------------------------------- scorers

def ease_scores_vec(ez: EaseRanker, profile: dict[int, float]) -> np.ndarray | None:
    x = np.zeros(len(ez.items))
    hit = 0
    for a, w in profile.items():
        j = ez.col.get(int(a))
        if j is not None:
            x[j] = w
            hit += 1
    if not hit:
        return None
    xXt = ez.X @ x
    return x - ((x - xXt @ ez.V) / ez.lam) / ez.diagP


def knn_scores_vec(kn: UserKNN, profile: dict[int, float]) -> np.ndarray | None:
    p = np.zeros(len(kn.items), dtype=np.float32)
    hit = 0
    for a, w in profile.items():
        j = kn.col.get(int(a))
        if j is not None:
            p[j] = w
            hit += 1
    if not hit:
        return None
    pn = np.linalg.norm(p)
    sims = np.asarray(kn.X @ p).ravel() / np.maximum(kn.row_norm * pn, 1e-12)
    top = np.argsort(-sims)[: kn.topk_users]
    wts = np.maximum(sims[top], 0)
    return np.asarray((sparse.diags(wts) @ kn.X[top]).sum(axis=0)).ravel()


def rank_topk(scores_vec: np.ndarray, items: np.ndarray, col: dict,
              profile: dict, exclude: set, k: int = K) -> list[int]:
    s = scores_vec.copy()
    for a in profile:
        j = col.get(int(a))
        if j is not None:
            s[j] = -np.inf
    rec = []
    for j in np.argsort(-s):
        a = int(items[j])
        if a not in exclude:
            rec.append(a)
        if len(rec) >= k:
            break
    return rec


class EasePositiveB:
    """T-a ablation: exact B rows for profile items, negatives clipped to 0.
    B[i,:] = e_i - P[i,:]/diagP  with  P[i,:] = (1/lam)(e_i - X^T (Minv X) e_i-col
    computed from the fitted EaseRanker's user-space factors."""

    def __init__(self, ez: EaseRanker, need_items: list[int], chunk: int = 512):
        self.ez = ez
        self.rows: dict[int, np.ndarray] = {}
        cols = [ez.col[a] for a in need_items if a in ez.col]
        Xc = ez.X.tocsc()
        for s0 in range(0, len(cols), chunk):
            cc = cols[s0:s0 + chunk]
            Xi = np.asarray(Xc[:, cc].todense())          # (u, c)
            P_rows = -(ez.V.T @ Xi).T / ez.lam            # (c, i) = (X^T Minv X)/lam rows
            for t, j in enumerate(cc):
                row = P_rows[t].copy()
                row[j] += 1.0 / ez.lam                    # + e_i/lam
                brow = -row / ez.diagP
                brow[j] += 1.0                            # B = I - P/diagP
                brow[j] = 0.0                             # zero diag (never self)
                self.rows[j] = np.maximum(brow, 0.0)      # CLIP negatives

    def scores(self, profile: dict[int, float]) -> np.ndarray | None:
        acc = np.zeros(len(self.ez.items))
        hit = 0
        for a, w in profile.items():
            j = self.ez.col.get(int(a))
            if j is not None and j in self.rows:
                acc += w * self.rows[j]
                hit += 1
        return acc if hit else None


class Edlae:
    """Full-rank EDLAE (dropout-equivalent ridge ~ a*diag(G)), zero-diag via the
    EASE construction; generalized Woodbery with diagonal D = a*diag(G)."""

    def __init__(self, scores, graph_users, pool, alpha: float):
        d = scores[(scores["s"] > 0) & scores["appid"].isin(pool)]
        d = d[d["steamid"].isin(set(graph_users))]
        self.items = np.array(sorted(d["appid"].unique()))
        self.col = {a: j for j, a in enumerate(self.items)}
        urow = {u: i for i, u in enumerate(sorted(d["steamid"].unique()))}
        r = d["steamid"].map(urow).values
        c = d["appid"].map(self.col).values
        X = sparse.csr_matrix((d["s"].values.astype(np.float64), (r, c)),
                              shape=(len(urow), len(self.items)))
        t0 = time.time()
        diagG = np.asarray(X.multiply(X).sum(axis=0)).ravel()
        Dinv = 1.0 / np.maximum(alpha * diagG, 1e-9)
        XD = X.multiply(Dinv[None, :]).tocsr()            # X D^-1
        M2 = np.linalg.inv(np.eye(X.shape[0]) + (XD @ X.T).toarray())
        self.X, self.XD, self.M2, self.Dinv = X, XD, M2, Dinv
        XDd = XD.toarray()
        diagP = Dinv - np.einsum("ui,ui->i", XDd, M2 @ XDd)
        self.diagP = np.maximum(diagP, 1e-9)
        log.info("EDLAE fit a=%.2f: %d x %d (%.1fs)", alpha, *X.shape[::-1],
                 time.time() - t0)

    def scores_vec(self, profile: dict[int, float]) -> np.ndarray | None:
        x = np.zeros(len(self.items))
        hit = 0
        for a, w in profile.items():
            j = self.col.get(int(a))
            if j is not None:
                x[j] = w
                hit += 1
        if not hit:
            return None
        xD = x * self.Dinv
        xP = xD - ((self.M2 @ (self.X @ xD)) @ self.XD)
        return x - xP / self.diagP


# --------------------------------------------------------------- main

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inter, gs, us, pool = load_artifacts()
    panels = load_panels()
    rel = build_relevance(inter, pool)
    counts = rel.groupby("steamid").size()
    explo = [int(u) for u in panels["exploration"] if u in counts.index]
    rng = np.random.default_rng(EVAL_SEED)
    eval_users = sorted(int(u) for u in rng.choice(explo, size=EVAL_N, replace=False))
    assert_firewall(eval_users, panels)
    inc = sorted(set(explo) - set(eval_users))
    panels_p4 = json.loads((P4_DIR / "panels.json").read_text())
    graph = sorted(set(panels_p4["train"]) | set(inc))

    splits = split_profile_holdout(rel, eval_users, seed=42)
    uu = sorted(splits)
    scores = bs.compute("pvalue_lognorm_eb", inter, gs, us)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            scores[scores["s"] > 0][["steamid", "appid", "s"]].values}

    wl = load_wishlist_snapshot()
    owned_pairs = set(zip(inter["steamid"].astype(int), inter["appid"].astype(int)))
    wl_targets = build_wl_targets(uu, pool, owned_pairs, wl)
    prof_all = {int(u): dict(zip(g["appid"].astype(int), g["rel"].astype(float)))
                for u, g in rel[rel["steamid"].isin(wl_targets)].groupby("steamid")}
    log.info("eval=%d graph=%d wl_eligible=%d", len(uu), len(graph), len(wl_targets))

    # fitted models
    ez = {lam: EaseRanker(scores, graph, pool, lam=float(lam))
          for lam in (30, 50, 70, 100, 140, 200, 300)}
    kn = UserKNN(scores, graph, pool, topk_users=25)
    base = ez[100]
    need = sorted({a for u in uu for a in splits[u]["profile"]}
                  | {a for u in wl_targets for a in prof_all.get(u, {})})
    tpos = time.time()
    bpos = EasePositiveB(base, need)
    log.info("EasePositiveB rows=%d (%.0fs)", len(bpos.rows), time.time() - tpos)
    ed = {a: Edlae(scores, graph, pool, alpha=a) for a in (0.1, 0.5, 1.0)}

    def variants(profile):
        """name -> score vector over base.items (all models share the index)."""
        out = {}
        e_vecs = {lam: ease_scores_vec(m, profile) for lam, m in ez.items()}
        k_vec = knn_scores_vec(kn, profile)
        for lam, v in e_vecs.items():
            out[f"ease_l{lam}"] = v
        out["ease_l100_nonneg"] = bpos.scores(profile)
        for a, m in ed.items():
            out[f"edlae_a{a}"] = m.scores_vec(profile)
        e, kv = e_vecs[100], k_vec
        if e is not None and kv is not None:
            zs = lambda v: (v - np.nanmean(v)) / (np.nanstd(v) + 1e-12)  # noqa: E731
            ze, zk = zs(e), zs(kv)
            for al in (0.3, 0.5, 0.7):
                out[f"zblend_a{al}"] = al * ze + (1 - al) * zk
            re = np.empty_like(e)
            re[np.argsort(-e)] = np.arange(len(e))
            rk = np.empty_like(kv, dtype=float)
            rk[np.argsort(-kv)] = np.arange(len(kv))
            out["rrf_k60"] = 1.0 / (60 + re) + 1.0 / (60 + rk)
        return out

    names = None
    nd: dict[str, dict] = {}
    wlr: dict[str, dict] = {}
    for u in uu:
        sp = splits[u]
        prof = graded_profile(u, sp["profile"], smap, rel_fallback=sp["profile"])
        vs = variants(prof)
        if names is None:
            names = list(vs)
            nd = {n: {} for n in names}
            wlr = {n: {} for n in names}
        for n, v in vs.items():
            if v is None:
                continue
            rec = rank_topk(v, base.items, base.col, prof, set(sp["profile"]))
            nd[n][u] = graded_ndcg(sp["holdout"], rec, K)
    for u, ts in wl_targets.items():
        pa = prof_all[u]
        wprof = graded_profile(u, pa, smap, rel_fallback=pa)
        vs = variants(wprof)
        for n, v in vs.items():
            if v is None:
                continue
            rec = rank_topk(v, base.items, base.col, wprof, set(pa))
            wlr[n][u] = len(ts & set(rec[:K])) / len(ts)

    rows = []
    for n in names:
        du = sorted(set(nd["ease_l100"]) & set(nd[n]))
        d1 = paired_bootstrap_diff([nd["ease_l100"][u] for u in du],
                                   [nd[n][u] for u in du])
        wu = sorted(set(wlr["ease_l100"]) & set(wlr[n]))
        d2 = paired_bootstrap_diff([wlr["ease_l100"][u] for u in wu],
                                   [wlr[n][u] for u in wu]) if wu else None
        rows.append({
            "variant": n,
            "ndcg": round(float(np.mean([nd[n][u] for u in du])), 4),
            "d_ndcg": round(d1["mean_diff"], 4),
            "d_ndcg_ci": f"[{d1['lo']:+.4f},{d1['hi']:+.4f}]",
            "sig_ndcg": d1["significant"],
            "wl": round(float(np.mean([wlr[n][u] for u in wu])), 4) if wu else np.nan,
            "d_wl": round(d2["mean_diff"], 4) if d2 else np.nan,
            "sig_wl": d2["significant"] if d2 else None,
            "n": len(du)})
        log.info("%s: ndcg=%.4f (d=%+.4f %s)", n, rows[-1]["ndcg"],
                 rows[-1]["d_ndcg"], "SIG" if rows[-1]["sig_ndcg"] else "ns")

    tab = pd.DataFrame(rows).sort_values("ndcg", ascending=False)
    tab.to_csv(OUT / "leaderboard.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(
        {"eval_n": len(uu), "graph_n": len(graph),
         "wl_eligible": len(wl_targets),
         "baseline": "ease_l100",
         "slim_deferred": "same regularization family as EDLAE at 10-100x "
                          "compute; run only if EDLAE separates from EASE",
         "table": tab.to_dict(orient="records")}, indent=2))
    print(tab.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
