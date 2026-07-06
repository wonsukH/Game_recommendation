"""Unified, resumable, budget-capped Steam crawler -> SQLite (data_collection/db.py).

TWO PHASES, interleaved round-robin so per-game metadata accumulates alongside the
per-user facts (each datum fetched at the cheapest point — see plan 최종 SQLite 스키마):

  Phase 1 users (facts)  — per public user. GetOwnedGames(include_appinfo=1: game names
      come FREE + has_community_visible_stats GATES achievement calls), Recently, Friends
      (+snowball enqueue), Wishlist, Followed, Groups, GetBadges(level+xp+badges), and
      GetPlayerAchievements for played(>=floor)+stats games — storing only WHICH apinames
      were unlocked (+unlocktime), interned to a compact ach_id. A user is `complete` only
      at the very end (atomic; resume re-runs idempotently). A transient (non-200) owned
      response leaves the user pending (NOT marked private) so it retries.
  Phase 2 games (dimension) — per distinct owned appid, ONCE. appdetails, SteamSpy,
      GetSchemaForGame (achievement display_name/description/hidden + game stats),
      GetGlobalAchievementPercentages (rarity %), GetNumberOfCurrentPlayers (live CCU).
      This is where achievement id->name/condition mapping happens. games.fetched_at =
      "visited" marker (sub-steps individually guarded for partial-visit resume).

(Reviews are intentionally NOT crawled: Steam has no per-user review-history API — only
the per-game appreviews endpoint — so it can't meet the per-user intent, and voted_up is
largely redundant with playtime. Owned/playtime/achievements/wishlist are the signal.)

Rate control: WALL-CLOCK pacing — sleep only `max(0, target - elapsed_since_last_start)`,
so the cadence equals `target` regardless of response latency (the old code slept AFTER
each call, so the real gap was RTT+sleep ≈ 1.3s, not 1.0s). AIMD adapts `target` (429 ->
×1.7 slower; success streak -> ×0.9 faster, floored). Circuit breaker on persistent 429.

Budget: EVERY HTTP request reserves 1 against the shared daily counter BEFORE firing
(reserve-before-call, retries counted too) -> the 100k/day cap can NEVER be exceeded
(default 90k). ToU: public profiles only, official/store APIs within cap, data stored
LOCALLY (gitignored).
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

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from data_collection import db  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("data_collection.crawl_unified")
API = "https://api.steampowered.com"
STORE = "https://store.steampowered.com"
STEAMSPY = "https://steamspy.com/api.php"


class Throttled(Exception):
    """Persistent HTTP 429 after backoff — caller cools down and retries later; the user
    must NOT be recorded private (that would corrupt data with false negatives)."""


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _i(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _csv(v) -> str | None:
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) if v else None
    return v if v else None


# ---------------- response parsers (pure functions) ----------------
def parse_appdetails(appid: int, data: dict | None) -> dict:
    """appdetails 'data' -> games columns (no fetched_at). data=None -> {appid} only
    (so the early-inserted name is preserved and fetched_at still gets stamped)."""
    g = {"appid": int(appid)}
    if not data:
        return g
    price = data.get("price_overview") or {}
    plat = data.get("platforms") or {}
    metac = data.get("metacritic") or {}
    rel = data.get("release_date") or {}
    rec = data.get("recommendations") or {}
    ach = data.get("achievements") or {}
    support = data.get("support_info") or {}
    g.update({
        "name": data.get("name"),
        "type": data.get("type"),
        "required_age": _i(data.get("required_age")),
        "is_free": int(bool(data.get("is_free"))),
        "controller_support": data.get("controller_support"),
        "dlc_json": json.dumps(data.get("dlc")) if data.get("dlc") else None,
        "short_description": data.get("short_description") or None,
        "detailed_description": data.get("detailed_description") or None,
        "about_the_game": data.get("about_the_game") or None,
        "supported_languages": data.get("supported_languages") or None,
        "developers": _csv(data.get("developers")),
        "publishers": _csv(data.get("publishers")),
        "win": int(bool(plat.get("windows"))),
        "mac": int(bool(plat.get("mac"))),
        "linux": int(bool(plat.get("linux"))),
        "price_final": _i(price.get("final")),
        "price_initial": _i(price.get("initial")),
        "price_discount": _i(price.get("discount_percent")),
        "price_currency": price.get("currency"),
        "metacritic_score": _i(metac.get("score")),
        "metacritic_url": metac.get("url"),
        "categories_json": json.dumps(data.get("categories")) if data.get("categories") else None,
        "genres_json": json.dumps(data.get("genres")) if data.get("genres") else None,
        "recommendations_total": _i(rec.get("total")),
        "achievements_total": _i(ach.get("total")),
        "release_date": rel.get("date"),
        "coming_soon": int(bool(rel.get("coming_soon"))),
        "header_image": data.get("header_image"),
        "content_descriptors_json": json.dumps(data.get("content_descriptors"))
        if data.get("content_descriptors") else None,
        "website": data.get("website"),
        "support_url": support.get("url") or None,
    })
    return g


def parse_steamspy(appid: int, d: dict) -> tuple:
    return (int(appid), d.get("name"), d.get("developer"), d.get("publisher"),
            str(d.get("score_rank")) if d.get("score_rank") not in (None, "") else None,
            _i(d.get("positive")), _i(d.get("negative")), _i(d.get("userscore")),
            d.get("owners"), _i(d.get("average_forever")), _i(d.get("average_2weeks")),
            _i(d.get("median_forever")), _i(d.get("median_2weeks")), _i(d.get("price")),
            _i(d.get("initialprice")), _i(d.get("discount")), _i(d.get("ccu")),
            d.get("languages"), d.get("genre"),
            json.dumps(d.get("tags")) if d.get("tags") else None, db.now_iso())


# ---------------- crawler ----------------
class Crawler:
    def __init__(self, conn, key, limit, target, ach_floor,
                 min_target=0.7, max_target=8.0, max_throttle=5,
                 crawl_ach=True, snowball=True, user_source="queue",
                 random_max=1_600_000_000, random_seed=42):
        self.conn, self.key, self.limit, self.ach_floor = conn, key, limit, ach_floor
        self.target = target            # current wall-clock interval (AIMD-adapted)
        self.min_target, self.max_target = min_target, max_target
        self.max_throttle = max_throttle
        self.crawl_ach = crawl_ach      # False -> skip per-game GetPlayerAchievements (25x faster users)
        self.snowball = snowball        # False -> do not enqueue friends (avoid bias)
        self.user_source = user_source  # "queue" (snowball BFS) | "random" (unbiased accountID sampling)
        self.random_max = random_max
        import random as _random
        self.rng = _random.Random(random_seed)
        self._last_start = None
        self.calls = 0
        self.throttle_hits = 0
        self._ok_streak = 0
        self.throttle_streak = 0
        self.budget_exhausted = False
        self.circuit_open = False

    def _pace(self):
        """Wall-clock pacing: ensure `target` elapsed between consecutive request STARTS,
        absorbing RTT into the interval (cadence = target regardless of latency)."""
        if self._last_start is not None:
            wait = self.target - (time.monotonic() - self._last_start)
            if wait > 0:
                time.sleep(wait)
        self._last_start = time.monotonic()

    def get(self, url, params, store=False):
        """Reserve-before-call PER HTTP attempt (429 retries counted too -> the daily cap
        is never under-counted). 200 -> json; other non-429 -> None; persistent 429 ->
        Throttled. AIMD adapts `target`."""
        p = dict(params)
        if not store:
            p["key"] = self.key
        for attempt in range(5):
            if not db.reserve(self.conn, 1, self.limit):
                raise db.BudgetExhausted()
            self.calls += 1
            self._pace()
            try:
                r = requests.get(url, params=p, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
            except Exception:
                time.sleep(2)
                continue
            if r.status_code == 429:
                self.throttle_hits += 1
                self._ok_streak = 0
                self.target = min(self.max_target, self.target * 1.7)   # AIMD: slow down
                time.sleep(min(120, 8 * (2 ** attempt)))                # exp backoff this attempt
                continue
            if r.status_code != 200:
                return None
            self._ok_streak += 1
            if self._ok_streak >= 25:
                self.target = max(self.min_target, self.target * 0.9)   # AIMD: speed up
                self._ok_streak = 0
            try:
                return r.json()
            except Exception:
                return None
        raise Throttled()

    # ---------- Phase 1: users ----------
    def crawl_user(self, sid) -> bool:
        """Crawl one user fully. Returns True if processed (public or genuinely private),
        False if a transient error left it pending (retry later). complete=1 set only at
        the very end -> atomic."""
        sid = int(sid)
        depth = db.queue_depth_of(self.conn, sid)
        j = self.get(f"{API}/IPlayerService/GetOwnedGames/v1/",
                     {"steamid": sid, "include_appinfo": 1, "include_played_free_games": 1,
                      "format": "json"})
        if j is None:
            return False  # transient (non-200) -> leave pending, do NOT mark private
        games = (j.get("response") or {}).get("games")
        if games is None:
            db.upsert_user(self.conn, sid, public=0, complete=1, fetched_at=db.now_iso())
            return True   # genuinely private (200 with no games)

        owned = [(sid, int(g["appid"]), _f(g.get("playtime_forever")), _f(g.get("playtime_2weeks")),
                  _f(g.get("playtime_windows_forever")), _f(g.get("playtime_mac_forever")),
                  _f(g.get("playtime_linux_forever")), _f(g.get("playtime_deck_forever")),
                  _f(g.get("playtime_disconnected")), _i(g.get("rtime_last_played")),
                  int(bool(g.get("has_community_visible_stats"))), None, g.get("img_icon_url"))
                 for g in games]
        db.upsert_many(self.conn, "owned",
                       ["steamid", "appid", "playtime_forever", "playtime_2weeks",
                        "playtime_windows", "playtime_mac", "playtime_linux", "playtime_deck",
                        "playtime_disconnected", "rtime_last_played", "has_stats",
                        "has_leaderboards", "img_icon_url"], owned)
        # game names come FREE here (include_appinfo=1) -> seed games(appid,name) w/o clobber
        db.insert_ignore(self.conn, "games", ["appid", "name"],
                         [(int(g["appid"]), g.get("name")) for g in games if g.get("name")])
        db.upsert_user(self.conn, sid, public=1, fetched_at=db.now_iso())

        # recently
        j = self.get(f"{API}/IPlayerService/GetRecentlyPlayedGames/v1/", {"steamid": sid, "format": "json"})
        rec = ((j or {}).get("response") or {}).get("games") or []
        db.upsert_many(self.conn, "recently", ["steamid", "appid", "playtime_2weeks"],
                       [(sid, int(g["appid"]), _f(g.get("playtime_2weeks"))) for g in rec])
        # friends (+ snowball enqueue)
        j = self.get(f"{API}/ISteamUser/GetFriendList/v1/",
                     {"steamid": sid, "relationship": "friend", "format": "json"})
        fr = ((j or {}).get("friendslist") or {}).get("friends") or []
        db.upsert_many(self.conn, "friends", ["steamid", "friend_steamid", "friend_since"],
                       [(sid, _i(f["steamid"]), _i(f.get("friend_since"))) for f in fr if f.get("steamid")])
        if fr and self.snowball:
            db.enqueue_users(self.conn, [f["steamid"] for f in fr if f.get("steamid")], depth + 1)
        # wishlist
        j = self.get(f"{API}/IWishlistService/GetWishlist/v1/", {"steamid": sid})
        wl = ((j or {}).get("response") or {}).get("items") or []
        db.upsert_many(self.conn, "wishlist", ["steamid", "appid", "priority", "date_added"],
                       [(sid, int(w["appid"]), _i(w.get("priority")), _i(w.get("date_added")))
                        for w in wl if w.get("appid")])
        # followed
        j = self.get(f"{API}/IStoreService/GetGamesFollowed/v1/", {"steamid": sid})
        fo = ((j or {}).get("response") or {}).get("games") or []
        db.upsert_many(self.conn, "followed", ["steamid", "appid"],
                       [(sid, int(g["appid"])) for g in fo if g.get("appid")])
        # groups
        j = self.get(f"{API}/ISteamUser/GetUserGroupList/v1/", {"steamid": sid, "format": "json"})
        gr = ((j or {}).get("response") or {}).get("groups") or []
        db.upsert_many(self.conn, "user_groups", ["steamid", "gid"],
                       [(sid, _i(g["gid"])) for g in gr if g.get("gid")])
        # badges (one call -> level + xp + per-game badges; supersedes GetSteamLevel)
        j = self.get(f"{API}/IPlayerService/GetBadges/v1/", {"steamid": sid, "format": "json"})
        resp = (j or {}).get("response") or {}
        db.upsert_user(self.conn, sid, level=_i(resp.get("player_level")), xp=_i(resp.get("player_xp")),
                       xp_needed=_i(resp.get("player_xp_needed_to_level_up")))
        bd = resp.get("badges") or []
        db.upsert_many(self.conn, "badges",
                       ["steamid", "badgeid", "appid", "level", "completion_time", "xp",
                        "scarcity", "border_color"],
                       [(sid, _i(b.get("badgeid")), _i(b.get("appid")) or 0, _i(b.get("level")),
                         _i(b.get("completion_time")), _i(b.get("xp")), _i(b.get("scarcity")),
                         _i(b.get("border_color"))) for b in bd if b.get("badgeid") is not None])

        # achievements: played games (playtime>=floor) that HAVE stats (gating saves calls)
        # NOTE: this is ~96% of per-user API cost (one call per played game). Disabled via
        # --no-achievements to trade the weak aggregate-completion signal (+0.0073) for ~25x
        # more users/day (P4-ext 07-07 finding: individual achievements don't beat completion).
        if self.crawl_ach:
            played = [int(g["appid"]) for g in games
                      if _f(g.get("playtime_forever")) >= self.ach_floor
                      and g.get("has_community_visible_stats")]
            for appid in played:
                j = self.get(f"{API}/ISteamUserStats/GetPlayerAchievements/v1/",
                             {"steamid": sid, "appid": appid})
                ach = ((j or {}).get("playerstats") or {}).get("achievements") if j else None
                if not ach:
                    continue   # stats genuinely absent / private for this game -> no signal
                unlocked = [(a["apiname"], _i(a.get("unlocktime")) or 0)
                            for a in ach if a.get("achieved") == 1 and a.get("apiname")]
                db.upsert_many(self.conn, "player_game_ach",
                               ["steamid", "appid", "unlocked", "total", "checked_at"],
                               [(sid, appid, len(unlocked), len(ach), db.now_iso())])
                if unlocked:
                    m = db.intern_achievements(self.conn, appid, [n for n, _ in unlocked])
                    db.upsert_many(self.conn, "user_achievement", ["steamid", "ach_id", "unlocktime"],
                                   [(sid, m[n], t) for n, t in unlocked if n in m])
        db.upsert_user(self.conn, sid, complete=1)
        return True

    # ---------- Phase 2: games ----------
    def crawl_game(self, appid):
        """Fetch all per-game dimension data ONCE. games.fetched_at stamped LAST = visited."""
        appid = int(appid)
        # appdetails (store API, no key)
        j = self.get(f"{STORE}/api/appdetails", {"appids": appid, "l": "english"}, store=True)
        data = None
        if j:
            node = j.get(str(appid)) or {}
            if node.get("success"):
                data = node.get("data")
        gcols = parse_appdetails(appid, data)
        # SteamSpy (store API, no key)
        if not db.has_steamspy(self.conn, appid):
            js = self.get(STEAMSPY, {"request": "appdetails", "appid": appid}, store=True)
            if js and js.get("appid") is not None:
                db.upsert_many(self.conn, "steamspy",
                               ["appid", "name", "developer", "publisher", "score_rank",
                                "positive", "negative", "userscore", "owners", "average_forever",
                                "average_2weeks", "median_forever", "median_2weeks", "price",
                                "initialprice", "discount", "ccu", "languages", "genre",
                                "tags_json", "fetched_at"], [parse_steamspy(appid, js)])
        # achievement schema: display_name + description(condition) + hidden + game stats
        if not db.has_schema(self.conn, appid):
            jsc = self.get(f"{API}/ISteamUserStats/GetSchemaForGame/v2/",
                           {"appid": appid, "l": "english"})
            ags = ((jsc or {}).get("game") or {}).get("availableGameStats") or {}
            achs = ags.get("achievements") or []
            if achs:
                db.upsert_achievement_schema(self.conn, appid, achs)
            stats = ags.get("stats") or []
            if stats:
                db.upsert_many(self.conn, "game_stat",
                               ["appid", "name", "display_name", "default_value"],
                               [(appid, s.get("name"), s.get("displayName"), _f(s.get("defaultvalue")))
                                for s in stats if s.get("name")])
        # global achievement rarity %
        if not db.has_global_pct(self.conn, appid):
            jp = self.get(f"{API}/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/",
                          {"gameid": appid})
            pcts = ((jp or {}).get("achievementpercentages") or {}).get("achievements") or []
            if pcts:
                db.upsert_global_pct(self.conn, appid,
                                     [(a["name"], a["percent"]) for a in pcts if a.get("name") is not None])
        # live concurrent players (official)
        if not db.has_live(self.conn, appid):
            jl = self.get(f"{API}/ISteamUserStats/GetNumberOfCurrentPlayers/v1/", {"appid": appid})
            pc = ((jl or {}).get("response") or {}).get("player_count")
            db.upsert_cols(self.conn, "game_live", ["appid"],
                           {"appid": appid, "player_count": _i(pc), "fetched_at": db.now_iso()})
        # stamp visited LAST (preserves early name if appdetails failed)
        db.upsert_cols(self.conn, "games", ["appid"], {**gcols, "fetched_at": db.now_iso()})

    # ---------- chunk runners (one round-robin slice each) ----------
    def _cooldown(self) -> bool:
        """Handle a Throttled in chunk context. Returns True if the circuit OPENED (stop)."""
        self.throttle_streak += 1
        if self.throttle_streak > self.max_throttle:
            self.circuit_open = True
            log.warning("circuit OPEN: persistent throttle (streak=%d) — pause this cycle",
                        self.throttle_streak)
            return True
        cd = min(600, 300 * self.throttle_streak)
        log.warning("circuit-break: throttled, pausing %ds (streak=%d)", cd, self.throttle_streak)
        time.sleep(cd)
        return False

    STEAMID_BASE = 76561197960265728  # SteamID64 = base + accountID

    def _random_candidates(self, n) -> list[int]:
        """Draw n random accountIDs not already in `users`. Measured (07-07): ~81% exist,
        ~79% public profile, ~11% of public have visible game details -> ~9% crawlable."""
        out, tries = [], 0
        while len(out) < n and tries < n * 5:
            tries += 1
            sid = self.STEAMID_BASE + self.rng.randint(1, self.random_max)
            if self.conn.execute("SELECT 1 FROM users WHERE steamid=?", (sid,)).fetchone():
                continue
            out.append(sid)
        return out

    def _screen_public(self, sids) -> list[int]:
        """Batch GetPlayerSummaries (100 steamids/call) -> keep only public profiles.
        Cheap pre-filter so GetOwnedGames isn't wasted on private/nonexistent accounts."""
        pub = []
        for i in range(0, len(sids), 100):
            j = self.get(f"{API}/ISteamUser/GetPlayerSummaries/v2/",
                         {"steamids": ",".join(str(s) for s in sids[i:i + 100])})
            players = ((j or {}).get("response") or {}).get("players") or []
            pub += [int(p["steamid"]) for p in players
                    if p.get("communityvisibilitystate") == 3 and p.get("steamid")]
        return pub

    def run_users_chunk(self, limit) -> int:
        try:
            if self.user_source == "random":
                # oversample ~1.35x since ~21% of random accounts aren't public
                sids = self._screen_public(self._random_candidates(int(limit * 1.35)))
                if sids:
                    db.enqueue_users(self.conn, sids, depth=-1)  # depth=-1 tags random/OOD panel
            else:
                sids = db.next_pending_users(self.conn, limit)
        except db.BudgetExhausted:
            self.budget_exhausted = True
            return 0
        except Throttled:
            self._cooldown()
            return 0
        done = 0
        for sid in sids:
            try:
                ok = self.crawl_user(sid)
            except db.BudgetExhausted:
                self.budget_exhausted = True
                break
            except Throttled:
                if self._cooldown():
                    break
                break  # leave user pending; next cycle retries
            else:
                self.throttle_streak = 0
                done += int(ok)
        return done

    def run_games_chunk(self, limit) -> int:
        done = 0
        for appid in db.next_games_to_fetch(self.conn, limit):
            try:
                self.crawl_game(appid)
            except db.BudgetExhausted:
                self.budget_exhausted = True
                break
            except Throttled:
                self._cooldown()
                break
            else:
                self.throttle_streak = 0
                done += 1
        return done

    def run_cycle(self, phases, users_chunk, games_chunk) -> int:
        n = 0
        if "users" in phases and not self.budget_exhausted:
            n += self.run_users_chunk(users_chunk)
        if "games" in phases and not self.budget_exhausted and not self.circuit_open:
            n += self.run_games_chunk(games_chunk)
        return n


def bootstrap_from_csv(conn, scores: Path, limit: int, seed: int = 42) -> int:
    """Seed the user queue (depth 0) from distinct steamids in a CSV. Only the ID column
    is used (not the old data) — a pure entry point; friend-snowball grows it from there.
    SEED-SHUFFLED: CSV order groups reviewers by game (biased), so a deterministic shuffle
    makes the early-crawled sample representative; the seq order then stays stable."""
    if not scores.exists():
        return 0
    import random
    ids, seen = [], set()
    with open(scores, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            s = row.get("steamid")
            if s and s not in seen:
                seen.add(s)
                ids.append(s)
            if len(ids) >= limit:
                break
    random.Random(seed).shuffle(ids)
    return db.enqueue_users(conn, ids, depth=0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=db.DEFAULT_DB)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv",
                    help="CSV to bootstrap the user queue (steamid column only)")
    ap.add_argument("--limit", type=int, default=db.DAILY_LIMIT, help="daily call cap (<100k)")
    ap.add_argument("--seed-today", type=int, default=0, help="calls already spent today outside this DB")
    ap.add_argument("--max-bootstrap", type=int, default=200000, help="max steamids to seed from CSV")
    ap.add_argument("--phases", default="users,games", help="comma list: users,games")
    ap.add_argument("--ach-floor", type=float, default=10.0,
                    help="min playtime(min) to crawl a game's achievements")
    ap.add_argument("--target", type=float, default=1.0, help="wall-clock interval seconds (RTT-absorbed)")
    ap.add_argument("--min-target", type=float, default=0.7, help="fastest interval AIMD may reach")
    ap.add_argument("--users-chunk", type=int, default=20)
    ap.add_argument("--games-chunk", type=int, default=60)
    ap.add_argument("--forever", action="store_true", help="run continuously across days")
    ap.add_argument("--loop-sleep", type=int, default=3600, help="sleep when paused/caught-up (--forever)")
    ap.add_argument("--stop-at-users", type=int, default=0,
                    help="stop once this many public+complete users are crawled (0 = no limit)")
    ap.add_argument("--no-achievements", action="store_true",
                    help="skip per-game GetPlayerAchievements (~96%% of user cost) -> ~25x more users/day")
    ap.add_argument("--user-source", choices=["queue", "random"], default="queue",
                    help="queue = snowball BFS from seed; random = unbiased accountID sampling (OOD/P6)")
    ap.add_argument("--random-max", type=int, default=1_600_000_000,
                    help="max accountID for random SteamID sampling")
    ap.add_argument("--random-seed", type=int, default=42)
    ap.add_argument("--no-snowball", action="store_true",
                    help="do not enqueue friends (avoid reintroducing cohort bias)")
    args = ap.parse_args()

    key = os.environ.get("STEAM_API_KEY")
    if not key:
        log.error("STEAM_API_KEY not set"); return 1
    conn = db.connect(args.db)
    if args.seed_today > 0:
        db.seed_today(conn, args.seed_today)
    random_mode = args.user_source == "random"
    snowball = not (args.no_snowball or random_mode)   # random implies no snowball
    # random mode ignores the biased CSV/queue seed entirely
    seeded = 0 if random_mode else bootstrap_from_csv(conn, args.scores, args.max_bootstrap)
    phases = [p.strip() for p in args.phases.split(",") if p.strip()]
    log.info("phases=%s source=%s ach=%s snowball=%s bootstrap=+%d, today_spent=%d, target=%.2fs",
             phases, args.user_source, not args.no_achievements, snowball, seeded,
             db.spent_today(conn), args.target)

    cr = Crawler(conn, key, args.limit, args.target, args.ach_floor, min_target=args.min_target,
                 crawl_ach=not args.no_achievements, snowball=snowball,
                 user_source=args.user_source, random_max=args.random_max,
                 random_seed=args.random_seed)

    def report():
        return {"calls_this_run": cr.calls, "throttle_hits": cr.throttle_hits,
                "final_interval": round(cr.target, 2), "spent_today": db.spent_today(conn),
                "pending_users": db.pending_users(conn), "counts": db.counts(conn)}

    cycles = 0
    while True:
        cr.budget_exhausted = False
        cr.circuit_open = False
        n = cr.run_cycle(phases, args.users_chunk, args.games_chunk)
        cycles += 1
        if cycles % 5 == 0:
            log.info("cycle=%d calls=%d spent_today=%d pending=%d public_done=%d interval=%.2fs throttle=%d",
                     cycles, cr.calls, db.spent_today(conn), db.pending_users(conn),
                     db.public_complete_users(conn), cr.target, cr.throttle_hits)
        if args.stop_at_users and db.public_complete_users(conn) >= args.stop_at_users:
            log.info("TARGET REACHED: %d public+complete users (>= %d). stopping.",
                     db.public_complete_users(conn), args.stop_at_users)
            break
        if cr.budget_exhausted:
            log.info("BUDGET EXHAUSTED today (spent=%d).", db.spent_today(conn))
            if not args.forever:
                break
            time.sleep(args.loop_sleep)
            continue
        if n == 0 and not cr.circuit_open:
            log.info("CAUGHT UP (nothing pending in %s). counts=%s", phases, db.counts(conn))
            if not args.forever:
                break
            time.sleep(args.loop_sleep)
            continue
        if cr.circuit_open and args.forever:
            time.sleep(args.loop_sleep)

    log.info("STOP. %s", json.dumps(report()))
    print(json.dumps(report()))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
