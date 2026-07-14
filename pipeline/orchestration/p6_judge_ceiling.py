"""Judge instrument CEILING calibration (post-hoc addendum to JUDGE_ABS_PREREG).

Question: is EASE's 44.5% High "low"? Uninterpretable without the instrument's
ceiling. This arm presents each user's OWN top-engagement games (ranks 9-18 by
relevance — disjoint from the 8 taste cards the judge sees) disguised as
recommendation candidates, same blind rubric. The High-rate on known-loved
items estimates the MAXIMUM this card-based judge can award — the denominator
for interpreting 44.5%. Descriptive calibration only; does not alter the
registered 3-arm results.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.evaluation.stats import bootstrap_ci  # noqa: E402
from pipeline.orchestration.p6_common import (  # noqa: E402
    assert_firewall, build_relevance, load_artifacts, load_panels)
from pipeline.orchestration.p6_judge_abs import load_tags, taste_summary  # noqa: E402

OUT = REPO_ROOT / "experiments" / "p6_ood" / "judge_abs"
N_USERS, SEED = 20, 20260715


def build(v2: bool = False) -> int:
    inter, gs, us, pool = load_artifacts()
    panels = load_panels()
    rel = build_relevance(inter, pool)
    counts = rel.groupby("steamid").size()
    explo = [int(u) for u in panels["exploration"] if u in counts.index]
    rng = np.random.default_rng(SEED)  # SAME draw as the 3-arm payload
    users = sorted(int(u) for u in rng.choice(explo, size=N_USERS, replace=False))
    assert_firewall(users, panels)

    con = sqlite3.connect(f"file:{REPO_ROOT / 'data_collection' / 'steam.db'}?mode=ro",
                          uri=True)
    meta = {int(r[0]): (r[1], r[2], r[3]) for r in con.execute(
        "SELECT appid, name, genres_json, short_description FROM games "
        "WHERE name IS NOT NULL")}
    con.close()

    tag_map = load_tags() if v2 else {}
    rng2 = np.random.default_rng(SEED + 7)

    def card(a: int) -> dict:
        m = meta.get(int(a))
        if not m:
            return {"appid": int(a), "name": f"(unknown {a})"}
        raw = json.loads(m[1] or "[]") if m[1] else []
        genres = ", ".join(g.get("description", str(g)) if isinstance(g, dict)
                           else str(g) for g in raw[:4])
        c = {"appid": int(a), "name": m[0], "genres": genres,
             "desc": (m[2] or "")[:160]}
        if v2:
            c["tags"] = ", ".join(t for t, _ in tag_map.get(int(a), [])[:5])
        return c

    prof_all = {int(u): sorted(zip(g["appid"].astype(int), g["rel"].astype(float)),
                               key=lambda x: -x[1])
                for u, g in rel[rel["steamid"].isin(users)].groupby("steamid")}
    cases = []
    for i, u in enumerate(users):
        items = prof_all[u]
        taste = items[:8]                     # what the judge sees as the profile
        ceiling = [a for a, _ in items[8:18]]  # the user's OWN next-loved games
        case = {
            "case": f"ceil{i}",
            "user_taste": [card(a) | {"engagement": round(r, 2)} for a, r in taste],
            "candidates": [card(a) | {"slot": t} for t, a in enumerate(ceiling)],
        }
        if v2:  # same v2 taste block as the main payload (ranks 19+ only)
            case["taste_summary_weighted_tags"] = taste_summary(items, tag_map)
            breadth = items[18:]
            if breadth:
                pick = rng2.choice(len(breadth), size=min(6, len(breadth)),
                                   replace=False)
                case["also_plays"] = [meta.get(int(breadth[j][0]), ("?",))[0]
                                      for j in sorted(pick)]
        cases.append(case)
    sfx = "_v2" if v2 else ""
    (OUT / f"payload_ceiling{sfx}.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"built {len(cases)} ceiling cases (v2={v2}) -> {OUT}")
    return 0


def aggregate(v2: bool = False) -> int:
    sfx = "_v2" if v2 else ""
    v = json.loads((OUT / f"verdicts_ceiling{sfx}.json").read_text(encoding="utf-8"))
    per_user_strict, per_user_len = [], []
    for _case, ratings in v.items():
        vals = [r for r in ratings.values() if r in ("High", "Medium", "Low")]
        if vals:
            per_user_strict.append(sum(r == "High" for r in vals) / len(vals))
            per_user_len.append(sum(r in ("High", "Medium") for r in vals) / len(vals))
    cs, cl = bootstrap_ci(np.array(per_user_strict)), bootstrap_ci(np.array(per_user_len))
    out = {"ceiling_strict": round(cs["mean"], 3),
           "strict_ci": f"[{cs['lo']:.3f},{cs['hi']:.3f}]",
           "ceiling_lenient": round(cl["mean"], 3),
           "lenient_ci": f"[{cl['lo']:.3f},{cl['hi']:.3f}]", "n_users": cs["n"]}
    (OUT / f"summary_ceiling{sfx}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aggregate", action="store_true")
    ap.add_argument("--v2", action="store_true")
    args = ap.parse_args()
    sys.exit(aggregate(args.v2) if args.aggregate else build(args.v2))
