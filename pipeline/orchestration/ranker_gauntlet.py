"""P4 Stage B — ranker gauntlet: 8 rankers x frozen top preferences.

Stage A froze the preference winners (cap_a03_blend04 NDCG-best, cap_a0_blend04
SNIPS/discovery-best). This one-shot benchmark asks: given those preference
matrices, which RANKER family serves them best? Same panels / splits / metrics
as preference_sweep ([F6] discipline); paired comparisons against condcos.

Rankers:
  condcos   item-item cosine over user-vectors (production formula; GradedCF)
  condasym  asymmetric conditional P(g|p) = C[g,p]/deg_p (popularity-tilted)
  jaccard   binary C/(da+db-C) (support-only view)
  ppmi      positive PMI log(C*T/(deg_i*deg_j)) (co-occurrence surprise)
  p3a       RP3B with beta=0 (pure 2-step walk)
  rp3b      weighted walk + popularity^0.6 discount
  ease      closed-form linear item model, Woodbury via user-space (lambda sweep)
  userknn   user-based CF: top-K similar train users' weighted libraries

EASE via Woodbury (n_users << n_items): P=(G+lI)^-1 = (1/l)(I - X^T M^-1 X),
M = l*I_u + X X^T (dense ~1.1k). diag(P) from V=M^-1 X columns. score_u =
x_u - (x_u P)/diag(P) elementwise — never materializes item x item.
"""

from __future__ import annotations

import argparse
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
from pipeline.game_rec.evaluation.stats import bootstrap_ci  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    P4, GradedCF, RP3B, build_relevance, get_panels, graded_ndcg,
    load_artifacts, longtail_recall, recall_at, snips_recall,
    split_profile_holdout, MIN_COOC)

log = get_logger("orchestration.ranker_gauntlet")


# ---------------------------------------------------------------- rankers

class VariantCF(GradedCF):
    """GradedCF with alternative item-item normalizations."""

    def __init__(self, scores, train_users, pool, kind: str = "condcos"):
        super().__init__(scores, train_users, pool)
        self.kind = kind
        self.deg_b = np.asarray(self.Xb.sum(axis=0)).ravel()
        self.n_train = self.Xb.shape[0]

    def sim_columns(self, need_appids):
        cols = [self.col[a] for a in need_appids if a in self.col]
        amap = {a: k for k, a in enumerate([a for a in need_appids if a in self.col])}
        if not cols:
            return sparse.csr_matrix((len(self.items), 0)), amap
        Cw = (self.Xw.T @ self.Xw[:, cols]).tocsr()
        Cb = (self.Xb.T @ self.Xb[:, cols]).tocsr()
        mask = Cb >= self.min_cooc
        if self.kind == "jaccard":
            Cbm = Cb.multiply(mask).tocoo()
            da = self.deg_b[Cbm.row]
            db = self.deg_b[np.array(cols)[Cbm.col]]
            data = Cbm.data / np.maximum(da + db - Cbm.data, 1)
            S = sparse.csr_matrix((data, (Cbm.row, Cbm.col)), shape=Cb.shape).tocsc()
        elif self.kind == "ppmi":
            Cbm = Cb.multiply(mask).tocoo()
            da = self.deg_b[Cbm.row]
            db = self.deg_b[np.array(cols)[Cbm.col]]
            pmi = np.log((Cbm.data * self.n_train) / np.maximum(da * db, 1e-9))
            data = np.maximum(pmi, 0.0)
            S = sparse.csr_matrix((data, (Cbm.row, Cbm.col)), shape=Cb.shape).tocsc()
        elif self.kind == "condasym":
            Cwm = Cw.multiply(mask)
            inv_cols = sparse.diags(1.0 / np.maximum(self.deg_w[cols], 1e-12))
            S = (Cwm @ inv_cols).tocsc()
        else:  # condcos
            Cwm = Cw.multiply(mask)
            dw = np.sqrt(np.maximum(self.deg_w, 1e-12))
            S = (sparse.diags(1.0 / dw) @ Cwm @ sparse.diags(1.0 / dw[cols])).tocsc()
        return S, amap


class EaseRanker:
    def __init__(self, scores, train_users, pool, lam: float = 200.0):
        d = scores[(scores["s"] > 0) & scores["appid"].isin(pool)]
        d = d[d["steamid"].isin(set(train_users))]
        self.items = np.array(sorted(d["appid"].unique()))
        self.col = {a: j for j, a in enumerate(self.items)}
        urow = {u: i for i, u in enumerate(sorted(d["steamid"].unique()))}
        r = d["steamid"].map(urow).values
        c = d["appid"].map(self.col).values
        X = sparse.csr_matrix((d["s"].values.astype(np.float64), (r, c)),
                              shape=(len(urow), len(self.items)))
        t = time.time()
        Xd = X.toarray()  # 1.1k x ~13k dense ~ 120MB float64 — OK once per fit
        M = lam * np.eye(Xd.shape[0]) + Xd @ Xd.T
        Minv = np.linalg.inv(M)
        self.V = Minv @ Xd                       # u x i
        diagP = (1.0 - np.einsum("ui,ui->i", Xd, self.V)) / lam
        self.diagP = np.maximum(diagP, 1e-9)
        self.lam = lam
        self.X = X
        log.info("EASE fit lam=%.0f: %d x %d (%.1fs)", lam, *Xd.shape, time.time() - t)

    def recommend(self, profile: dict[int, float], k: int, exclude: set[int]) -> list[int]:
        x = np.zeros(len(self.items))
        hit = 0
        for a, w in profile.items():
            j = self.col.get(a)
            if j is not None:
                x[j] = w
                hit += 1
        if hit == 0:
            return []
        # xP = (1/lam)(x - (x X^T) M^-1 X) = (1/lam)(x - (X x)^T V)
        xXt = self.X @ x                     # (u,)
        xP = (x - xXt @ self.V) / self.lam   # (i,)
        scores = x - xP / self.diagP         # x_u B
        for a in profile:
            j = self.col.get(a)
            if j is not None:
                scores[j] = -np.inf
        order = np.argsort(-scores)
        rec = []
        for j in order[: k * 3]:
            if not np.isfinite(scores[j]) or scores[j] <= 0:
                break
            a = int(self.items[j])
            if a not in exclude:
                rec.append(a)
            if len(rec) >= k:
                break
        return rec


class UserKNN:
    def __init__(self, scores, train_users, pool, topk_users: int = 50):
        d = scores[(scores["s"] > 0) & scores["appid"].isin(pool)]
        d = d[d["steamid"].isin(set(train_users))]
        self.items = np.array(sorted(d["appid"].unique()))
        self.col = {a: j for j, a in enumerate(self.items)}
        urow = {u: i for i, u in enumerate(sorted(d["steamid"].unique()))}
        r = d["steamid"].map(urow).values
        c = d["appid"].map(self.col).values
        self.X = sparse.csr_matrix((d["s"].values.astype(np.float32), (r, c)),
                                   shape=(len(urow), len(self.items)))
        self.row_norm = np.sqrt(np.asarray(self.X.multiply(self.X).sum(axis=1)).ravel())
        self.topk_users = topk_users

    def recommend(self, profile: dict[int, float], k: int, exclude: set[int]) -> list[int]:
        p = np.zeros(len(self.items), dtype=np.float32)
        hit = 0
        for a, w in profile.items():
            j = self.col.get(a)
            if j is not None:
                p[j] = w
                hit += 1
        if hit == 0:
            return []
        pn = np.linalg.norm(p)
        sims = np.asarray(self.X @ p).ravel() / np.maximum(self.row_norm * pn, 1e-12)
        top = np.argsort(-sims)[: self.topk_users]
        wts = np.maximum(sims[top], 0)
        agg = np.asarray((sparse.diags(wts) @ self.X[top]).sum(axis=0)).ravel()
        for a in profile:
            j = self.col.get(a)
            if j is not None:
                agg[j] = 0.0
        order = np.argsort(-agg)
        rec = []
        for j in order[: k * 3]:
            if agg[j] <= 0:
                break
            a = int(self.items[j])
            if a not in exclude:
                rec.append(a)
            if len(rec) >= k:
                break
        return rec


# ---------------------------------------------------------------- runner

PREFS = {
    "cap_a03_blend04": {"name": "per_user_cap", "params": {"base": "blend", "lam": 0.4, "alpha": 0.3}},
    "cap_a0_blend04": {"name": "per_user_cap", "params": {"base": "blend", "lam": 0.4, "alpha": 0.0}},
    # Stage C / 패자부활전 선호들
    "pvalue_eb": {"name": "pvalue_lognorm_eb", "params": {}},
    "pctl_game": {"name": "pctl_game", "params": {}},
    "anchor_binary": {"name": "anchor_binary", "params": {}},
}

RANKERS = ["condcos", "condasym", "jaccard", "ppmi", "p3a", "rp3b",
           "ease_l50", "ease_l200", "ease_l800", "userknn25", "userknn100"]


def run(panel: str = "dev", k: int = 20, seed: int = 42,
        prefs: list[str] | None = None, rankers: list[str] | None = None,
        tag: str = "stageB") -> pd.DataFrame:
    inter, game_stats, user_stats, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel, seed=seed)
    users = panels[panel]
    splits = split_profile_holdout(rel, users, seed=seed)
    users = sorted(splits)
    n_total = inter["steamid"].nunique()
    own_cnt = inter.groupby("appid").size()
    prop = (own_cnt / n_total).to_dict()
    own_pool = own_cnt[own_cnt.index.isin(pool)]
    pop_pct = own_pool.rank(pct=True).to_dict()

    rows = []
    outdir = P4 / tag
    outdir.mkdir(parents=True, exist_ok=True)
    use_prefs = {p: PREFS[p] for p in (prefs or list(PREFS))}
    use_rankers = rankers or RANKERS
    for pref_name, spec in use_prefs.items():
        scores = bs.compute(spec["name"], inter, game_stats, user_stats, **spec["params"])
        smap = {(int(u), int(a)): float(s) for u, a, s in
                scores[scores["s"] > 0][["steamid", "appid", "s"]].values}
        need = sorted({a for u in users for a in splits[u]["profile"]})
        for rk in use_rankers:
            t0 = time.time()
            try:
                S = amap = model = None
                if rk in ("condcos", "condasym", "jaccard", "ppmi"):
                    model = VariantCF(scores, panels["train"], pool, kind=rk)
                    S, amap = model.sim_columns(need)
                elif rk == "p3a":
                    model = RP3B(scores, panels["train"], pool, beta=0.0)
                elif rk == "rp3b":
                    model = RP3B(scores, panels["train"], pool, beta=0.6)
                elif rk.startswith("ease"):
                    model = EaseRanker(scores, panels["train"], pool,
                                       lam=float(rk.split("_l")[1]))
                elif rk.startswith("userknn"):
                    model = UserKNN(scores, panels["train"], pool,
                                    topk_users=int(rk.replace("userknn", "")))
                pu = []
                for u in users:
                    sp = splits[u]
                    prof_w = {a: smap.get((u, a), 0.0) for a in sp["profile"]}
                    prof_w = {a: w for a, w in prof_w.items() if w > 0} or dict(sp["profile"])
                    excl = set(sp["profile"])
                    if S is not None:
                        rec = model.recommend(prof_w, S, amap, k, excl)
                    else:
                        rec = model.recommend(prof_w, k, excl)
                    pu.append({"steamid": u,
                               "ndcg": graded_ndcg(sp["holdout"], rec, k),
                               "recall": recall_at(sp["holdout"], rec, k),
                               "snips": snips_recall(sp["holdout"], rec, k, prop),
                               "longtail": longtail_recall(sp["holdout"], rec, k, pop_pct)})
                pud = pd.DataFrame(pu)
                pud.to_csv(outdir / f"per_user_{pref_name}__{rk}.csv", index=False)
                row = {"pref": pref_name, "ranker": rk,
                       "sec": round(time.time() - t0, 1)}
                for m in ["ndcg", "recall", "snips", "longtail"]:
                    ci = bootstrap_ci(pud[m].dropna().values)
                    row[m] = round(ci["mean"], 4)
                    row[f"{m}_ci"] = f"[{ci['lo']:.3f},{ci['hi']:.3f}]"
                rows.append(row)
                log.info("%s x %s: ndcg=%.4f (%.1fs)", pref_name, rk, row["ndcg"], row["sec"])
            except Exception as e:
                log.exception("%s x %s failed", pref_name, rk)
                rows.append({"pref": pref_name, "ranker": rk,
                             "ndcg": np.nan, "error": f"{type(e).__name__}: {e}"})
    lb = pd.DataFrame(rows).sort_values(["pref", "ndcg"], ascending=[True, False])
    lb.to_csv(outdir / f"{tag}_leaderboard.csv", index=False)
    (outdir / "config.json").write_text(json.dumps(
        {"panel": panel, "k": k, "seed": seed, "rankers": use_rankers,
         "prefs": list(use_prefs), "ts": time.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
    return lb


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", default="dev")
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--prefs", type=str, default=None, help="comma list of PREFS keys")
    ap.add_argument("--rankers", type=str, default=None, help="comma list of RANKERS")
    ap.add_argument("--tag", type=str, default="stageB")
    args = ap.parse_args()
    lb = run(panel=args.panel, k=args.k, tag=args.tag,
             prefs=args.prefs.split(",") if args.prefs else None,
             rankers=args.rankers.split(",") if args.rankers else None)
    cols = [c for c in ["pref", "ranker", "ndcg", "recall", "snips", "longtail", "sec"]
            if c in lb.columns]
    print(lb[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
