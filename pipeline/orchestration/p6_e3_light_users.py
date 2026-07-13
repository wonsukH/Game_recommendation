"""E3 — light-user segment (5-11 effective items): DESCRIPTIVE ONLY, no verdicts.

The unbiased cohort's median library is ~8 games — below the >=12 panel filter.
Question: does personalization beat POP at all for the *typical* random Steam
user, and does the P6 winner hold below the eligibility cutoff? Variance is
huge at this sparsity (1-3 holdout items) — report means + CIs, decide nothing.

Uses the frozen `light` stratum (disjoint from confirm/reserve by construction).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.evaluation.stats import bootstrap_ci  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.p6_common import (  # noqa: E402
    K, P4_DIR, P6_DIR, SLOTS, assert_firewall, build_relevance, fit_slot,
    graded_profile, load_artifacts, load_panels, pop_ranker,
    split_profile_holdout)
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    graded_ndcg, recall_at)

log = get_logger("orchestration.p6_e3")
OUT = P6_DIR / "e3_light_users"
EVAL_SLOTS = ("S5b", "S1", "S2", "S4", "null")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inter, gs, us, pool = load_artifacts()
    panels = load_panels()
    rel = build_relevance(inter, pool)
    counts = rel.groupby("steamid").size()
    light = [int(u) for u in panels["light"] if u in counts.index]
    assert_firewall(light, panels)
    log.info("light users (5-11 effective items): %d", len(light))

    splits = split_profile_holdout(rel, light, seed=42)
    uu = sorted(splits)
    need = sorted({a for u in uu for a in splits[u]["profile"]})
    panels_p4 = json.loads((P4_DIR / "panels.json").read_text())
    graph = sorted(panels_p4["train"])

    rows = []
    for key in EVAL_SLOTS:
        rec_fn, smap = fit_slot(key, inter, gs, us, pool, graph, need_appids=need)
        nd, rc = [], []
        for u in uu:
            sp = splits[u]
            prof = graded_profile(u, sp["profile"], smap, rel_fallback=sp["profile"])
            rec = rec_fn(prof, K, set(sp["profile"]))
            nd.append(graded_ndcg(sp["holdout"], rec, K))
            rc.append(recall_at(sp["holdout"], rec, K))
        ci_n, ci_r = bootstrap_ci(np.array(nd)), bootstrap_ci(np.array(rc))
        rows.append({"slot": key, "ndcg": round(ci_n["mean"], 4),
                     "ndcg_ci": f"[{ci_n['lo']:.4f},{ci_n['hi']:.4f}]",
                     "recall": round(ci_r["mean"], 4),
                     "recall_ci": f"[{ci_r['lo']:.4f},{ci_r['hi']:.4f}]",
                     "n": len(nd)})
        log.info("%s: ndcg=%.4f recall=%.4f", key, ci_n["mean"], ci_r["mean"])

    pop_fn = pop_ranker(inter, pool, graph)
    nd, rc = [], []
    for u in uu:
        sp = splits[u]
        rec = pop_fn(dict(sp["profile"]), K, set(sp["profile"]))
        nd.append(graded_ndcg(sp["holdout"], rec, K))
        rc.append(recall_at(sp["holdout"], rec, K))
    ci_n, ci_r = bootstrap_ci(np.array(nd)), bootstrap_ci(np.array(rc))
    rows.append({"slot": "POP", "ndcg": round(ci_n["mean"], 4),
                 "ndcg_ci": f"[{ci_n['lo']:.4f},{ci_n['hi']:.4f}]",
                 "recall": round(ci_r["mean"], 4),
                 "recall_ci": f"[{ci_r['lo']:.4f},{ci_r['hi']:.4f}]", "n": len(nd)})

    tab = pd.DataFrame(rows).sort_values("ndcg", ascending=False)
    tab.to_csv(OUT / "leaderboard.csv", index=False)
    hold_sizes = pd.Series({u: len(splits[u]["holdout"]) for u in uu})
    meta = {"n_users": len(uu),
            "holdout_items_mean": round(float(hold_sizes.mean()), 2),
            "holdout_items_median": float(hold_sizes.median()),
            "note": "DESCRIPTIVE ONLY — no decisions; variance is structurally huge"}
    (OUT / "summary.json").write_text(json.dumps(meta, indent=2))
    print(tab.to_string(index=False))
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
