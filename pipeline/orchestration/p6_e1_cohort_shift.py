"""E1 — cohort-shift quantification (winner's curse map). Post-verdict, descriptive.

Compares every registered slot's metric-A performance between:
  in-cohort : the fresh-854 zero-exposure snowball cohort (p4 artifacts,
              graph = frozen train-1,133) — evaluated twice: with the standard
              max(pt, completion) relevance AND with a playtime-only relevance
              (apples-to-apples with the OOD panel, whose cohort has no
              achievement rows).
  OOD       : the confirm_frozen one-shot outputs (read-only — the panel is
              NEVER re-queried; this script only reads the existing CSVs).

Deliverables: per-slot delta/shrinkage table, Kendall tau between slot
orderings, profile-size-stratified shrinkage for S5b/S1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.p6_common import (  # noqa: E402
    K, P4_DIR, P4_OUT, P6_DIR, SLOTS, build_relevance, fit_slot,
    graded_profile, load_artifacts, split_profile_holdout)
from pipeline.orchestration.preference_sweep import graded_ndcg  # noqa: E402

log = get_logger("orchestration.p6_e1")
OUT = P6_DIR / "e1_cohort_shift"


def build_relevance_pt_only(inter: pd.DataFrame, pool: set[int]) -> pd.DataFrame:
    """Playtime-percentile-only target — matches what the OOD cohort (zero
    achievement rows) effectively gets from build_relevance."""
    d = inter[inter["appid"].isin(pool)].copy()
    pt_p = bs._pos_pctl_within(d, "playtime_forever", "appid")
    out = d[["steamid", "appid"]].copy()
    out["rel"] = pt_p.fillna(0.0).astype(np.float32)
    return out[out["rel"] > 0]


def eval_slots(inter, gs, us, pool, rel, graph, users, seed=42):
    splits = split_profile_holdout(rel, users, seed=seed)
    uu = sorted(splits)
    need = sorted({a for u in uu for a in splits[u]["profile"]})
    per = {}
    for key in SLOTS:
        rec_fn, smap = fit_slot(key, inter, gs, us, pool, graph, need_appids=need)
        vals = {}
        for u in uu:
            sp = splits[u]
            prof = graded_profile(u, sp["profile"], smap, rel_fallback=sp["profile"])
            rec = rec_fn(prof, K, set(sp["profile"]))
            vals[u] = graded_ndcg(sp["holdout"], rec, K)
        per[key] = vals
        log.info("in-cohort %s: ndcg=%.4f", key, np.mean(list(vals.values())))
    return per, {u: len(splits[u]["profile"]) for u in uu}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inter, gs, us, pool = load_artifacts(P4_OUT)
    panels_p4 = json.loads((P4_DIR / "panels.json").read_text())
    graph = sorted(panels_p4["train"])
    frozen = (set(panels_p4["train"]) | set(panels_p4["dev"])
              | set(panels_p4["private"]))

    rel_std = build_relevance(inter, pool)
    counts = rel_std.groupby("steamid").size()
    fresh = sorted(int(u) for u in counts[counts >= 12].index if int(u) not in frozen)
    log.info("in-cohort fresh users: %d", len(fresh))

    per_std, _ = eval_slots(inter, gs, us, pool, rel_std, graph, fresh)
    rel_pt = build_relevance_pt_only(inter, pool)
    per_pt, prof_sizes_ic = eval_slots(inter, gs, us, pool, rel_pt, graph, fresh)

    # OOD side: read the one-shot outputs (never re-run)
    ood_mean, ood_per = {}, {}
    for key in SLOTS:
        pu = pd.read_csv(P6_DIR / "confirm_frozen" / f"per_user_{key}.csv")
        ood_mean[key] = float(pu["ndcg"].mean())
        ood_per[key] = pu.set_index("steamid")["ndcg"]

    rows = []
    for key in SLOTS:
        ic_std = float(np.mean(list(per_std[key].values())))
        ic_pt = float(np.mean(list(per_pt[key].values())))
        ood = ood_mean[key]
        rows.append({"slot": key, "ic_ndcg_std": round(ic_std, 4),
                     "ic_ndcg_ptonly": round(ic_pt, 4), "ood_ndcg": round(ood, 4),
                     "delta_vs_ptonly": round(ood - ic_pt, 4),
                     "shrink_pct": round(100 * (1 - ood / ic_pt), 1) if ic_pt else np.nan})
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "shift_table.csv", index=False)

    order_ic = tab.sort_values("ic_ndcg_ptonly", ascending=False)["slot"].tolist()
    order_ood = tab.sort_values("ood_ndcg", ascending=False)["slot"].tolist()
    tau = kendalltau([order_ic.index(s) for s in SLOTS],
                     [order_ood.index(s) for s in SLOTS])

    # profile-size stratification (S5b, S1): OOD profile sizes from p6 artifacts
    inter6, gs6, us6, pool6 = load_artifacts()
    rel6 = build_relevance(inter6, pool6)
    cnt6 = rel6.groupby("steamid").size()
    strata = {}
    for key in ("S5b", "S1"):
        ic = pd.Series(per_pt[key])
        ic_sz = pd.Series(prof_sizes_ic).reindex(ic.index)
        ood = ood_per[key]
        ood_sz = (cnt6.reindex(ood.index) * 0.7).round()
        buckets = [(0, 15), (15, 40), (40, 10 ** 9)]
        strata[key] = {}
        for lo, hi in buckets:
            m_ic = float(ic[(ic_sz >= lo) & (ic_sz < hi)].mean())
            m_ood = float(ood[(ood_sz >= lo) & (ood_sz < hi)].mean())
            n_ood = int(((ood_sz >= lo) & (ood_sz < hi)).sum())
            strata[key][f"[{lo},{hi})"] = {
                "ic_ptonly": round(m_ic, 4), "ood": round(m_ood, 4),
                "n_ood": n_ood,
                "shrink_pct": round(100 * (1 - m_ood / m_ic), 1) if m_ic else None}

    summary = {"n_in_cohort": len(fresh), "n_ood": int(len(ood_per["S5b"])),
               "kendall_tau": round(float(tau.statistic), 3),
               "kendall_p": round(float(tau.pvalue), 4),
               "profile_size_strata": strata}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))

    print(tab.sort_values("ood_ndcg", ascending=False).to_string(index=False))
    print(f"\nKendall tau (slot ordering, in-cohort pt-only vs OOD) = "
          f"{tau.statistic:.3f} (p={tau.pvalue:.4f})")
    print(json.dumps(strata, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
