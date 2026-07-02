"""P4 Step 1 — steam.db -> per-(user,game) behavioral feature tables + eval pool.

Reads the behavioral SQLite store (owned playtime + achievement summaries) and
materializes three pickled DataFrames plus a pool snapshot that the preference
sweep consumes. Deterministic given the db; cheap to re-run (games crawl keeps
filling `games.type`, so re-extract after CAUGHT UP to widen the pool).

Outputs (all under outputs/p4/, gitignored derived data):
  interactions.pkl  per (steamid, appid): playtime_forever, playtime_2weeks,
                    ach_unlocked, ach_total, completion (NaN if no achievements)
  game_stats.pkl    per appid: owner counts, positive-playtime quantiles,
                    completion aggregates, type/coming_soon/name (for pool+norm)
  user_stats.pkl    per steamid: library size, played counts, per-user medians
  pool.json         appids with type=='game' AND coming_soon!=1 (user-confirmed
                    a안: no owner floor; DLC/soundtrack/demo/tool excluded)
  extract_stats.json  coverage numbers (typed fraction etc.) for the journal

Pool policy while the games crawl is still filling: unknown-type games are
EXCLUDED (conservative; re-extract post-crawl restores them). The stats file
reports how many appids that suppresses.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.io import save_stats  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("data.behavioral_extract")

DB_DEFAULT = REPO_ROOT / "data_collection" / "steam.db"
OUT_DEFAULT = REPO_ROOT / "outputs" / "p4"


def _read_sql(conn, sql: str) -> pd.DataFrame:
    t = time.time()
    df = pd.read_sql_query(sql, conn)
    log.info("%s -> %d rows (%.1fs)", sql.split("FROM")[1].split()[0], len(df), time.time() - t)
    return df


def extract(db_path: Path, out_dir: Path) -> dict:
    import sqlite3

    conn = sqlite3.connect(db_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- per-(u,g) interactions: owned playtime x achievement summary -----
    owned = _read_sql(conn, (
        "SELECT o.steamid, o.appid, o.playtime_forever, o.playtime_2weeks "
        "FROM owned o JOIN users u ON u.steamid=o.steamid "
        "WHERE u.public=1 AND u.complete=1"))
    pga = _read_sql(conn, "SELECT steamid, appid, unlocked, total FROM player_game_ach")
    # D-family temporal signals: per-(u,g) first/last unlock timestamps
    ua = _read_sql(conn, (
        "SELECT ua.steamid, ga.appid, MIN(ua.unlocktime) AS unlock_first, "
        "MAX(ua.unlocktime) AS unlock_last, COUNT(*) AS n_unlocks_t "
        "FROM user_achievement ua JOIN game_achievement ga ON ga.ach_id=ua.ach_id "
        "WHERE ua.unlocktime > 0 GROUP BY ua.steamid, ga.appid"))
    inter = owned.merge(pga, on=["steamid", "appid"], how="left")
    inter = inter.merge(ua, on=["steamid", "appid"], how="left")
    inter = inter.rename(columns={"unlocked": "ach_unlocked", "total": "ach_total"})
    inter["playtime_forever"] = inter["playtime_forever"].fillna(0.0)
    inter["playtime_2weeks"] = inter["playtime_2weeks"].fillna(0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        inter["completion"] = np.where(
            inter["ach_total"].fillna(0) > 0,
            inter["ach_unlocked"].fillna(0) / inter["ach_total"],
            np.nan)

    # ---- game-level stats (normalization references + pool metadata) ------
    games_meta = _read_sql(conn, (
        "SELECT g.appid, g.name, g.type, g.coming_soon, g.release_date, g.fetched_at, "
        "s.positive AS ss_positive, s.negative AS ss_negative "
        "FROM games g LEFT JOIN steamspy s ON s.appid=g.appid"))

    pos = inter[inter["playtime_forever"] > 0]
    gq = pos.groupby("appid")["playtime_forever"]
    game_stats = pd.DataFrame({
        "n_owners": inter.groupby("appid").size(),
        "n_played": gq.size(),
        "pt_pos_median": gq.median(),
        "pt_pos_mean": gq.mean(),
        "pt_pos_p90": gq.quantile(0.90),
        "pt_pos_p99": gq.quantile(0.99),
    })
    comp = inter[inter["ach_total"].fillna(0) > 0]
    game_stats["n_ach_rows"] = comp.groupby("appid").size()
    game_stats["completion_median"] = comp.groupby("appid")["completion"].median()
    game_stats["completion_mean"] = comp.groupby("appid")["completion"].mean()
    game_stats = game_stats.reset_index().merge(games_meta, on="appid", how="left")

    # ---- user-level stats (per-user normalization references) -------------
    upos = pos.groupby("steamid")["playtime_forever"]
    user_stats = pd.DataFrame({
        "lib_size": inter.groupby("steamid").size(),
        "n_played": upos.size(),
        "pt_pos_median": upos.median(),
        "pt_pos_mean": upos.mean(),
    })
    user_stats["zero_frac"] = 1.0 - user_stats["n_played"].fillna(0) / user_stats["lib_size"]
    ucomp = comp.groupby("steamid")
    user_stats["ach_games"] = ucomp.size()
    user_stats["completion_mean_user"] = ucomp["completion"].mean() if len(comp) else np.nan
    user_stats = user_stats.reset_index()

    # ---- eval pool (user-confirmed a안) ------------------------------------
    gm = games_meta
    typed = gm[gm["type"].notna()]
    pool_mask = (gm["type"] == "game") & (gm["coming_soon"].fillna(0).astype(int) != 1)
    pool = sorted(int(a) for a in gm.loc[pool_mask, "appid"])
    untyped = int(gm["type"].isna().sum())

    inter.to_pickle(out_dir / "interactions.pkl")
    game_stats.to_pickle(out_dir / "game_stats.pkl")
    user_stats.to_pickle(out_dir / "user_stats.pkl")
    (out_dir / "pool.json").write_text(json.dumps({"pool": pool}), encoding="utf-8")

    stats = {
        "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_users": int(inter["steamid"].nunique()),
        "n_interactions": int(len(inter)),
        "n_played_rows": int((inter["playtime_forever"] > 0).sum()),
        "n_ach_rows": int((inter["ach_total"].fillna(0) > 0).sum()),
        "n_games_seen": int(gm.shape[0]),
        "n_games_typed": int(typed.shape[0]),
        "n_untyped_excluded_from_pool": untyped,
        "pool_size": len(pool),
        "pool_policy": "type=='game' AND coming_soon!=1; unknown-type excluded until games-crawl done (a안, no owner floor)",
    }
    save_stats(stats, out_dir / "extract_stats.json")
    log.info("extract done: %s", stats)
    conn.close()
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()
    stats = extract(args.db, args.out)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
