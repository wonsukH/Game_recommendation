"""P5 — catalog-side serving artifacts, steam.db-native (no CSV inputs).

Replaces the review-CSV-era producers while keeping the consumer contracts
(CatalogMeta / ContentLayer / title maps) byte-compatible where possible:

  index_maps.json        appid2row / row2appid over the P5 pool + tag2idx
  X_game_tag_csr.npz     binary pool×tag matrix from steamspy.tags_json
                         (coverage ~35k games vs the old 9,956 CSV build)
  game_popularity.npy    row-aligned UNBIASED ownership rates (E2 artifact
                         outputs/p6/pop_unbiased.json); missing -> eps floor
  game_quality.json      Bayesian-shrunk SteamSpy positive-share (same shrink
                         formula as the old build_quality.py, source swapped)
  steam_games_tags.csv   appid,game_title,tags (tracked title/tag CSV, regen)
  catalog.json           per-appid constraint metadata from `games`
                         (coop/multiplayer/single_player/korean/price/is_free/
                          release/metacritic) — replaces steam_appdetails.csv

Pure functions take DataFrames (unit-testable); main() wires the DB reads.
Tag canonicalization reuses tag_vocab.normalize_tag/apply_alias and the
existing curated vocab (outputs/tag_vocab.json) when present.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, save_npz

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data.tag_vocab import apply_alias, normalize_tag  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("data.build_catalog_db")

DB_DEFAULT = REPO_ROOT / "data_collection" / "steam.db"
POOL_DEFAULT = REPO_ROOT / "outputs" / "p5" / "pool.json"
POP_DEFAULT = REPO_ROOT / "outputs" / "p6" / "pop_unbiased.json"
VOCAB_DEFAULT = REPO_ROOT / "outputs" / "tag_vocab.json"
OUT_DEFAULT = REPO_ROOT / "serving" / "data"
MIN_TAG_VOTES = 5


# ------------------------------------------------------------ pure functions

def build_tag_bags(tags_df: pd.DataFrame, pool: list[int],
                   allowed: set[str] | None, min_votes: int = MIN_TAG_VOTES):
    """(appid, tags_json) rows -> {appid: [canonical tags]} over the pool."""
    pool_set = set(int(a) for a in pool)
    bags: dict[int, list[str]] = {}
    for r in tags_df.itertuples():
        a = int(r.appid)
        if a not in pool_set or not isinstance(r.tags_json, str):
            continue
        try:
            d = json.loads(r.tags_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(d, dict):
            continue
        tags = []
        for t, v in d.items():
            if not isinstance(v, (int, float)) or v < min_votes:
                continue
            ct = apply_alias(normalize_tag(t))
            if allowed is not None and ct not in allowed:
                continue
            if ct:
                tags.append(ct)
        if tags:
            bags[a] = sorted(set(tags))
    return bags


def build_tag_matrix(bags: dict[int, list[str]], pool: list[int]):
    """-> (X binary csr pool×tags, tag2idx). Row order == pool order."""
    vocab = sorted({t for ts in bags.values() for t in ts})
    tag2idx = {t: j for j, t in enumerate(vocab)}
    rows, cols = [], []
    for r, a in enumerate(pool):
        for t in bags.get(int(a), []):
            rows.append(r)
            cols.append(tag2idx[t])
    X = csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)),
                   shape=(len(pool), len(vocab)))
    return X, tag2idx


def build_popularity(pool: list[int], rates: dict[str, float]) -> np.ndarray:
    """Row-aligned unbiased ownership rate; missing -> min positive rate."""
    vals = np.array([float(rates.get(str(int(a)), 0.0)) for a in pool])
    pos = vals[vals > 0]
    eps = float(pos.min()) if len(pos) else 1e-6
    vals[vals <= 0] = eps
    return vals


def build_quality_steamspy(ss_df: pd.DataFrame, pool: list[int],
                           prior_m: float = 200.0) -> dict:
    """Bayesian-shrunk positive-share (0-10 scale, old q semantics).
    q = (n*raw + m*gmean) / (n + m), raw = 10*pos/(pos+neg), n = pos+neg."""
    pool_set = set(int(a) for a in pool)
    d = ss_df[ss_df["appid"].isin(pool_set)].copy()
    d["n"] = d["positive"].fillna(0) + d["negative"].fillna(0)
    d = d[d["n"] > 0]
    d["raw"] = 10.0 * d["positive"].fillna(0) / d["n"]
    gmean = float(np.average(d["raw"], weights=np.minimum(d["n"], 1000))) if len(d) else 0.0
    games = {}
    for r in d.itertuples():
        q = (r.n * r.raw + prior_m * gmean) / (r.n + prior_m)
        games[str(int(r.appid))] = {"q": round(float(q), 4), "n": int(r.n),
                                    "raw": round(float(r.raw), 4)}
    return {"global_mean": round(gmean, 4), "prior_m": prior_m,
            "source": "steamspy positive/negative", "games": games}


def parse_catalog_row(row) -> dict:
    """games-table row -> CatalogMeta constraint dict (release kept as string)."""
    cats = ""
    if isinstance(row.categories_json, str) and row.categories_json:
        try:
            cats = " ".join(str(c.get("description", "")) for c in
                            json.loads(row.categories_json) if isinstance(c, dict))
        except (json.JSONDecodeError, TypeError):
            cats = ""
    langs = row.supported_languages or ""
    is_free = bool(row.is_free)
    price = None
    currency = getattr(row, "price_currency", None)
    if row.price_final is not None and not pd.isna(row.price_final):
        # price_final is in hundredths of the STORE currency (KRW for ~99.3%
        # of rows; a small foreign-currency tail exists — currency is stored
        # so the filter can handle it conservatively)
        price = float(row.price_final) / 100.0
    mc = None
    if row.metacritic_score is not None and not pd.isna(row.metacritic_score) \
            and float(row.metacritic_score) > 0:
        mc = float(row.metacritic_score)
    return {
        "coop": "Co-op" in cats,
        "multiplayer": "Multi-player" in cats,
        "single_player": "Single-player" in cats,
        "korean": "Korean" in str(langs),
        "price": 0.0 if is_free else price,
        "currency": currency if not is_free else "KRW",
        "is_free": is_free,
        "release": row.release_date or None,
        "metacritic": mc,
    }


# ------------------------------------------------------------ main wiring

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    ap.add_argument("--pool", type=Path, default=POOL_DEFAULT)
    ap.add_argument("--pop", type=Path, default=POP_DEFAULT)
    ap.add_argument("--vocab", type=Path, default=VOCAB_DEFAULT)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--prior-m", type=float, default=200.0)
    args = ap.parse_args()

    pool = sorted(int(a) for a in json.loads(args.pool.read_text())["pool"])
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    games = pd.read_sql_query(
        "SELECT appid, name, categories_json, supported_languages, price_final, "
        "price_currency, is_free, release_date, metacritic_score "
        "FROM games WHERE name IS NOT NULL", con)
    ss = pd.read_sql_query(
        "SELECT appid, positive, negative, tags_json FROM steamspy", con)
    con.close()

    allowed = None
    if args.vocab.exists():
        raw = json.loads(args.vocab.read_text(encoding="utf-8"))
        allowed = set(raw if isinstance(raw, list) else raw.get("tags", []))
        log.info("curated tag vocab: %d tags", len(allowed))

    bags = build_tag_bags(ss[["appid", "tags_json"]], pool, allowed)
    X, tag2idx = build_tag_matrix(bags, pool)
    quality = build_quality_steamspy(ss, pool, args.prior_m)
    rates = json.loads(args.pop.read_text())
    popularity = build_popularity(pool, rates)

    name_map = dict(zip(games["appid"].astype(int), games["name"]))
    catalog = {}
    for r in games.itertuples():
        a = int(r.appid)
        if a in set(pool):
            catalog[str(a)] = parse_catalog_row(r)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "index_maps.json").write_text(json.dumps({
        "appid2row": {str(a): r for r, a in enumerate(pool)},
        "row2appid": {str(r): a for r, a in enumerate(pool)},
        "tag2idx": tag2idx,
        "idx2tag": {str(j): t for t, j in tag2idx.items()}}), encoding="utf-8")
    save_npz(out / "X_game_tag_csr.npz", X)
    (out / "game_quality.json").write_text(json.dumps(quality), encoding="utf-8")
    np.save(out / "game_popularity.npy", popularity)
    (out / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    rows = [{"appid": a, "game_title": name_map.get(a, ""),
             "tags": ",".join(bags.get(a, []))} for a in pool]
    pd.DataFrame(rows).to_csv(out / "steam_games_tags.csv", index=False)

    stats = {"pool": len(pool), "tagged_games": len(bags), "tags": len(tag2idx),
             "quality_games": len(quality["games"]),
             "pop_nonmissing": int((popularity > popularity.min()).sum()),
             "catalog_rows": len(catalog)}
    log.info("catalog artifacts -> %s | %s", out, stats)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
