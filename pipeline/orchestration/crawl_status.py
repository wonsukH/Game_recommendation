"""Live progress + merge for the sharded GetOwnedGames crawl.

Reads every shard cache (`<dir>/shard*.json`) and its state file
(`<...>.json.state.json`), prints per-shard progress (pos/total %, public, rich)
and totals. With --merge, combines all shard caches (+ optional base) into one
deduped owned-libraries JSON for the experiments.

Usage:
  python -m pipeline.orchestration.crawl_status --dir <scratch>            # progress
  python -m pipeline.orchestration.crawl_status --dir <scratch> --merge experiments/05_personalization/owned_all.json
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", type=Path, required=True, help="dir containing shard*.json caches")
    ap.add_argument("--pattern", type=str, default="shard*.json")
    ap.add_argument("--min-rich", type=int, default=20)
    ap.add_argument("--base", type=Path, default=None, help="base cache to include in --merge")
    ap.add_argument("--merge", type=Path, default=None, help="write combined deduped cache here")
    args = ap.parse_args()

    files = sorted(f for f in glob.glob(str(args.dir / args.pattern)) if not f.endswith(".state.json") and not f.endswith(".tmp"))
    tot_pub = tot_rich = tot_pos = tot_total = tot_fetched = 0
    merged: dict = {}
    print(f"{'shard':<26} {'pos/total':>14} {'pct':>6} {'public':>7} {'rich':>6}")
    print("-" * 64)
    for f in files:
        cache = json.loads(Path(f).read_text(encoding="utf-8"))
        sp = Path(f).with_suffix(Path(f).suffix + ".state.json")
        st = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
        rich = sum(1 for v in cache.values() if len(v) >= args.min_rich)
        pos, total = int(st.get("pos", 0)), int(st.get("total", 0))
        pct = st.get("pct", round(100 * pos / total, 1) if total else 0)
        done = " ✓" if st.get("done") else ""
        print(f"{Path(f).name:<26} {f'{pos}/{total}':>14} {f'{pct}%':>6} {len(cache):>7} {rich:>6}{done}")
        tot_pub += len(cache); tot_rich += rich; tot_pos += pos; tot_total += total
        tot_fetched += int(st.get("fetched", 0))
        merged.update(cache)
    print("-" * 64)
    opct = round(100 * tot_pos / tot_total, 1) if tot_total else 0
    print(f"{'TOTAL':<26} {f'{tot_pos}/{tot_total}':>14} {f'{opct}%':>6} {tot_pub:>7} {tot_rich:>6}")
    print(f"(fetched API calls: {tot_fetched}; merged distinct public: {len(merged)})")

    if args.merge:
        if args.base and args.base.exists():
            base = json.loads(args.base.read_text(encoding="utf-8"))
            for k, v in base.items():
                merged.setdefault(k, v)
        args.merge.write_text(json.dumps(merged), encoding="utf-8")
        rich = sum(1 for v in merged.values() if len(v) >= args.min_rich)
        print(f"\nMERGED -> {args.merge}  (public={len(merged)}, rich={rich})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
