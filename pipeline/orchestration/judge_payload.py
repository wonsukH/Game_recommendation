"""P4 judge guardrail payload — blinded S1 vs S4 recommendation pairs.

Builds grounded comparison cases for the Sonnet judge: per sampled dev user,
top-10 recs from S1 (pvalue x userknn25) and S4 (cap_blend x condcos), with
game cards (name/genres/short-desc) and the user's taste profile. A/B labels
randomized per case; the unblinding map is stored separately.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    P4, GradedCF, build_relevance, get_panels, load_artifacts)
from pipeline.orchestration.ranker_gauntlet import UserKNN  # noqa: E402

N_USERS, K = 12, 10


def card(meta, a):
    m = meta.get(a)
    if not m:
        return {"appid": a, "name": f"(미크롤 {a})"}
    raw = json.loads(m[1] or "[]") if m[1] else []
    genres = ", ".join(g.get("description", str(g)) if isinstance(g, dict) else str(g)
                       for g in raw[:4])
    desc = (m[2] or "")[:160]
    return {"appid": a, "name": m[0], "genres": genres, "desc": desc}


def main() -> int:
    import os
    variant = os.environ.get("JUDGE_VARIANT", "s1_vs_s4")
    n_users = int(os.environ.get("JUDGE_N", N_USERS))

    inter, game_stats, user_stats, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    rng = np.random.default_rng(99)
    if variant.endswith("_fresh"):
        frozen = (set(panels["train"]) | set(panels["dev"])
                  | set(panels["private"]))
        counts = rel.groupby("steamid").size()
        cand = [int(u) for u in counts[counts >= 12].index if int(u) not in frozen]
        users = sorted(rng.choice(cand, size=n_users, replace=False).tolist())
    else:
        users = sorted(rng.choice(panels["dev"], size=n_users, replace=False).tolist())

    con = sqlite3.connect(REPO_ROOT / "data_collection" / "steam.db")
    meta = {int(r[0]): (r[1], r[2], r[3]) for r in con.execute(
        "SELECT appid, name, genres_json, short_description FROM games WHERE name IS NOT NULL")}
    con.close()

    prof_all = {int(u): dict(zip(g["appid"].astype(int), g["rel"].astype(float)))
                for u, g in rel[rel["steamid"].isin(users)].groupby("steamid")}

    def recs_for(spec, ranker):
        scores = bs.compute(spec["name"], inter, game_stats, user_stats, **spec["params"])
        smap = {(int(u), int(a)): float(s) for u, a, s in
                scores[scores["s"] > 0][["steamid", "appid", "s"]].values}
        if ranker == "knnpd03":
            model = UserKNN(scores, panels["train"], pool, topk_users=25, pop_beta=0.3)
            S = amap = None
        elif ranker == "userknn":
            model = UserKNN(scores, panels["train"], pool, topk_users=25)
            S = amap = None
        else:
            model = GradedCF(scores, panels["train"], pool)
            need = sorted({a for u in users for a in prof_all.get(u, {})})
            S, amap = model.sim_columns(need)
        out = {}
        for u in users:
            prof = {a: smap.get((u, a), 0.0) for a in prof_all.get(u, {})}
            prof = {a: w for a, w in prof.items() if w > 0} or prof_all.get(u, {})
            excl = set(prof_all.get(u, {}))
            out[u] = (model.recommend(prof, S, amap, K, excl) if S is not None
                      else model.recommend(prof, K, excl))
        return out

    pv = {"name": "pvalue_lognorm_eb", "params": {}}
    cap = {"name": "per_user_cap", "params": {"base": "blend", "lam": 0.4, "alpha": 0.3}}
    if variant == "s0_vs_s1_fresh":
        lx, ly = "S0", "S1"
        sx, sy = recs_for(pv, "knnpd03"), recs_for(pv, "userknn")
    elif variant == "s1pd_vs_s4":
        lx, ly = "S1", "S4"
        sx, sy = recs_for(pv, "knnpd03"), recs_for(cap, "condcos")
    else:  # s1_vs_s4
        lx, ly = "S1", "S4"
        sx, sy = recs_for(pv, "userknn"), recs_for(cap, "condcos")

    cases, unblind = [], {}
    for i, u in enumerate(users):
        taste = sorted(prof_all[u].items(), key=lambda x: -x[1])[:8]
        flip = bool(rng.integers(0, 2))
        a_list, b_list = (sy[u], sx[u]) if flip else (sx[u], sy[u])
        unblind[f"case{i}"] = {"A": ly if flip else lx, "B": lx if flip else ly,
                               "steamid": u}
        cases.append({
            "case": f"case{i}",
            "user_taste": [card(meta, a) | {"engagement": round(r, 2)} for a, r in taste],
            "list_A": [card(meta, a) for a in a_list],
            "list_B": [card(meta, a) for a in b_list],
        })
    out = P4 / "judge"
    out.mkdir(exist_ok=True)
    (out / "payload.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    (out / "unblind.json").write_text(json.dumps(unblind, indent=1), encoding="utf-8")
    print(f"built {len(cases)} cases -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
