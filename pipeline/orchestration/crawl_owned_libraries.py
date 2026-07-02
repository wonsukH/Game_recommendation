"""Crawl real GetOwnedGames libraries for crawled steamids (for the LIVE D4 test
and the playtime-based co-occurrence rebuild).

The review crawl gave ~3 liked games/user (a cap artifact). GetOwnedGames returns
a public profile's FULL owned library + playtime — the real personalization input.
This collects rich public profiles and caches them.

ROBUST for long/mass crawls (resumable + progress):
  - Sharded by --start/--count (a window of the distinct-steamid list).
  - CURSOR resume: a `<out>.state.json` records how far the window was processed;
    re-running the SAME command resumes from there (no re-probing public OR
    non-public profiles already tried).
  - ATOMIC writes (tmp + os.replace) so a kill mid-write never corrupts the cache.
  - Flushes cache + state every --flush-every probes and on exit (try/finally).
  - Progress (pos/total, public, rich) is in the state file — read live with
    `python -m pipeline.orchestration.crawl_status`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.crawl_owned")
URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"


def _atomic_write(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj), encoding="utf-8")
    os.replace(tmp, path)


def _distinct_steamids(scores: Path, upto: int) -> list[str]:
    order, seen = [], set()
    with open(scores, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            s = row["steamid"]
            if s not in seen:
                seen.add(s); order.append(s)
            if len(order) >= upto:
                break
    return order


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--out", type=Path, required=True, help="shard cache file {steamid: {appid: playtime}}")
    ap.add_argument("--start", type=int, default=0, help="index offset into the distinct-steamid list (sharding)")
    ap.add_argument("--count", type=int, default=5000, help="how many distinct steamids in this shard's window")
    ap.add_argument("--base-cache", type=Path, default=None, help="skip steamids already present here")
    ap.add_argument("--min-rich", type=int, default=20)
    ap.add_argument("--sleep", type=float, default=0.18)
    ap.add_argument("--flush-every", type=int, default=25)
    args = ap.parse_args()

    key = os.environ.get("STEAM_API_KEY")
    if not key:
        log.error("STEAM_API_KEY not set"); return 1
    pool = set(int(a) for a in load_index_maps(args.data_dir / "index_maps.json")["appid2row"].keys())

    state_path = args.out.with_suffix(args.out.suffix + ".state.json")
    cache = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    skip = set(cache.keys())
    if args.base_cache and args.base_cache.exists():
        skip |= set(json.loads(args.base_cache.read_text(encoding="utf-8")).keys())

    def _inpool(lib):  # count of in-pool games (the recommendable subset)
        return sum(1 for a in lib if int(a) in pool)

    order = _distinct_steamids(args.scores, args.start + args.count)[args.start:args.start + args.count]
    total = len(order)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    pos = int(state.get("pos", 0))               # resume cursor (window index)
    fetched = int(state.get("fetched", 0))
    rich = sum(1 for v in cache.values() if _inpool(v) >= args.min_rich)  # in-pool rich, recomputed on resume
    log.info("[shard %d] window=%d resume_pos=%d cached=%d rich=%d", args.start, total, pos, len(cache), rich)

    def fetch(sid):
        for attempt in range(3):
            try:
                r = requests.get(URL, params={"key": key, "steamid": sid, "include_appinfo": 0,
                                              "include_played_free_games": 1, "format": "json"}, timeout=15)
                if r.status_code == 429:
                    time.sleep(3.0 + attempt * 4.0); continue
                return (r.json().get("response", {}) or {}).get("games"), True
            except Exception:
                time.sleep(1.0)
        return None, False  # gave up (treat as attempted, not public)

    def flush(p):
        _atomic_write(args.out, cache)
        _atomic_write(state_path, {"start": args.start, "total": total, "pos": p,
                                   "fetched": fetched, "public": len(cache), "rich": rich,
                                   "pct": round(100 * p / max(total, 1), 1),
                                   "done": p >= total})

    p = pos
    try:
        for p in range(pos, total):
            sid = order[p]
            if sid not in skip:
                games, ok = fetch(sid)
                fetched += 1
                if games is not None:  # public profile -> store the FULL library (nothing discarded:
                    # all owned games incl. never-played; downstream filters to pool/playtime as needed)
                    lib = {str(int(g["appid"])): float(g.get("playtime_forever", 0)) for g in games}
                    cache[sid] = lib
                    if _inpool(lib) >= args.min_rich:
                        rich += 1
                time.sleep(args.sleep)
            if (p + 1) % args.flush_every == 0:
                flush(p + 1)
                log.info("[shard %d] pos=%d/%d (%.1f%%) public=%d rich=%d", args.start, p + 1, total,
                         100 * (p + 1) / max(total, 1), len(cache), rich)
    finally:
        flush(min(p + 1, total))
        log.info("[shard %d] FLUSHED pos=%d/%d public=%d rich(in-pool)=%d -> %s",
                 args.start, min(p + 1, total), total, len(cache), rich, args.out)

    print(f"shard start={args.start} done: public={len(cache)} rich={rich} pos={min(p+1,total)}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
