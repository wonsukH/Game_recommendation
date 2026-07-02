"""P4 learned candidate (#20, honest lightweight form) — simplex-weight search.

Learns s = w1*pt_pctl + w2*completion_pctl + w3*pvalue_s by BLACK-BOX search
against downstream NDCG with the Stage-B winning ranker (user-KNN25).

Discipline (overfit guards):
- weights tuned ONLY on a train-INTERNAL panel (sampled from panels["train"];
  the tuning graph excludes those users — leave-user-out within train).
- dev panel touched ONCE with the single chosen weight vector.
- if the learned blend does not significantly beat pctl_game x userknn on dev,
  it is logged as a NEGATIVE result (pre-declared).

Note we deliberately do NOT train f(features)->rel regression: rel is itself a
function of these features (identity trap). The learnable object is the blend
that maximizes DOWNSTREAM ranking quality.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.evaluation.stats import bootstrap_ci, paired_bootstrap_diff  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    P4, build_relevance, get_panels, graded_ndcg, load_artifacts,
    split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import UserKNN  # noqa: E402

log = get_logger("orchestration.learned_blend")

SIMPLEX = [
    (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
    (0.5, 0.5, 0.0), (0.5, 0.0, 0.5), (0.0, 0.5, 0.5),
    (0.34, 0.33, 0.33), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6),
    (0.7, 0.0, 0.3), (0.3, 0.0, 0.7),
]


def blend_scores(feats: dict[str, pd.DataFrame], w) -> pd.DataFrame:
    out = feats["pt"].copy()
    out["s"] = (w[0] * feats["pt"]["s"].values
                + w[1] * feats["comp"]["s"].values
                + w[2] * feats["pv"]["s"].values).astype(np.float32)
    return out


def eval_on(scores, users, splits, train_users, pool, k=20):
    smap = {(int(u), int(a)): float(s) for u, a, s in
            scores[scores["s"] > 0][["steamid", "appid", "s"]].values}
    model = UserKNN(scores, train_users, pool, topk_users=25)
    vals = []
    for u in users:
        sp = splits[u]
        prof = {a: smap.get((u, a), 0.0) for a in sp["profile"]}
        prof = {a: w for a, w in prof.items() if w > 0} or dict(sp["profile"])
        rec = model.recommend(prof, k, set(sp["profile"]))
        vals.append(graded_ndcg(sp["holdout"], rec, k))
    return np.array(vals)


def main() -> int:
    inter, game_stats, user_stats, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)

    # feature frames (aligned to inter rows)
    feats = {
        "pt": bs.compute("pctl_game", inter, game_stats, user_stats),
        "pv": bs.compute("pvalue_lognorm_eb", inter, game_stats, user_stats),
    }
    # completion pctl alone: blend with lam=0 gives pure completion pctl w/ pt fallback
    feats["comp"] = bs.compute("ach_completion_pctl_blend", inter, game_stats,
                               user_stats, lam=0.0)

    # train-internal tuning panel (never dev/private)
    rng = np.random.default_rng(7)
    internal = sorted(rng.choice(panels["train"], size=120, replace=False).tolist())
    tune_train = sorted(set(panels["train"]) - set(internal))
    splits_int = split_profile_holdout(rel, internal, seed=42)
    users_int = sorted(splits_int)

    results = []
    for w in SIMPLEX:
        s = blend_scores(feats, w)
        vals = eval_on(s, users_int, splits_int, tune_train, pool)
        results.append({"w": w, "ndcg": float(vals.mean())})
        log.info("w=%s internal ndcg=%.4f", w, vals.mean())
    best = max(results, key=lambda r: r["ndcg"])
    log.info("BEST internal: %s", best)

    # single dev evaluation vs pctl_game baseline (S2)
    splits_dev = split_profile_holdout(rel, panels["dev"], seed=42)
    users_dev = sorted(splits_dev)
    s_best = blend_scores(feats, best["w"])
    v_best = eval_on(s_best, users_dev, splits_dev, panels["train"], pool)
    v_base = eval_on(feats["pt"], users_dev, splits_dev, panels["train"], pool)
    diff = paired_bootstrap_diff(v_base, v_best)
    out = {
        "internal_results": results, "best_w": best,
        "dev_learned": bootstrap_ci(v_best), "dev_pctl_base": bootstrap_ci(v_base),
        "paired_learned_minus_base": diff,
        "verdict": ("ADOPT-candidate" if diff["significant"] and diff["mean_diff"] > 0
                    else "NEGATIVE (pre-declared): learned blend does not beat pctl on dev"),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (P4 / "learned20_result.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ["best_w", "dev_learned", "dev_pctl_base",
                                          "paired_learned_minus_base", "verdict"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
