"""P5 validation gates — must be green before the serving swap ships.

  G-a  TRUNCATION: sparse top-K B (the serving artifact, scored through
       EASERecommender) vs EXACT Woodbury scoring (factors persisted by the
       builder) — paired NDCG@20 on 400 exploration-pool users.
       GATE: mean Δ(sparse − exact) >= -0.005 OR paired-ns. Also reports
       mean top-20 Jaccard.
  G-b  PREF SANITY (status.md flag): pctl_game×EASE vs pvalue_eb×EASE, exact
       scoring, same graph users — the serving combo was not a registered P6
       slot; H2 says they should be ~tied. Descriptive, but a large SIG loss
       for pctl would escalate to the user.
  G-c  WEIGHT APPROX: serving-time ECDF-interpolated pctl weights vs exact
       snapshot pctl weights — per-item Spearman + end-to-end paired NDCG
       (adapter ECDF weights vs adapter exact weights).

Exploration-pool only; the P6 confirm/reserve firewall stays enforced.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.agent.ease_recommender import EASERecommender  # noqa: E402
from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.data.build_ease_artifact import (  # noqa: E402
    exact_scores, fit_ease, load_snapshot)
from pipeline.game_rec.evaluation.stats import paired_bootstrap_diff  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.p6_common import (  # noqa: E402
    K, assert_firewall, build_relevance, graded_profile, load_panels,
    split_profile_holdout)
from pipeline.orchestration.preference_sweep import graded_ndcg  # noqa: E402

log = get_logger("orchestration.p5_validate")

ART = REPO_ROOT / "outputs" / "p5"
FAC = ART / "ease_factors"
EASE_DIR = REPO_ROOT / "serving" / "data" / "ease"
EVAL_N, EVAL_SEED = 400, 888


def rank_topk_from_scores(scores, items, profile, exclude, k=K):
    s = scores.copy()
    for a in profile:
        j = np.searchsorted(items, int(a))
        if j < len(items) and items[j] == int(a):
            s[j] = -np.inf
    out = []
    for j in np.argsort(-s):
        a = int(items[j])
        if a not in exclude:
            out.append(a)
        if len(out) >= k:
            break
    return out


def main() -> int:
    inter, gs, us, pool = load_snapshot(ART)
    rel = build_relevance(inter, pool)
    counts = rel.groupby("steamid").size()
    panels = load_panels()
    explo = [int(u) for u in panels["exploration"] if u in counts.index]
    rng = np.random.default_rng(EVAL_SEED)
    users = sorted(int(u) for u in rng.choice(explo, size=min(EVAL_N, len(explo)),
                                              replace=False))
    assert_firewall(users, panels)
    splits = split_profile_holdout(rel, users, seed=42)
    uu = sorted(splits)
    log.info("eval users: %d (exploration pool)", len(uu))

    scores_pctl = bs.compute("pctl_game", inter, gs, us)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            scores_pctl[scores_pctl["s"] > 0][["steamid", "appid", "s"]].values}

    # exact factors from the build
    X = sparse.load_npz(FAC / "X.npz")
    V = np.load(FAC / "V.npy", mmap_mode="r")
    diagP = np.load(FAC / "diagP.npy")
    items = np.load(FAC / "items.npy")
    col = {int(a): j for j, a in enumerate(items)}
    rec = EASERecommender(EASE_DIR)
    meta = rec.meta
    lam = float(meta["lam"])
    assert np.array_equal(items, rec.items), "factor/artifact item map mismatch"

    # ---------------- G-a: truncation loss ----------------
    nd_exact, nd_sparse, jac = {}, {}, []
    for u in uu:
        sp = splits[u]
        prof = graded_profile(u, sp["profile"], smap, rel_fallback=sp["profile"])
        x = np.zeros(len(items))
        for a, w in prof.items():
            j = col.get(int(a))
            if j is not None:
                x[j] = w
        excl = set(sp["profile"])
        ex_s = exact_scores(X, V, diagP, lam, x)
        sp_s = rec.score_with_weights(prof)
        r_ex = rank_topk_from_scores(ex_s, items, prof, excl)
        r_sp = rank_topk_from_scores(sp_s, items, prof, excl)
        nd_exact[u] = graded_ndcg(sp["holdout"], r_ex, K)
        nd_sparse[u] = graded_ndcg(sp["holdout"], r_sp, K)
        jac.append(len(set(r_ex) & set(r_sp)) / len(set(r_ex) | set(r_sp)))
    d = paired_bootstrap_diff([nd_exact[u] for u in uu], [nd_sparse[u] for u in uu])
    ga_pass = (d["mean_diff"] >= -0.005) or (not d["significant"])
    print(f"G-a truncation: exact={np.mean(list(nd_exact.values())):.4f} "
          f"sparse={np.mean(list(nd_sparse.values())):.4f} "
          f"d(sparse-exact)={d['mean_diff']:+.4f} [{d['lo']:+.4f},{d['hi']:+.4f}] "
          f"{'SIG' if d['significant'] else 'ns'} | top20 Jaccard={np.mean(jac):.3f} "
          f"| GATE {'PASS' if ga_pass else 'FAIL'}")

    # ---------------- G-c: ECDF weight approximation ----------------
    pt_map = {(int(r.steamid), int(r.appid)): float(r.playtime_forever)
              for r in inter[inter["steamid"].isin(set(uu))].itertuples()}
    w_ex, w_ec = [], []
    nd_ecdf = {}
    for u in uu:
        sp = splits[u]
        prof_ex = graded_profile(u, sp["profile"], smap, rel_fallback=sp["profile"])
        prof_ec = {int(a): rec.profile_weight(a, pt_map.get((u, int(a)), 0.0))
                   for a in sp["profile"]}
        prof_ec = {a: w for a, w in prof_ec.items() if w > 0} or prof_ex
        for a in prof_ex:
            if a in prof_ec:
                w_ex.append(prof_ex[a])
                w_ec.append(prof_ec[a])
        s = rec.score_with_weights(prof_ec)
        r = rank_topk_from_scores(s, items, prof_ec, set(sp["profile"]))
        nd_ecdf[u] = graded_ndcg(sp["holdout"], r, K)
    rho = spearmanr(w_ex, w_ec).statistic
    d_c = paired_bootstrap_diff([nd_sparse[u] for u in uu], [nd_ecdf[u] for u in uu])
    print(f"G-c weights: spearman(exact,ecdf)={rho:.4f} "
          f"mean|dw|={np.mean(np.abs(np.array(w_ex) - np.array(w_ec))):.4f} | "
          f"ndcg ecdf={np.mean(list(nd_ecdf.values())):.4f} "
          f"d(ecdf-exactw)={d_c['mean_diff']:+.4f} [{d_c['lo']:+.4f},{d_c['hi']:+.4f}] "
          f"{'SIG' if d_c['significant'] else 'ns'}")

    # ---------------- G-b: pctl vs pvalue under EASE ----------------
    del V  # release mmap before the second fit
    graph_users = json.loads((EASE_DIR / "graph_users.json").read_text())
    scores_pv = bs.compute("pvalue_lognorm_eb", inter, gs, us)
    smap_pv = {(int(u), int(a)): float(s) for u, a, s in
               scores_pv[scores_pv["s"] > 0][["steamid", "appid", "s"]].values}
    Xp, Vp, dPp, items_p, col_p = fit_ease(scores_pv, graph_users, pool, lam)
    nd_pv = {}
    for u in uu:
        sp = splits[u]
        prof = graded_profile(u, sp["profile"], smap_pv, rel_fallback=sp["profile"])
        x = np.zeros(len(items_p))
        for a, w in prof.items():
            j = col_p.get(int(a))
            if j is not None:
                x[j] = w
        s = exact_scores(Xp, Vp, dPp, lam, x)
        r = rank_topk_from_scores(s, items_p, prof, set(sp["profile"]))
        nd_pv[u] = graded_ndcg(sp["holdout"], r, K)
    d_b = paired_bootstrap_diff([nd_pv[u] for u in uu], [nd_exact[u] for u in uu])
    print(f"G-b pref sanity: pctl(exact)={np.mean(list(nd_exact.values())):.4f} "
          f"pvalue(exact)={np.mean(list(nd_pv.values())):.4f} "
          f"d(pctl-pvalue)={d_b['mean_diff']:+.4f} [{d_b['lo']:+.4f},{d_b['hi']:+.4f}] "
          f"{'SIG' if d_b['significant'] else 'ns'}")

    out = {"n_users": len(uu),
           "g_a": {"exact": round(float(np.mean(list(nd_exact.values()))), 4),
                   "sparse": round(float(np.mean(list(nd_sparse.values()))), 4),
                   "diff": round(d["mean_diff"], 4), "ci": [round(d["lo"], 4), round(d["hi"], 4)],
                   "sig": d["significant"], "jaccard": round(float(np.mean(jac)), 3),
                   "pass": bool(ga_pass)},
           "g_b": {"pctl": round(float(np.mean(list(nd_exact.values()))), 4),
                   "pvalue": round(float(np.mean(list(nd_pv.values()))), 4),
                   "diff_pctl_minus_pvalue": round(d_b["mean_diff"], 4),
                   "ci": [round(d_b["lo"], 4), round(d_b["hi"], 4)], "sig": d_b["significant"]},
           "g_c": {"weight_spearman": round(float(rho), 4),
                   "ndcg_ecdf": round(float(np.mean(list(nd_ecdf.values()))), 4),
                   "diff_vs_exact_weights": round(d_c["mean_diff"], 4), "sig": d_c["significant"]}}
    (REPO_ROOT / "experiments" / "p6_ood" / "p5_validate.json").write_text(
        json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if ga_pass else 1


if __name__ == "__main__":
    sys.exit(main())
