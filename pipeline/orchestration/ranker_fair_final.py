"""Corrected fair ranker comparison (post T35 EASE cutoff-bug fix).

Only EASE had the score<=0 truncation (MF.recommend takes top-k by score, no
break) — so the fix affects EASE alone. Definitive fair comparison on dev:
userknn25, knnpd03, condcos, ease_l100(fair) on BOTH graded-NDCG (circular) and
the clean target-INDEPENDENT wishlist recall (audit_verify construction), with
paired bootstrap ease-vs-userknn on each. Read-only, dev only.
"""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    build_relevance, get_panels, graded_ndcg, load_artifacts,
    split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import EaseRanker, UserKNN, VariantCF  # noqa: E402
from pipeline.orchestration.ease_recheck import ease_reclist  # noqa: E402

log = get_logger("orchestration.ranker_fair_final")
rng = np.random.default_rng(3)


def pboot(diff, n=5000):
    diff = np.asarray([d for d in diff if np.isfinite(d)], float)
    b = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(n)]
    return float(diff.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main() -> int:
    inter, gs, us, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    sc = bs.compute("pvalue_lognorm_eb", inter, gs, us)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            sc[sc["s"] > 0][["steamid", "appid", "s"]].values}
    splits = split_profile_holdout(rel, panels["dev"], seed=42)
    uu = sorted(splits)

    knn = UserKNN(sc, panels["train"], pool, topk_users=25)
    knn_pd = UserKNN(sc, panels["train"], pool, topk_users=25, pop_beta=0.3)
    cc = VariantCF(sc, panels["train"], pool, kind="condcos")
    ez = EaseRanker(sc, panels["train"], pool, lam=100.0)

    # clean wishlist targets (audit_verify construction)
    con = sqlite3.connect(REPO / "data_collection" / "steam.db")
    wl = pd.read_sql_query("SELECT steamid,appid,date_added FROM wishlist WHERE date_added>0", con)
    con.close()
    owned = set(zip(inter["steamid"].astype(int), inter["appid"].astype(int)))
    dev = set(panels["dev"])
    wl = wl[wl["steamid"].isin(dev) & wl["appid"].isin(pool)].sort_values("date_added", ascending=False)
    tgt, prof_all = {}, {}
    for uid, g in wl.groupby("steamid"):
        t = [int(a) for a in g["appid"] if (int(uid), int(a)) not in owned][:10]
        if len(t) >= 3:
            tgt[int(uid)] = set(t)
    for u, g in rel[rel["steamid"].isin(tgt)].groupby("steamid"):
        prof_all[int(u)] = dict(zip(g["appid"].astype(int), g["rel"].astype(float)))

    def profw(u, ap):
        p = {a: smap.get((u, a), 0.0) for a in ap}
        return {a: w for a, w in p.items() if w > 0} or {a: 1.0 for a in ap}

    need = sorted({a for u in splits for a in profw(u, splits[u]["profile"])}
                  | {a for u in tgt for a in prof_all.get(u, {})})
    ccS, ccA = cc.sim_columns(need)

    reclist = {
        "userknn25": lambda u, p, k, e: knn.recommend(p, k, e),
        "knnpd03": lambda u, p, k, e: knn_pd.recommend(p, k, e),
        "condcos": lambda u, p, k, e: cc.recommend(p, ccS, ccA, k, e),
        "ease_l100_fair": lambda u, p, k, e: ease_reclist(ez, p, k, e),
    }
    nd, wlr = {n: {} for n in reclist}, {n: {} for n in reclist}
    for name, fn in reclist.items():
        for u, sp in splits.items():
            rec = fn(u, profw(u, sp["profile"]), 20, set(sp["profile"]))
            nd[name][u] = graded_ndcg(sp["holdout"], rec, k=20)
        for u, ts in tgt.items():
            rec = fn(u, profw(u, prof_all.get(u, {})), 20, set(prof_all.get(u, {})))
            wlr[name][u] = len(ts & set(rec[:20])) / len(ts)

    print(f"\n{'ranker':16s} {'devNDCG':>8s} {'wl_recall':>9s}")
    for name in reclist:
        print(f"{name:16s} {np.mean([nd[name][u] for u in uu]):8.4f} {np.mean(list(wlr[name].values())):9.4f}")
    for tgtn, base in [("NDCG", nd), ("wishlist", wlr)]:
        if tgtn == "NDCG":
            d = [nd["ease_l100_fair"][u] - nd["userknn25"][u] for u in uu]
        else:
            d = [wlr["ease_l100_fair"][u] - wlr["userknn25"][u] for u in sorted(tgt)]
        m, lo, hi = pboot(d)
        print(f"  ease_l100 - userknn25 [{tgtn}] = {m:+.4f} [{lo:+.4f},{hi:+.4f}] "
              f"{'SIG' if (lo>0 or hi<0) else 'ns'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
