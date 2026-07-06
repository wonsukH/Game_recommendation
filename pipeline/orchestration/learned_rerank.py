"""Audit follow-up (T33 'no-learned-reranker-only-preference-simplex').

P4 only ever did preference x ranker; never a LEARNED rerank over candidate
features. Build a monotone HistGradientBoosting reranker over candidate-level
features [userknn_score, condcos_score, pop_pct, lib_size] — a learned fusion +
popularity reweighting (a superset of what knnpd03's hand-set beta=0.3 does).
Train on train-panel users' holdout engagement; evaluate ONCE on dev vs userknn
(leader) and knnpd03 on BOTH graded-NDCG (circular) and the target-INDEPENDENT
wishlist recall. If it can't beat userknn on the independent target, the learned-
fusion gap is honestly closed. Read-only, dev/train only; no private, no API.
"""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import sparse

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    build_relevance, get_panels, graded_ndcg, load_artifacts,
    split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import UserKNN, VariantCF  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402

log = get_logger("orchestration.learned_rerank")


def main() -> int:
    inter, gs, us, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    sc = bs.compute("pvalue_lognorm_eb", inter, gs, us)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            sc[sc["s"] > 0][["steamid", "appid", "s"]].values}
    lib = inter.groupby("steamid").size().to_dict()

    knn = UserKNN(sc, panels["train"], pool, topk_users=25)
    knn_pd = UserKNN(sc, panels["train"], pool, topk_users=25, pop_beta=0.3)
    cc = VariantCF(sc, panels["train"], pool, kind="condcos")
    items = knn.items
    col = knn.col
    i_pop = np.asarray((knn.X > 0).sum(axis=0)).ravel().astype(float)
    pop_pct = pd.Series(i_pop).rank(pct=True).values  # popularity percentile

    def knn_vec(prof, model):
        p = np.zeros(len(items), np.float32)
        for a, w in prof.items():
            j = col.get(a)
            if j is not None:
                p[j] = w
        pn = np.linalg.norm(p)
        if pn == 0:
            return None
        sims = np.asarray(model.X @ p).ravel() / np.maximum(model.row_norm * pn, 1e-12)
        top = np.argsort(-sims)[: model.topk_users]
        agg = np.asarray((sparse.diags(np.maximum(sims[top], 0)) @ model.X[top]).sum(axis=0)).ravel()
        if model.pop_disc is not None:
            agg = agg * model.pop_disc
        return agg

    # condcos full score vector via sim columns (align to knn.items)
    ccS_cache = {}
    def cc_vec(prof):
        need = [a for a in prof if a in cc.col]
        key = tuple(sorted(need))
        if key not in ccS_cache:
            S, amap = cc.sim_columns(need)
            ccS_cache[key] = (S, amap)
        S, amap = ccS_cache[key]
        w = np.zeros(S.shape[1])
        for a in need:
            w[amap[a]] += prof[a]
        acc_cc = np.asarray(S @ w).ravel()  # over cc.items order
        # remap cc.items -> knn.items
        out = np.zeros(len(items))
        for jj, a in enumerate(cc.items):
            k = col.get(int(a))
            if k is not None:
                out[k] = acc_cc[jj]
        return out

    def prof_of(u, profset):
        p = {a: smap.get((u, a), 0.0) for a in profset}
        return {a: w for a, w in p.items() if w > 0} or {a: 1.0 for a in profset}

    def feats(u, prof, cand_idx):
        kv = knn_vec(prof, knn)
        cv = cc_vec(prof)
        n = len(cand_idx)
        return np.column_stack([kv[cand_idx], cv[cand_idx], pop_pct[cand_idx],
                                np.full(n, np.log1p(lib.get(u, 1)))])

    # ---- training data: train-panel users, candidates = knn top-80 U holdout+ ----
    tr_splits = split_profile_holdout(rel, panels["train"], seed=1)
    Xtr, ytr = [], []
    for u, sp in tr_splits.items():
        prof = prof_of(u, sp["profile"])
        kv = knn_vec(prof, knn)
        if kv is None:
            continue
        excl = set(sp["profile"])
        cand = [j for j in np.argsort(-kv)[:80] if int(items[j]) not in excl]
        pos = [col[a] for a in sp["holdout"] if a in col and int(items[col[a]]) not in excl]
        cand = sorted(set(cand) | set(pos))
        if not cand:
            continue
        Xtr.append(feats(u, prof, np.array(cand)))
        ytr.append(np.array([sp["holdout"].get(int(items[j]), 0.0) for j in cand]))
    Xtr = np.vstack(Xtr); ytr = np.concatenate(ytr)
    log.info("train rerank rows: %d (%.1f%% positive)", len(ytr), 100 * (ytr > 0).mean())
    mdl = HistGradientBoostingRegressor(
        max_iter=200, max_depth=3, learning_rate=0.05, l2_regularization=1.0,
        monotonic_cst=[1, 1, 0, 0], random_state=0)  # increasing in knn, condcos
    mdl.fit(Xtr, ytr)

    # ---- eval on dev ----
    dev_splits = split_profile_holdout(rel, panels["dev"], seed=42)
    con = sqlite3.connect(REPO / "data_collection" / "steam.db")
    wl = pd.read_sql_query("SELECT steamid,appid,date_added FROM wishlist WHERE date_added>0", con)
    con.close()
    owned = set(zip(inter["steamid"].astype(int), inter["appid"].astype(int)))
    dev = set(panels["dev"])
    wl = wl[wl["steamid"].isin(dev) & wl["appid"].isin(pool)].sort_values("date_added", ascending=False)
    tgt = {}
    for uid, g in wl.groupby("steamid"):
        t = [int(a) for a in g["appid"] if (int(uid), int(a)) not in owned][:10]
        if len(t) >= 3:
            tgt[int(uid)] = set(t)

    def rerank_reclist(u, prof, k, excl):
        kv = knn_vec(prof, knn)
        if kv is None:
            return []
        cand = np.array([j for j in np.argsort(-kv)[:120] if int(items[j]) not in excl])
        pred = mdl.predict(feats(u, prof, cand))
        return [int(items[cand[i]]) for i in np.argsort(-pred)[:k]]

    def eval_all(rec_fn):
        nd = []
        for u, sp in dev_splits.items():
            rec = rec_fn(u, prof_of(u, sp["profile"]), 20, set(sp["profile"]))
            nd.append(graded_ndcg(sp["holdout"], rec, k=20))
        wlr = []
        for u, ts in tgt.items():
            profset = set(rel[rel.steamid == u]["appid"].astype(int))
            rec = rec_fn(u, prof_of(u, profset), 20, profset)
            wlr.append(len(ts & set(rec[:20])) / len(ts))
        return float(np.mean(nd)), float(np.mean(wlr))

    print(f"\n{'config':16s} {'devNDCG':>8s} {'wl_recall':>9s}")
    for name, fn in [("userknn25", lambda u, p, k, e: knn.recommend(p, k, e)),
                     ("knnpd03", lambda u, p, k, e: knn_pd.recommend(p, k, e)),
                     ("learned_rerank", rerank_reclist)]:
        nd, wlr = eval_all(fn)
        print(f"{name:16s} {nd:8.4f} {wlr:9.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
