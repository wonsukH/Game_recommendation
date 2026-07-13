"""P6 runner — dry-run (exploration pool), V1 replication, and the ONE-SHOT
confirmation. Implements P6_PREREG.md (v3): fixed slots, two graph conditions,
co-primary A (graded NDCG@20) + co-primary B (held-out wishlist recall@20).

Panels:
  --panel dryrun    seeded draw from the EXPLORATION stratum (firewall-asserted);
                    repeatable — used for V2/V5/V6 and the user sign-off table.
  --panel fresh854  V1 harness-correctness anchor: reruns the T38 fresh
                    zero-exposure cohort on the OLD outputs/p4 artifacts through
                    THIS code path. Must reproduce ease_l100 0.3359 / userknn
                    0.2736 / knnpd03 0.2663 / condcos 0.2304, ease-userknn
                    +0.0623. Adds the V1cc slot (pvalue x condcos, T38 config).
  --panel confirm   THE one-shot confirmation. Requires --acknowledge-one-shot;
                    refuses if this graph condition's output dir already exists.

Graphs (A4): frozen = legacy train-1,133 membership (scores recomputed on the
p6 snapshot); mixed = train + ALL exploration users (panel stays fully held
out in both conditions — paired comparison on identical users).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.evaluation.stats import (  # noqa: E402
    bootstrap_ci, paired_bootstrap_diff)
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.p6_common import (  # noqa: E402
    K, P4_DIR, P4_OUT, P6_DIR, P6_OUT, SLOTS, assert_firewall, build_relevance,
    build_wl_targets, fit_slot, git_head, graded_profile, load_artifacts,
    load_panels, load_wishlist_snapshot, pop_ranker, split_profile_holdout,
    verify_panel_hashes)
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    graded_ndcg, recall_at, snips_recall)

log = get_logger("orchestration.p6_confirm")

# T38 replication extra (NOT a registered confirmation slot): pvalue x condcos
EXTRA_V1_SLOTS = {"V1cc": ("pvalue_lognorm_eb", {}, "condcos", {})}


def resolve_users_and_graph(args, rel, panels_p4):
    counts = rel.groupby("steamid").size()
    if args.panel == "fresh854":
        frozen = (set(panels_p4["train"]) | set(panels_p4["dev"])
                  | set(panels_p4["private"]))
        users = sorted(int(u) for u in counts[counts >= 12].index
                       if int(u) not in frozen)
        graph = sorted(panels_p4["train"])
        return users, graph, None
    p6 = load_panels()
    verify_panel_hashes(p6)
    if args.panel == "dryrun":
        pool_users = [u for u in p6["exploration"] if u in counts.index]
        rng = np.random.default_rng(args.draw_seed)
        users = sorted(int(u) for u in
                       rng.choice(pool_users, size=min(args.n, len(pool_users)),
                                  replace=False))
        assert_firewall(users, p6)
    else:  # confirm
        users = [int(u) for u in p6["confirm"] if u in counts.index]
    if args.graph == "frozen":
        graph = sorted(panels_p4["train"])
    else:  # mixed (A4): train + ALL exploration users, panel fully held out
        graph = sorted(set(panels_p4["train"]) | set(p6["exploration"]))
    assert not (set(graph) & set(users)), "graph/panel overlap — holdout broken"
    return users, graph, p6


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", choices=["dryrun", "fresh854", "confirm"], required=True)
    ap.add_argument("--graph", choices=["frozen", "mixed"], default="frozen")
    ap.add_argument("--n", type=int, default=300, help="dryrun draw size")
    ap.add_argument("--draw-seed", type=int, default=777)
    ap.add_argument("--seed", type=int, default=42, help="profile/holdout split seed")
    ap.add_argument("--tag", default="", help="suffix for the run dir (dryrun only)")
    ap.add_argument("--acknowledge-one-shot", action="store_true")
    args = ap.parse_args()

    if args.panel == "confirm" and not args.acknowledge_one_shot:
        print("REFUSE: --panel confirm requires --acknowledge-one-shot")
        return 1

    run_name = f"{args.panel}_{args.graph}" + (f"_{args.tag}" if args.tag else "")
    out_dir = P6_DIR / run_name
    if args.panel == "confirm" and out_dir.exists():
        print(f"REFUSE: {out_dir} exists — the confirmation panel is ONE-SHOT "
              f"per registered graph condition.")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    art_dir = P4_OUT if args.panel == "fresh854" else P6_OUT
    inter, game_stats, user_stats, pool = load_artifacts(art_dir)
    rel = build_relevance(inter, pool)
    panels_p4 = json.loads((P4_DIR / "panels.json").read_text())
    users, graph, p6 = resolve_users_and_graph(args, rel, panels_p4)
    log.info("panel=%s users=%d graph=%s(%d) artifacts=%s",
             args.panel, len(users), args.graph, len(graph), art_dir.name)

    splits = split_profile_holdout(rel, users, seed=args.seed)
    users = sorted(splits)
    prop = (inter.groupby("appid").size() / inter["steamid"].nunique()).to_dict()

    # ---- metric-B targets (A5; snapshot only; skipped for fresh854/V1) ------
    wl_targets, prof_all = {}, {}
    if args.panel != "fresh854":
        wl = load_wishlist_snapshot()
        owned_pairs = set(zip(inter["steamid"].astype(int), inter["appid"].astype(int)))
        wl_targets = build_wl_targets(users, pool, owned_pairs, wl)
        prof_all = {int(u): dict(zip(g["appid"].astype(int), g["rel"].astype(float)))
                    for u, g in rel[rel["steamid"].isin(wl_targets)].groupby("steamid")}
        log.info("metric-B eligible: %d/%d users", len(wl_targets), len(users))

    # condcos needs the union of every profile it will ever score
    need = sorted({a for u in users for a in splits[u]["profile"]}
                  | {a for u in wl_targets for a in prof_all.get(u, {})})

    slot_specs = dict(SLOTS)
    if args.panel == "fresh854":
        slot_specs.update(EXTRA_V1_SLOTS)

    rows, t0 = [], time.time()
    for key in slot_specs:
        ts = time.time()
        # fresh854/V1 uses the T38 slot set only (registered EASE/KNN + V1cc)
        if args.panel == "fresh854" and key in ("S0a", "S2", "S3", "S4", "S5a",
                                                "S5c", "null"):
            continue
        pref, pparams, rkind, rparams = slot_specs[key]
        rec_fn, smap = fit_slot(key, inter, game_stats, user_stats, pool, graph,
                                need_appids=need, spec=slot_specs[key])
        per = []
        for u in users:
            sp = splits[u]
            prof = graded_profile(u, sp["profile"], smap, rel_fallback=sp["profile"])
            rec = rec_fn(prof, K, set(sp["profile"]))
            row = {"steamid": u,
                   "ndcg": graded_ndcg(sp["holdout"], rec, K),
                   "recall": recall_at(sp["holdout"], rec, K),
                   "snips": snips_recall(sp["holdout"], rec, K, prop),
                   "wl_recall": np.nan}
            if u in wl_targets:
                pa = prof_all[u]
                wprof = graded_profile(u, pa, smap, rel_fallback=pa)
                wrec = rec_fn(wprof, K, set(pa))
                row["wl_recall"] = (len(wl_targets[u] & set(wrec[:K]))
                                    / len(wl_targets[u]))
            per.append(row)
        pu = pd.DataFrame(per)
        pu.to_csv(out_dir / f"per_user_{key}.csv", index=False)
        r = {"slot": key, "spec": f"{pref}|{rkind}{rparams}", "n": len(pu)}
        for m in ("ndcg", "recall", "snips", "wl_recall"):
            ci = bootstrap_ci(pu[m].dropna().values)
            r[m] = round(ci["mean"], 4)
            r[f"{m}_ci"] = f"[{ci['lo']:.4f},{ci['hi']:.4f}]"
        r["n_wl"] = int(pu["wl_recall"].notna().sum())
        r["sec"] = round(time.time() - ts, 1)
        rows.append(r)
        log.info("%s: ndcg=%.4f wl=%.4f (%.0fs)", key, r["ndcg"],
                 r["wl_recall"] if r["n_wl"] else float("nan"), r["sec"])

    # ---- anchors (metric health, non-slots) --------------------------------
    pop_fn = pop_ranker(inter, pool, graph)
    per = []
    for u in users:
        sp = splits[u]
        rec = pop_fn(dict(sp["profile"]), K, set(sp["profile"]))
        orc = [a for a, _ in sorted(sp["holdout"].items(), key=lambda x: -x[1])][:K]
        row = {"steamid": u, "pop_ndcg": graded_ndcg(sp["holdout"], rec, K),
               "oracle_ndcg": graded_ndcg(sp["holdout"], orc, K),
               "pop_wl": np.nan}
        if u in wl_targets:
            pa = prof_all[u]
            wrec = pop_fn(dict(pa), K, set(pa))
            row["pop_wl"] = len(wl_targets[u] & set(wrec[:K])) / len(wl_targets[u])
        per.append(row)
    anchors = pd.DataFrame(per)
    anchors.to_csv(out_dir / "per_user_anchors.csv", index=False)

    lb = pd.DataFrame(rows).sort_values("ndcg", ascending=False)
    lb.to_csv(out_dir / "leaderboard.csv", index=False)
    config = {
        "run": run_name, "panel": args.panel, "graph": args.graph,
        "n_users": len(users), "n_graph": len(graph),
        "n_wl_eligible": len(wl_targets),
        "seed_split": args.seed, "draw_seed": args.draw_seed,
        "artifacts": str(art_dir), "git_head": git_head(),
        "panel_sha": (p6 or {}).get("sha256_confirm") if args.panel == "confirm"
                     else None,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0)),
        "elapsed_s": round(time.time() - t0),
        "anchors": {"oracle_ndcg": round(float(anchors["oracle_ndcg"].mean()), 4),
                    "pop_ndcg": round(float(anchors["pop_ndcg"].mean()), 4),
                    "pop_wl": round(float(anchors["pop_wl"].mean()), 4)
                    if anchors["pop_wl"].notna().any() else None},
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2))

    print(f"\n== {run_name}: n={len(users)} graph={len(graph)} "
          f"wl_eligible={len(wl_targets)} ==")
    print(lb.drop(columns=["spec"]).to_string(index=False))
    print(f"anchors: ORACLE ndcg={config['anchors']['oracle_ndcg']} "
          f"POP ndcg={config['anchors']['pop_ndcg']} "
          f"POP wl={config['anchors']['pop_wl']}")

    if args.panel == "fresh854":
        a = pd.read_csv(out_dir / "per_user_S5b.csv").set_index("steamid")["ndcg"]
        b = pd.read_csv(out_dir / "per_user_S1.csv").set_index("steamid")["ndcg"]
        d = paired_bootstrap_diff(b.values, a.values)
        print(f"\nV1 paired: ease_l100 - userknn25 NDCG = {d['mean_diff']:+.4f} "
              f"[{d['lo']:+.4f},{d['hi']:+.4f}] "
              f"{'SIG' if d['significant'] else 'ns'} (T38: +0.0623 [+0.0566,+0.0679])")
    return 0


if __name__ == "__main__":
    sys.exit(main())
