"""P4 secondary fitness axis — held-out wishlist prediction (discovery patch).

Question: can the recommender surface games the user has DEMONSTRABLY wanted
(recent wishlist adds, not owned) from play behavior alone?

Per plan: wishlist is EVAL-ONLY (never an input — P4 rule); target = each panel
user's most recent wishlist adds (by date_added) that are in-pool and NOT owned;
input = the user's full played profile (no holdout hiding needed — targets are
disjoint from ownership by construction). Caveats logged: desire != enjoyment,
sale/marketing bursts, not strictly forward-in-time vs cumulative playtime.

Evaluates the current leader configs + null anchor on dev panel.
"""

from __future__ import annotations

import json
import sqlite3
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
    P4, RP3B, GradedCF, build_relevance, get_panels, load_artifacts)
from pipeline.orchestration.ranker_gauntlet import UserKNN  # noqa: E402

log = get_logger("orchestration.wishlist_axis")

CONFIGS = [
    ("pvalue_eb__userknn25", {"name": "pvalue_lognorm_eb", "params": {}}, "userknn"),
    ("pctl_game__userknn25", {"name": "pctl_game", "params": {}}, "userknn"),
    ("cap_blend__rp3b", {"name": "per_user_cap",
                         "params": {"base": "blend", "lam": 0.4, "alpha": 0.3}}, "rp3b"),
    ("cap_blend__condcos", {"name": "per_user_cap",
                            "params": {"base": "blend", "lam": 0.4, "alpha": 0.3}}, "condcos"),
    ("random_support__userknn25", {"name": "random_support", "params": {}}, "userknn"),
]

K = 20
N_TARGET = 10  # most recent in-pool non-owned wishlist adds per user


def main() -> int:
    inter, game_stats, user_stats, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    users = panels["dev"]

    con = sqlite3.connect(REPO_ROOT / "data_collection" / "steam.db")
    wl = pd.read_sql_query(
        "SELECT steamid, appid, date_added FROM wishlist WHERE date_added>0", con)
    con.close()
    owned_pairs = set(zip(inter["steamid"].astype(int), inter["appid"].astype(int)))

    # per-user targets: most recent in-pool, non-owned wishlist adds
    wl = wl[wl["steamid"].isin(set(users)) & wl["appid"].isin(pool)]
    wl = wl.sort_values("date_added", ascending=False)
    targets: dict[int, set[int]] = {}
    for uid, grp in wl.groupby("steamid"):
        t = [int(a) for a in grp["appid"]
             if (int(uid), int(a)) not in owned_pairs][:N_TARGET]
        if len(t) >= 3:
            targets[int(uid)] = set(t)
    log.info("wishlist targets: %d/%d dev users (>=3 in-pool non-owned adds)",
             len(targets), len(users))

    # full played profile per user (rel>0 items)
    prof_all = {int(u): dict(zip(g["appid"].astype(int), g["rel"].astype(float)))
                for u, g in rel[rel["steamid"].isin(targets)].groupby("steamid")}

    rows = []
    for cfg_name, spec, ranker in CONFIGS:
        t0 = time.time()
        scores = bs.compute(spec["name"], inter, game_stats, user_stats, **spec["params"])
        smap = {(int(u), int(a)): float(s) for u, a, s in
                scores[scores["s"] > 0][["steamid", "appid", "s"]].values}
        if ranker == "userknn":
            model = UserKNN(scores, panels["train"], pool, topk_users=25)
        elif ranker == "rp3b":
            model = RP3B(scores, panels["train"], pool, beta=0.6)
        else:
            model = GradedCF(scores, panels["train"], pool)
            need = sorted({a for u in targets for a in prof_all.get(u, {})})
            S, amap = model.sim_columns(need)
        recalls = []
        for u, tset in targets.items():
            prof = {a: smap.get((u, a), 0.0) for a in prof_all.get(u, {})}
            prof = {a: w for a, w in prof.items() if w > 0} or prof_all.get(u, {})
            excl = set(prof_all.get(u, {}))  # exclude owned/played
            if ranker == "condcos":
                rec = model.recommend(prof, S, amap, K, excl)
            else:
                rec = model.recommend(prof, K, excl)
            recalls.append(len(tset & set(rec[:K])) / len(tset))
        ci = bootstrap_ci(np.array(recalls))
        rows.append({"config": cfg_name, "wl_recall@20": round(ci["mean"], 4),
                     "ci": f"[{ci['lo']:.3f},{ci['hi']:.3f}]",
                     "n_users": len(recalls), "sec": round(time.time() - t0, 1)})
        log.info("%s: wl_recall=%.4f", cfg_name, ci["mean"])
    lb = pd.DataFrame(rows)
    out = P4 / "wishlist_axis"
    out.mkdir(exist_ok=True)
    lb.to_csv(out / "leaderboard.csv", index=False)
    print(lb.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
