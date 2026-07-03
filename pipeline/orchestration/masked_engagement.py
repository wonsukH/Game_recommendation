"""P4 supplementary axis — masked-engagement: rank held-out pairs by their
neutral relevance (per-game engagement pctl), scored by each config's ranker.

Per plan: target is the NEUTRAL rel (never the candidate's own s — the
predictability trap), pairs are the user's held-out OWNED items, metric is
per-user Spearman(ranker_score, rel) over holdout items (>=5 items).
Intensity-calibration lens: complements top-K ranking, does not replace it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.evaluation.stats import bootstrap_ci  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    P4, GradedCF, build_relevance, get_panels, load_artifacts,
    split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import UserKNN  # noqa: E402

log = get_logger("orchestration.masked_engagement")

CONFIGS = [
    ("S0_pvalue_knnpd03", {"name": "pvalue_lognorm_eb", "params": {}}, ("knn", 0.3)),
    ("S1_pvalue_userknn", {"name": "pvalue_lognorm_eb", "params": {}}, ("knn", 0.0)),
    ("S4_capblend_condcos", {"name": "per_user_cap",
                             "params": {"base": "blend", "lam": 0.4, "alpha": 0.3}},
     ("condcos", None)),
    ("null_random_support", {"name": "random_support", "params": {}}, ("knn", 0.0)),
]


def main() -> int:
    inter, game_stats, user_stats, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    users = panels["dev"]
    splits = split_profile_holdout(rel, users, seed=42)
    users = sorted(splits)

    rows = []
    for name, spec, (rkind, beta) in CONFIGS:
        scores = bs.compute(spec["name"], inter, game_stats, user_stats, **spec["params"])
        smap = {(int(u), int(a)): float(s) for u, a, s in
                scores[scores["s"] > 0][["steamid", "appid", "s"]].values}
        if rkind == "knn":
            model = UserKNN(scores, panels["train"], pool, topk_users=25,
                            pop_beta=beta or 0.0)
        else:
            model = GradedCF(scores, panels["train"], pool)
            need = sorted({a for u in users for a in
                           list(splits[u]["profile"]) + list(splits[u]["holdout"])})
            S, amap = model.sim_columns(need)
        rhos = []
        for u in users:
            sp = splits[u]
            hold = sp["holdout"]
            if len(hold) < 5:
                continue
            prof = {a: smap.get((u, a), 0.0) for a in sp["profile"]}
            prof = {a: w for a, w in prof.items() if w > 0} or dict(sp["profile"])
            if rkind == "knn":
                # replicate scoring vector
                p = np.zeros(len(model.items), dtype=np.float32)
                for a, w in prof.items():
                    j = model.col.get(a)
                    if j is not None:
                        p[j] = w
                pn = np.linalg.norm(p)
                if pn == 0:
                    continue
                sims = (np.asarray(model.X @ p).ravel()
                        / np.maximum(model.row_norm * pn, 1e-12))
                top = np.argsort(-sims)[: model.topk_users]
                from scipy import sparse as sp_
                agg = np.asarray((sp_.diags(np.maximum(sims[top], 0))
                                  @ model.X[top]).sum(axis=0)).ravel()
                if model.pop_disc is not None:
                    agg = agg * model.pop_disc
                sc = {a: (agg[model.col[a]] if a in model.col else 0.0) for a in hold}
            else:
                use = [(a, w) for a, w in prof.items() if a in amap]
                acc = np.zeros(S.shape[0])
                for a, w in use:
                    colv = S.getcol(amap[a])
                    acc[colv.indices] += w * colv.data
                sc = {a: (acc[model.col[a]] if a in model.col else 0.0) for a in hold}
            xs = [sc[a] for a in hold]
            ys = [hold[a] for a in hold]
            if len(set(xs)) > 1 and len(set(ys)) > 1:
                rho = spearmanr(xs, ys).statistic
                if np.isfinite(rho):
                    rhos.append(rho)
        ci = bootstrap_ci(np.array(rhos))
        rows.append({"config": name, "spearman_masked": round(ci["mean"], 4),
                     "ci": f"[{ci['lo']:.3f},{ci['hi']:.3f}]", "n_users": len(rhos)})
        log.info("%s: rho=%.4f (n=%d)", name, ci["mean"], len(rhos))
    lb = pd.DataFrame(rows)
    out = P4 / "masked_engagement"
    out.mkdir(exist_ok=True)
    lb.to_csv(out / "leaderboard.csv", index=False)
    print(lb.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
