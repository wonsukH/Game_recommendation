"""Decisive read-only checks for the T32 adversarial audit.

(A) Circularity: per-game Spearman(pref score, relevance target). ~1 => the
    preference is a monotone copy of its own ground truth (home-field).
(B) Target-INDEPENDENT test: S0/S1/S2/S4/null on the wishlist holdout (future
    non-owned wishlist adds — a signal with NO playtime provenance), paired
    bootstrap S0-vs-S1. This is the one axis build_relevance does not touch.
(C) Primary-metric honesty: dev-panel S0 vs S1 on graded-NDCG, recall@20,
    SNIPS with PAIRED bootstrap — does the pop-discount cost recall (audit
    claims Δrecall -0.011 SIG) while being ns on NDCG?

Dev panel only (already exposed/tuning); no private reuse, no metered API,
no writes to db/outputs.
"""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    build_relevance, get_panels, graded_ndcg, load_artifacts, snips_recall,
    split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import UserKNN  # noqa: E402

log = get_logger("orchestration.audit_verify")
rng = np.random.default_rng(7)


def paired_boot(diff, n=5000):
    diff = np.asarray(diff, float)
    diff = diff[np.isfinite(diff)]
    if not len(diff):
        return (np.nan, np.nan, np.nan)
    bs_ = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(n)]
    return float(diff.mean()), float(np.percentile(bs_, 2.5)), float(np.percentile(bs_, 97.5))


def recall_at(holdout, rec, k=20):
    hs = set(holdout)
    return len(hs & set(rec[:k])) / len(hs) if hs else np.nan


def main() -> int:
    inter, gs, us, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    prop = (inter.groupby("appid").size() / inter["steamid"].nunique()).to_dict()

    # ---------- (A) circularity ----------
    print("\n=== (A) per-game Spearman(pref score, rel target) — ~1 means circular ===")
    reld = rel.set_index(["steamid", "appid"])["rel"]
    for name in ["pvalue_lognorm_eb", "pctl_game", "per_user_cap"]:
        sc = bs.compute(name, inter, gs, us)
        m = sc.merge(rel[["steamid", "appid", "rel"]], on=["steamid", "appid"])
        m = m[m["s"] > 0]
        rhos = []
        for a, g in m.groupby("appid"):
            if len(g) >= 8 and g["s"].nunique() > 1 and g["rel"].nunique() > 1:
                rhos.append(spearmanr(g["s"], g["rel"]).statistic)
        rhos = np.array([r for r in rhos if np.isfinite(r)])
        print(f"  {name:22s}: median per-game rho = {np.median(rhos):.3f}  (n_games={len(rhos)})")

    # ---------- shared: build scored maps + knn models ----------
    def smap_of(name, **p):
        sc = bs.compute(name, inter, gs, us, **p)
        return {(int(u), int(a)): float(s) for u, a, s in
                sc[sc["s"] > 0][["steamid", "appid", "s"]].values}, sc
    pv_map, pv_sc = smap_of("pvalue_lognorm_eb")
    pc_map, pc_sc = smap_of("pctl_game")
    knn_pv = UserKNN(pv_sc, panels["train"], pool, topk_users=25)
    knn_pv_pd = UserKNN(pv_sc, panels["train"], pool, topk_users=25, pop_beta=0.3)
    knn_pc = UserKNN(pc_sc, panels["train"], pool, topk_users=25)

    # ---------- (C) primary-metric honesty: S0 vs S1 on dev, paired ----------
    print("\n=== (C) dev S0(pvalue x knnpd03) vs S1(pvalue x userknn) — PAIRED ===")
    splits = split_profile_holdout(rel, panels["dev"], seed=42)
    def eval_knn(model, smap):
        nd, rc, sn = {}, {}, {}
        for u, sp in splits.items():
            prof = {a: smap.get((u, a), 0.0) for a in sp["profile"]}
            prof = {a: w for a, w in prof.items() if w > 0} or dict(sp["profile"])
            rec = model.recommend(prof, 20, set(sp["profile"]))
            nd[u] = graded_ndcg(sp["holdout"], rec, k=20)
            rc[u] = recall_at(sp["holdout"], rec, 20)
            sn[u] = snips_recall(sp["holdout"], rec, 20, prop)
        return nd, rc, sn
    nd0, rc0, sn0 = eval_knn(knn_pv_pd, pv_map)
    nd1, rc1, sn1 = eval_knn(knn_pv, pv_map)
    uu = sorted(splits)
    for label, a, b in [("NDCG", nd0, nd1), ("recall@20", rc0, rc1), ("SNIPS", sn0, sn1)]:
        d = [a[u] - b[u] for u in uu]
        m, lo, hi = paired_boot(d)
        sig = "SIG" if (lo > 0 or hi < 0) else "ns"
        print(f"  {label:10s} S0={np.mean([a[u] for u in uu]):.4f} S1={np.mean([b[u] for u in uu]):.4f} "
              f"| S0-S1 = {m:+.4f} [{lo:+.4f},{hi:+.4f}] {sig}")

    # ---------- (B) target-INDEPENDENT: wishlist holdout ----------
    print("\n=== (B) wishlist holdout (target-INDEPENDENT of playtime) ===")
    con = sqlite3.connect(REPO / "data_collection" / "steam.db")
    wl = pd.read_sql_query("SELECT steamid, appid, date_added FROM wishlist WHERE date_added>0", con)
    con.close()
    owned = set(zip(inter["steamid"].astype(int), inter["appid"].astype(int)))
    dev = set(panels["dev"])
    wl = wl[wl["steamid"].isin(dev) & wl["appid"].isin(pool)].sort_values("date_added", ascending=False)
    tgt = {}
    for uid, g in wl.groupby("steamid"):
        t = [int(a) for a in g["appid"] if (int(uid), int(a)) not in owned][:10]
        if len(t) >= 3:
            tgt[int(uid)] = set(t)
    prof_all = {int(u): dict(zip(gp["appid"].astype(int), gp["rel"].astype(float)))
                for u, gp in rel[rel["steamid"].isin(tgt)].groupby("steamid")}
    print(f"  wishlist-eligible dev users: {len(tgt)}")
    configs = {"S0_pv_knnpd03": (knn_pv_pd, pv_map), "S1_pv_userknn": (knn_pv, pv_map),
               "S2_pctl_userknn": (knn_pc, pc_map)}
    wl_rec = {}
    for name, (model, smap) in configs.items():
        per = {}
        for u, ts in tgt.items():
            prof = {a: smap.get((u, a), 0.0) for a in prof_all.get(u, {})}
            prof = {a: w for a, w in prof.items() if w > 0} or prof_all.get(u, {})
            rec = model.recommend(prof, 20, set(prof_all.get(u, {})))
            per[u] = len(ts & set(rec[:20])) / len(ts)
        wl_rec[name] = per
        print(f"  {name:16s} wl_recall@20 = {np.mean(list(per.values())):.4f}")
    du = sorted(tgt)
    d = [wl_rec["S0_pv_knnpd03"][u] - wl_rec["S1_pv_userknn"][u] for u in du]
    m, lo, hi = paired_boot(d)
    sig = "SIG" if (lo > 0 or hi < 0) else "ns"
    print(f"  >>> S0-S1 on INDEPENDENT wishlist target = {m:+.4f} [{lo:+.4f},{hi:+.4f}] {sig}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
