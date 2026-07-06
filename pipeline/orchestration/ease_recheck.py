"""Audit follow-up (T33 CONFIRMED 'ease-truncated-lambda-grid-and-list-cutoff-bug').

The gauntlet's recommend() does `if score<=0: break` — harmless for similarity-sum
rankers (userknn/condcos, scores>=0) but EASE's linear scores legitimately go
negative, so its list truncates early and it is handicapped. Re-evaluate EASE
with (a) NO <=0 break (rank purely by score, top-k after exclude) and (b) a fuller
lambda grid, on dev, vs userknn (leader) and condcos (production) — on BOTH the
(circular) graded-NDCG and the target-INDEPENDENT wishlist recall. Read-only, dev only.
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
    build_relevance, get_panels, graded_ndcg, load_artifacts, snips_recall,
    split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import EaseRanker, UserKNN, VariantCF  # noqa: E402

log = get_logger("orchestration.ease_recheck")
rng = np.random.default_rng(11)


def paired_boot(diff, n=4000):
    diff = np.asarray([d for d in diff if np.isfinite(d)], float)
    if not len(diff):
        return (np.nan, np.nan, np.nan)
    b = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(n)]
    return float(diff.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def ease_reclist(ez, profile, k, exclude):
    """EASE top-k WITHOUT the score<=0 break (fair to negative linear scores)."""
    x = np.zeros(len(ez.items))
    hit = 0
    for a, w in profile.items():
        j = ez.col.get(a)
        if j is not None:
            x[j] = w; hit += 1
    if not hit:
        return []
    xXt = ez.X @ x
    scores = x - ((x - xXt @ ez.V) / ez.lam) / ez.diagP
    for a in profile:
        j = ez.col.get(a)
        if j is not None:
            scores[j] = -np.inf
    rec = []
    for j in np.argsort(-scores):
        a = int(ez.items[j])
        if a not in exclude:
            rec.append(a)
        if len(rec) >= k:
            break
    return rec


def main() -> int:
    inter, gs, us, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    prop = (inter.groupby("appid").size() / inter["steamid"].nunique()).to_dict()
    sc = bs.compute("pvalue_lognorm_eb", inter, gs, us)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            sc[sc["s"] > 0][["steamid", "appid", "s"]].values}
    splits = split_profile_holdout(rel, panels["dev"], seed=42)
    uu = sorted(splits)

    # wishlist independent targets (dev)
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

    def prof_of(u, sp):
        p = {a: smap.get((u, a), 0.0) for a in sp["profile"]}
        return {a: w for a, w in p.items() if w > 0} or dict(sp["profile"])

    def eval_model(name, rec_fn):
        nd, rc = {}, {}
        for u, sp in splits.items():
            rec = rec_fn(u, prof_of(u, sp), 20, set(sp["profile"]))
            nd[u] = graded_ndcg(sp["holdout"], rec, k=20)
            rc[u] = len(set(sp["holdout"]) & set(rec[:20])) / len(sp["holdout"]) if sp["holdout"] else np.nan
        wl_r = {}
        for u, ts in tgt.items():
            prof = {a: smap.get((u, a), 0.0) for a in rel[rel.steamid == u]["appid"].astype(int)}
            prof = {a: w for a, w in prof.items() if w > 0}
            excl = set(prof)
            rec = rec_fn(u, prof or {a: 1.0 for a in excl}, 20, excl)
            wl_r[u] = len(ts & set(rec[:20])) / len(ts)
        return nd, rc, wl_r

    # baselines
    knn = UserKNN(sc, panels["train"], pool, topk_users=25)
    cc = VariantCF(sc, panels["train"], pool, kind="condcos")
    need = set()
    for u in splits:
        need |= set(prof_of(u, splits[u]))
    for u in tgt:
        need |= {int(a) for a in rel[rel.steamid == u]["appid"].astype(int)}
    ccS, ccA = cc.sim_columns(sorted(need))

    def knn_fn(u, prof, k, excl):
        return knn.recommend(prof, k, excl)

    def cc_fn(u, prof, k, excl):
        return cc.recommend(prof, ccS, ccA, k, excl)

    results = {}
    for name, fn in [("userknn25", knn_fn), ("condcos", cc_fn)]:
        results[name] = eval_model(name, fn)

    for lam in [10, 30, 100, 300, 1000]:
        ez = EaseRanker(sc, panels["train"], pool, lam=float(lam))
        results[f"ease_l{lam}_fair"] = eval_model(f"ease_l{lam}", lambda u, p, k, e, _ez=ez: ease_reclist(_ez, p, k, e))

    print(f"\n{'config':18s} {'NDCG':>7s} {'recall':>7s} {'wl_recall':>9s}")
    for name, (nd, rc, wl_r) in results.items():
        print(f"{name:18s} {np.mean([nd[u] for u in uu]):7.4f} {np.mean([rc[u] for u in uu]):7.4f} {np.mean(list(wl_r.values())):9.4f}")

    # paired: best EASE vs userknn on NDCG
    best = max([k for k in results if k.startswith("ease")], key=lambda k: np.mean([results[k][0][u] for u in uu]))
    d = [results[best][0][u] - results["userknn25"][0][u] for u in uu]
    m, lo, hi = paired_boot(d)
    print(f"\nbest EASE = {best}; {best} - userknn25 NDCG = {m:+.4f} [{lo:+.4f},{hi:+.4f}] "
          f"{'SIG' if (lo>0 or hi<0) else 'ns'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
