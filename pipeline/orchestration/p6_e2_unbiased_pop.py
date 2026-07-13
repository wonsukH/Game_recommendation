"""E2 — unbiased popularity / propensity re-estimation. Exploration pool only.

The snowball cohort's ownership rates are a biased popularity prior (immersed
reviewer-linked users). The depth=-1 random cohort gives the first UNBIASED
ownership-rate estimate. Deliverables:
  1. outputs/p6/pop_unbiased.json — appid -> ownership rate among OOD usable
     users (a P5 serving artifact: popularity prior / propensity source).
  2. Distortion analysis: biased-vs-unbiased rank shifts (top movers).
  3. SNIPS sensitivity: re-scores the seeded 300-user exploration dry-run with
     OOD-only propensities vs the mixed-snapshot propensities — does the slot
     ordering change? (Expected null = the in-cohort SNIPS machinery is safe.)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.p6_common import (  # noqa: E402
    K, P4_DIR, P6_DIR, P6_OUT, assert_firewall, build_relevance, fit_slot,
    graded_profile, load_artifacts, load_panels, split_profile_holdout)
from pipeline.orchestration.preference_sweep import snips_recall  # noqa: E402

log = get_logger("orchestration.p6_e2")
OUT = P6_DIR / "e2_unbiased_pop"
DB = REPO_ROOT / "data_collection" / "steam.db"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inter, gs, us, pool = load_artifacts()

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    ood_ids = {int(r[0]) for r in con.execute(
        "SELECT steamid FROM user_queue WHERE depth=-1").fetchall()}
    con.close()

    in_snap = set(inter["steamid"].astype(int).unique())
    ood = ood_ids & in_snap
    biased = in_snap - ood_ids
    log.info("snapshot users: OOD=%d biased=%d", len(ood), len(biased))

    d = inter[["steamid", "appid"]].copy()
    d["steamid"] = d["steamid"].astype(int)
    own_ood = d[d["steamid"].isin(ood)].groupby("appid").size()
    own_bia = d[d["steamid"].isin(biased)].groupby("appid").size()
    rate_ood = (own_ood / len(ood)).rename("rate_ood")
    rate_bia = (own_bia / len(biased)).rename("rate_biased")

    pop = pd.concat([rate_ood, rate_bia], axis=1).fillna(0.0)
    pop = pop[pop.index.isin(pool)]
    (P6_OUT / "pop_unbiased.json").write_text(json.dumps(
        {str(int(a)): round(float(r), 8) for a, r in rate_ood.items()
         if int(a) in pool}))
    log.info("pop_unbiased.json written: %d appids", int((rate_ood.index.isin(pool)).sum()))

    # distortion: rank shift among the union of both top-200s
    pop["rank_ood"] = pop["rate_ood"].rank(ascending=False)
    pop["rank_bia"] = pop["rate_biased"].rank(ascending=False)
    top = pop[(pop["rank_ood"] <= 200) | (pop["rank_bia"] <= 200)].copy()
    top["rank_shift"] = top["rank_bia"] - top["rank_ood"]
    names = gs.set_index("appid")["name"]
    top["name"] = names.reindex(top.index)
    movers = top.reindex(top["rank_shift"].abs().sort_values(ascending=False).index)
    movers.head(30).to_csv(OUT / "top_movers.csv")
    corr = float(pop["rate_ood"].corr(pop["rate_biased"], method="spearman"))
    log.info("popularity spearman (OOD vs biased, pool) = %.4f", corr)

    # SNIPS sensitivity on the seeded exploration dry-run (same draw as dryrun_a)
    panels = load_panels()
    rel = build_relevance(inter, pool)
    counts = rel.groupby("steamid").size()
    pool_users = [u for u in panels["exploration"] if u in counts.index]
    rng = np.random.default_rng(777)
    users = sorted(int(u) for u in rng.choice(pool_users, size=min(300, len(pool_users)),
                                              replace=False))
    assert_firewall(users, panels)
    splits = split_profile_holdout(rel, users, seed=42)
    uu = sorted(splits)
    need = sorted({a for u in uu for a in splits[u]["profile"]})

    n_all = inter["steamid"].nunique()
    prop_mixed = (inter.groupby("appid").size() / n_all).to_dict()
    prop_ood = rate_ood.to_dict()

    panels_p4 = json.loads((P4_DIR / "panels.json").read_text())
    graph = sorted(panels_p4["train"])
    res = {}
    for key in ("S5b", "S1", "S2", "S0a"):
        rec_fn, smap = fit_slot(key, inter, gs, us, pool, graph, need_appids=need)
        sm, so = [], []
        for u in uu:
            sp = splits[u]
            prof = graded_profile(u, sp["profile"], smap, rel_fallback=sp["profile"])
            rec = rec_fn(prof, K, set(sp["profile"]))
            sm.append(snips_recall(sp["holdout"], rec, K, prop_mixed))
            so.append(snips_recall(sp["holdout"], rec, K, prop_ood))
        res[key] = {"snips_mixed": round(float(np.nanmean(sm)), 4),
                    "snips_ood_prop": round(float(np.nanmean(so)), 4)}
        log.info("%s: snips mixed=%.4f ood-prop=%.4f", key,
                 res[key]["snips_mixed"], res[key]["snips_ood_prop"])

    order_m = sorted(res, key=lambda k: -res[k]["snips_mixed"])
    order_o = sorted(res, key=lambda k: -res[k]["snips_ood_prop"])
    summary = {"n_ood_users": len(ood), "n_biased_users": len(biased),
               "pop_spearman_ood_vs_biased": round(corr, 4),
               "snips_sensitivity": res,
               "ordering_mixed": order_m, "ordering_ood_prop": order_o,
               "ordering_unchanged": order_m == order_o}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print("\ntop rank movers (biased rank - OOD rank):")
    print(movers.head(15)[["name", "rate_ood", "rate_biased", "rank_ood",
                           "rank_bia", "rank_shift"]].to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
