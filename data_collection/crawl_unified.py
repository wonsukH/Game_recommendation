"""Unified, resumable, budget-capped Steam crawler -> SQLite (data_collection/db.py).

Collects EVERY key-callable preference/quality signal (API audit via
GetSupportedAPIList). Every HTTP call goes through `api_get`, which reserves against
the shared daily budget BEFORE the call (reserve-before-call) -> the 100k/day cap can
never be exceeded (default limit 90k). Resumable via crawl_state cursors; run daily
(manually or scheduled) to accumulate slowly.

Phases:
  users  : per distinct steamid -> owned(full); if public -> recently, friends,
           wishlist, followed, groups, level+badges, summary(country), and
           achievements for owned games with playtime >= --ach-floor min.
  games  : per appid seen in owned (or pool) -> appdetails, steamspy, current players,
           global achievement rarity, schema, reviews(text+votes+weighted+playtime_at_review).

ToU: public profiles only (private -> API returns nothing); official API within cap;
data stored LOCALLY (gitignored). Stops cleanly when the day's budget is spent.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from data_collection import db  # noqa: E402
from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("data_collection.crawl_unified")
API = "https://api.steampowered.com"
STORE = "https://store.steampowered.com"


class Throttled(Exception):
    """Persistent HTTP 429 after backoff — caller must cool down and retry, and must
    NOT record the user as private (that would corrupt data with false negatives)."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Crawler:
    def __init__(self, conn, key, limit, sleep, ach_floor):
        self.conn, self.key, self.limit, self.sleep, self.ach_floor = conn, key, limit, sleep, ach_floor
        self.calls = 0
        self.throttle_hits = 0

    def get(self, url, params, store=False):
        """Reserve-before-call (1 reservation per get, retries don't re-reserve).
        Returns parsed json on HTTP 200, None on other non-429 errors. On 429 backs
        off exponentially; if still 429 after backoff raises Throttled (caller must
        cool down and retry — NEVER treat as 'private'). Raises BudgetExhausted."""
        if not db.reserve(self.conn, 1, self.limit):
            raise db.BudgetExhausted()
        self.calls += 1
        p = dict(params)
        if not store:
            p["key"] = self.key
        for attempt in range(5):
            try:
                r = requests.get(url, params=p, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 429:
                    self.throttle_hits += 1
                    time.sleep(min(120, 8 * (2 ** attempt)))  # 8,16,32,64,120
                    continue
                if r.status_code != 200:
                    return None
                return r.json()
            except Exception:
                time.sleep(2)
        raise Throttled()  # persistent 429

    # ---------- per-user ----------
    def crawl_user(self, sid, pool):
        j = self.get(f"{API}/IPlayerService/GetOwnedGames/v1/",
                     {"steamid": sid, "include_appinfo": 0, "include_played_free_games": 1, "format": "json"})
        time.sleep(self.sleep)
        games = (j or {}).get("response", {}).get("games") if j else None
        if games is None:
            db.upsert_many(self.conn, "users", ["steamid", "public", "fetched_at"], [(sid, 0, _now())])
            return  # private/unavailable (still counted the 1 call)
        owned = [(sid, int(g["appid"]), float(g.get("playtime_forever", 0)), float(g.get("playtime_2weeks", 0)))
                 for g in games]
        db.upsert_many(self.conn, "owned",
                       ["steamid", "appid", "playtime_forever", "playtime_2weeks"], owned)
        db.upsert_many(self.conn, "users", ["steamid", "public", "fetched_at"], [(sid, 1, _now())])

        # recently
        j = self.get(f"{API}/IPlayerService/GetRecentlyPlayedGames/v1/", {"steamid": sid, "format": "json"})
        time.sleep(self.sleep)
        rec = (j or {}).get("response", {}).get("games") or []
        db.upsert_many(self.conn, "recently", ["steamid", "appid", "playtime_2weeks"],
                       [(sid, int(g["appid"]), float(g.get("playtime_2weeks", 0))) for g in rec])
        # friends
        j = self.get(f"{API}/ISteamUser/GetFriendList/v1/", {"steamid": sid, "relationship": "friend", "format": "json"})
        time.sleep(self.sleep)
        fr = (j or {}).get("friendslist", {}).get("friends") or []
        db.upsert_many(self.conn, "friends", ["steamid", "friend_steamid"],
                       [(sid, f["steamid"]) for f in fr])
        # wishlist
        j = self.get(f"{API}/IWishlistService/GetWishlist/v1/", {"steamid": sid})
        time.sleep(self.sleep)
        wl = (j or {}).get("response", {}).get("items") or []
        db.upsert_many(self.conn, "wishlist", ["steamid", "appid", "priority"],
                       [(sid, int(w.get("appid")), int(w.get("priority", 0))) for w in wl if w.get("appid")])
        # followed
        j = self.get(f"{API}/IStoreService/GetGamesFollowed/v1/", {"steamid": sid})
        time.sleep(self.sleep)
        fo = (j or {}).get("response", {}).get("games") or []
        db.upsert_many(self.conn, "followed", ["steamid", "appid"],
                       [(sid, int(g.get("appid"))) for g in fo if g.get("appid")])
        # groups
        j = self.get(f"{API}/ISteamUser/GetUserGroupList/v1/", {"steamid": sid, "format": "json"})
        time.sleep(self.sleep)
        gr = (j or {}).get("response", {}).get("groups") or []
        db.upsert_many(self.conn, "user_groups", ["steamid", "gid"], [(sid, g["gid"]) for g in gr])
        # level + summary(country)
        j = self.get(f"{API}/IPlayerService/GetSteamLevel/v1/", {"steamid": sid, "format": "json"})
        time.sleep(self.sleep)
        level = (j or {}).get("response", {}).get("player_level")
        j = self.get(f"{API}/ISteamUser/GetPlayerSummaries/v2/", {"steamids": sid, "format": "json"})
        time.sleep(self.sleep)
        pl = ((j or {}).get("response", {}).get("players") or [{}])[0]
        db.upsert_many(self.conn, "users", ["steamid", "country", "level", "public", "fetched_at"],
                       [(sid, pl.get("loccountrycode"), level, 1, _now())])
        # achievements for meaningfully-played games (playtime >= floor)
        played = [(a, pt) for (_, a, pt, _) in owned if pt >= self.ach_floor and int(a) in pool]
        for appid, _pt in played:
            j = self.get(f"{API}/ISteamUserStats/GetPlayerAchievements/v1/",
                         {"steamid": sid, "appid": appid})
            time.sleep(self.sleep)
            ach = (j or {}).get("playerstats", {}).get("achievements") if j else None
            if ach:
                done = sum(1 for a in ach if a.get("achieved") == 1)
                db.upsert_many(self.conn, "achievements", ["steamid", "appid", "unlocked", "total"],
                               [(sid, int(appid), done, len(ach))])

    def run_users(self, steamids, pool, cooldown=60, max_throttle_retries=8):
        key = "phase:users"
        pos, _ = db.get_cursor(self.conn, key)
        log.info("users phase resume pos=%d / %d (today spent=%d)", pos, len(steamids), db.spent_today(self.conn))
        i = pos
        throttle_streak = 0
        try:
            while i < len(steamids):
                try:
                    self.crawl_user(steamids[i], pool)
                except Throttled:
                    throttle_streak += 1
                    db.set_cursor(self.conn, key, i)  # checkpoint; retry SAME user (no false-private)
                    if throttle_streak > max_throttle_retries:
                        log.warning("persistent throttle at pos=%d (streak=%d) — stopping for now", i, throttle_streak)
                        return False
                    log.warning("throttled at pos=%d — cooling down %ds (streak=%d)", i, cooldown, throttle_streak)
                    time.sleep(cooldown)
                    continue
                throttle_streak = 0
                i += 1
                if i % 20 == 0:
                    db.set_cursor(self.conn, key, i)
                    log.info("users pos=%d/%d spent_today=%d throttle_hits=%d",
                             i, len(steamids), db.spent_today(self.conn), self.throttle_hits)
        except db.BudgetExhausted:
            db.set_cursor(self.conn, key, i)
            log.info("BUDGET EXHAUSTED at users pos=%d (today=%d). resume tomorrow.", i, db.spent_today(self.conn))
            return False
        db.set_cursor(self.conn, key, len(steamids), done=True)
        return True


def distinct_steamids(scores: Path, limit: int) -> list[str]:
    order, seen = [], set()
    with open(scores, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            s = row["steamid"]
            if s not in seen:
                seen.add(s); order.append(s)
            if len(order) >= limit:
                break
    return order


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=db.DEFAULT_DB)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--phase", choices=["users", "games"], default="users")
    ap.add_argument("--limit", type=int, default=db.DAILY_LIMIT, help="daily call cap (<100k)")
    ap.add_argument("--seed-today", type=int, default=0, help="calls already spent today outside this DB")
    ap.add_argument("--max-steamids", type=int, default=200000)
    ap.add_argument("--ach-floor", type=float, default=30.0, help="min playtime(min) to crawl a game's achievements")
    ap.add_argument("--sleep", type=float, default=1.0, help="pause between calls; >=1.0 avoids Steam 429")
    args = ap.parse_args()

    key = os.environ.get("STEAM_API_KEY")
    if not key:
        log.error("STEAM_API_KEY not set"); return 1
    conn = db.connect(args.db)
    if args.seed_today > 0:
        db.seed_today(conn, args.seed_today)
    pool = set(int(a) for a in load_index_maps(args.data_dir / "index_maps.json")["appid2row"].keys())

    cr = Crawler(conn, key, args.limit, args.sleep, args.ach_floor)
    if args.phase == "users":
        steamids = distinct_steamids(args.scores, args.max_steamids)
        done = cr.run_users(steamids, pool)
        log.info("users phase %s. calls this run=%d. counts=%s",
                 "DONE" if done else "paused(budget)", cr.calls, db.counts(conn))
    print(json.dumps({"calls_this_run": cr.calls, "spent_today": db.spent_today(conn), "counts": db.counts(conn)}))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
