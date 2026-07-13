"""P6 Phase 2 — freeze the OOD panels (the firewall artifact). FREEZE-ONCE.

From the immutable p6 snapshot (outputs/p6), splits the unbiased depth=-1
cohort into four disjoint strata and freezes them with hashes:

  confirm      N users (default 1,000) — the ONE-SHOT confirmation panel.
  reserve      500 users — quarantined; usable only under a future new prereg.
  exploration  remaining eligible users — dry-runs, verification, E1-E5.
  light        5-11 effective-item users — E3 descriptives (outside eligibility).

Eligibility = >=12 effective played items per build_relevance on the p6
snapshot (P6_PREREG.md amendment A3 — NOT raw owned counts). The draw is an
unconditional seeded shuffle over ALL eligible users (no wishlist conditioning
— that would bias the panel toward engaged users; metric B is computed on the
B-eligible subset inside the panel).

Also snapshots the OOD wishlist rows to outputs/p6/wishlist_ood.pkl (A5): the
confirmation must never read the live, still-growing DB.

Refuses to run if the panels file already exists (freeze-once, same pattern as
preference_sweep.get_panels).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.p6_common import (  # noqa: E402
    P4_DIR, P6_DIR, P6_OUT, PANELS_FILE, build_relevance, build_wl_targets,
    git_head, load_artifacts, sha_ids)

log = get_logger("orchestration.p6_panel_freeze")

DB = REPO_ROOT / "data_collection" / "steam.db"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirm-n", type=int, default=1000)
    ap.add_argument("--reserve-n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=20260714)
    ap.add_argument("--min-items", type=int, default=12)
    ap.add_argument("--light-lo", type=int, default=5)
    args = ap.parse_args()

    if PANELS_FILE.exists():
        print(f"REFUSE: {PANELS_FILE} already exists (freeze-once). Delete it "
              f"manually ONLY if you know the confirmation has not run.")
        return 1
    P6_DIR.mkdir(parents=True, exist_ok=True)

    inter, game_stats, user_stats, pool = load_artifacts(P6_OUT)
    rel = build_relevance(inter, pool)
    counts = rel.groupby("steamid").size()

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    ood = {int(r[0]) for r in con.execute(
        "SELECT steamid FROM user_queue WHERE depth=-1").fetchall()}
    wl = pd.read_sql_query(
        "SELECT w.steamid, w.appid, w.priority, w.date_added FROM wishlist w "
        "JOIN user_queue uq ON uq.steamid = w.steamid WHERE uq.depth = -1", con)
    con.close()

    eligible = sorted(int(u) for u in counts[counts >= args.min_items].index
                      if int(u) in ood)
    light = sorted(int(u) for u in counts[(counts >= args.light_lo)
                                          & (counts < args.min_items)].index
                   if int(u) in ood)
    need = args.confirm_n + args.reserve_n
    if len(eligible) < need + 300:
        print(f"REFUSE: only {len(eligible)} eligible OOD users; need "
              f"{need} + a meaningful exploration pool")
        return 1

    rng = np.random.default_rng(args.seed)
    order = np.array(eligible)
    rng.shuffle(order)
    confirm = sorted(int(u) for u in order[:args.confirm_n])
    reserve = sorted(int(u) for u in order[args.confirm_n:need])
    exploration = sorted(int(u) for u in order[need:])

    # ---- assertions -------------------------------------------------------
    assert not (set(confirm) & set(reserve)), "confirm/reserve overlap"
    assert not (set(confirm) & set(exploration)), "confirm/exploration overlap"
    assert not (set(reserve) & set(exploration)), "reserve/exploration overlap"
    p4_panels = json.loads((P4_DIR / "panels.json").read_text())
    frozen_old = (set(p4_panels["train"]) | set(p4_panels["dev"])
                  | set(p4_panels["private"]))
    assert not (set(confirm) & frozen_old), "confirm overlaps legacy P4 panels"
    assert not (set(reserve) & frozen_old), "reserve overlaps legacy P4 panels"

    # ---- wishlist snapshot (A5) ------------------------------------------
    wl.to_pickle(P6_OUT / "wishlist_ood.pkl")
    owned_pairs = set(zip(inter["steamid"].astype(int), inter["appid"].astype(int)))
    b_eligible = build_wl_targets(confirm, pool, owned_pairs, wl)

    extract_digest = (P6_OUT / "extract_stats.json").read_text(encoding="utf-8")
    panels = {
        "seed": args.seed,
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git_head": git_head(),
        "min_items": args.min_items,
        "light_range": [args.light_lo, args.min_items - 1],
        "extract_stats": json.loads(extract_digest),
        "counts": {"ood_usable_in_snapshot": len(ood & set(int(u) for u in counts.index)),
                   "eligible": len(eligible), "confirm": len(confirm),
                   "reserve": len(reserve), "exploration": len(exploration),
                   "light": len(light), "confirm_b_eligible": len(b_eligible),
                   "wl_snapshot_rows": int(len(wl))},
        "confirm": confirm,
        "reserve": reserve,
        "exploration": exploration,
        "light": light,
        "sha256_confirm": sha_ids(confirm),
        "sha256_reserve": sha_ids(reserve),
    }
    PANELS_FILE.write_text(json.dumps(panels), encoding="utf-8")
    log.info("frozen: %s", panels["counts"])
    print(json.dumps({k: panels[k] for k in
                      ("seed", "frozen_at", "counts", "sha256_confirm",
                       "sha256_reserve")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
