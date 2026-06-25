"""Empirically characterize Steam's rate limit (each method tested separately).

We hit a long 429 cooldown from a 10 req/s burst. This probe WAITS for the cooldown
to clear (polling), then runs, separately:
  - Exp BULK : GetPlayerSummaries with 100 steamids in one call (does bulk work?).
  - Exp RATE : sustained-rate sweep (1.5/2/3/5 req/s, 25 calls each) -> highest 429-free
               rate = the safe sustained ceiling. Escalates, stops at first throttle.
  - Exp BURST: from rested, fire fast and record the request index of the first 429
               = token-bucket capacity (run LAST; it re-triggers cooldown).

Calls are reserved against the shared SQLite daily budget (stays < 100k/day).
Results -> stdout + experiments/DELIBERATION_LOG.md. Re-runnable (resets nothing).
"""

from __future__ import annotations

import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from data_collection import db  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.rate_limit_probe")
OWNED = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
SUMM = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--max-wait", type=int, default=5400, help="max seconds to wait for cooldown")
    ap.add_argument("--poll", type=int, default=120)
    ap.add_argument("--limit", type=int, default=db.DAILY_LIMIT)
    ap.add_argument("--do-burst", action="store_true", help="also run the destructive burst probe last")
    args = ap.parse_args()
    key = os.environ["STEAM_API_KEY"]
    conn = db.connect()

    ids, seen = [], set()
    with open(args.scores, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            s = r["steamid"]
            if s not in seen:
                seen.add(s); ids.append(s)
            if len(ids) >= 300:
                break

    def call(url, params):
        if not db.reserve(conn, 1, args.limit):
            raise db.BudgetExhausted()
        try:
            return requests.get(url, params={**params, "key": key}, timeout=15).status_code
        except Exception:
            return -1

    def owned(sid):
        return call(OWNED, {"steamid": sid, "include_played_free_games": 1, "format": "json"})

    # ---- wait for cooldown ----
    waited = 0
    while owned(ids[0]) != 200:
        if waited >= args.max_wait:
            log.warning("cooldown not cleared after %ds — aborting", waited)
            print("ABORT: cooldown not cleared after %ds" % waited)
            return 0
        log.info("still throttled; waited=%ds, sleeping %ds", waited, args.poll)
        time.sleep(args.poll); waited += args.poll
    log.info("cooldown CLEARED after ~%ds", waited)
    lines = [f"# Rate-limit probe — {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
             f"- cooldown cleared after ~{waited}s of waiting (post 10/s burst)."]

    # ---- Exp BULK ----
    if db.reserve(conn, 1, args.limit):
        r = requests.get(SUMM, params={"key": key, "steamids": ",".join(ids[:100]), "format": "json"}, timeout=20)
        n = len((r.json().get("response", {}) or {}).get("players", [])) if r.status_code == 200 else 0
        lines.append(f"- **BULK** GetPlayerSummaries(100 ids): HTTP {r.status_code}, players={n} "
                     f"(1 call returns up to 100 -> ~{n}x for summaries).")

    # ---- Exp RATE (sustained sweep) ----
    lines.append("- **RATE sweep** (25 calls each, stop at first throttle):")
    i, safe_rate = 1, None
    for rate, iv in [("1.5/s", 0.667), ("2/s", 0.5), ("3/s", 0.333), ("5/s", 0.2)]:
        codes = []
        for _ in range(25):
            codes.append(owned(ids[i % len(ids)])); i += 1; time.sleep(iv)
        n429 = codes.count(429)
        lines.append(f"    - {rate}: 200={codes.count(200)} 429={n429} -> {'SAFE' if n429 == 0 else 'THROTTLED'}")
        if n429 == 0:
            safe_rate = rate
        else:
            break
        time.sleep(3)
    lines.append(f"- **safe sustained rate (measured): {safe_rate or '<1.5/s'}**")

    # ---- Exp BURST (optional, destructive) ----
    if args.do_burst:
        time.sleep(30)
        first429 = None
        for n in range(1, 101):
            if owned(ids[n % len(ids)]) == 429:
                first429 = n; break
        lines.append(f"- **BURST** token-bucket: first 429 at request #{first429 or '>100'} (= bucket capacity).")

    report = "\n".join(lines)
    print(report)
    dlog = REPO_ROOT / "experiments" / "DELIBERATION_LOG.md"
    if dlog.exists():
        with open(dlog, "a", encoding="utf-8") as f:
            f.write("\n\n## (인프라 실험) Steam rate-limit probe\n" + report + "\n")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
