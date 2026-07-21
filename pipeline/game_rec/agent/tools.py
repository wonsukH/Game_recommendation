"""Agent tools — the things the LLM router/critic orchestrate around the CF moat.

Each tool takes a candidate list (appids, ranked) and returns a filtered/scored
list, so they compose: cf_rank -> constraint_filter -> quality_gate -> played_filter.
This is the layer that does what a bare LLM can't reliably do (verified hard
constraints from real metadata) and what a bare CF doesn't (constraints, novelty,
played-state).

Local data only (fast, deterministic):
  - constraints/metadata from outputs/steam_appdetails.csv
    (co-op 2,108 · multiplayer 3,693 · Korean 3,008 · price 78% · release_date)
  - quality from user-score (dense 86.6%, D2) + metacritic (sparse 30.5%) + popularity pct.
Live verification (freshness/existence) is a separate optional tool (steam_live).
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.evaluation.metrics import popularity_percentile  # noqa: E402
from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("game_rec.agent.tools")


def _parse_date(s: str):
    for fmt in ("%b %d, %Y", "%d %b, %Y", "%b %Y", "%Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


class CatalogMeta:
    """Per-game structured metadata for constraint verification (loaded once)."""

    def __init__(self, data_dir: str | Path = REPO_ROOT / "serving" / "data",
                 min_quality_reviews: int = 5):
        data_dir = Path(data_dir)
        maps = load_index_maps(data_dir / "index_maps.json")
        self.appid2row = {int(a): int(r) for a, r in maps["appid2row"].items()}
        pop = np.load(data_dir / "game_popularity.npy").astype(np.float64)
        self._pct = popularity_percentile(pop)

        # D2: dense user-score quality (86.6% coverage vs metacritic 30.5%).
        # quality_pct = percentile rank of a game's Bayesian-shrunk user-score among
        # games with >= min_quality_reviews reviews (so 1-review noise gets no rank).
        self.quality_q: dict[int, float] = {}
        self._quality_pct: dict[int, float] = {}
        qpath = data_dir / "game_quality.json"
        if qpath.exists():
            qobj = json.loads(qpath.read_text(encoding="utf-8"))
            self.quality_q = {int(a): float(g["q"]) for a, g in qobj["games"].items()}
            rated = [(int(a), float(g["q"])) for a, g in qobj["games"].items()
                     if int(g["n"]) >= min_quality_reviews]
            if rated:
                qs = np.array([q for _, q in rated])
                order = np.argsort(np.argsort(qs))  # rank 0..n-1
                denom = max(len(rated) - 1, 1)
                self._quality_pct = {a: float(order[i]) / denom for i, (a, _) in enumerate(rated)}

        # P5: constraint metadata is steam.db-native (build_catalog_db.py ->
        # catalog.json); the old outputs/steam_appdetails.csv path is retired.
        # Prices are in the STORE currency (KRW for ~99.3% of rows; `currency`
        # rides along so max_price — interpreted as KRW — can conservatively
        # drop the small foreign-currency tail instead of leaking it through).
        self.meta: dict[int, dict] = {}
        cat = json.loads((data_dir / "catalog.json").read_text(encoding="utf-8"))
        for a_str, m in cat.items():
            self.meta[int(a_str)] = {
                "coop": bool(m.get("coop")),
                "multiplayer": bool(m.get("multiplayer")),
                "single_player": bool(m.get("single_player")),
                "korean": bool(m.get("korean")),
                "price": m.get("price"),
                "currency": m.get("currency") or "KRW",
                "is_free": bool(m.get("is_free")),
                "release": _parse_date(m.get("release") or ""),
                "metacritic": m.get("metacritic"),
            }

    def pct(self, appid: int) -> float:
        r = self.appid2row.get(int(appid))
        return float(self._pct[r]) if r is not None else 0.0

    def quality_pct(self, appid: int) -> float | None:
        """User-score quality percentile in [0,1] (None if too few reviews)."""
        return self._quality_pct.get(int(appid))

    # ----- tools -----
    def constraint_filter(self, candidates: list[int], constraints: dict) -> list[int]:
        """Keep candidates satisfying ALL hard constraints.

        constraints keys (any subset): coop, multiplayer, single_player (bool),
        korean (bool), free (bool), max_price (float USD), released_after (year int).
        Missing metadata for a required field = drop (conservative).
        """
        if not constraints:
            return candidates
        out = []
        for a in candidates:
            m = self.meta.get(int(a))
            if m is None:
                continue
            ok = True
            for key in ("coop", "multiplayer", "single_player", "korean"):
                if constraints.get(key) and not m.get(key):
                    ok = False; break
            if ok and constraints.get("free") and not m["is_free"]:
                ok = False
            if ok and constraints.get("max_price") is not None:
                # max_price is KRW (Korean-facing app). Non-KRW-priced rows
                # (~0.7%, geo hiccups in the crawl) are dropped conservatively
                # — same policy as missing metadata.
                p = m["price"]
                if p is None or m.get("currency", "KRW") != "KRW" \
                        or p > float(constraints["max_price"]):
                    ok = False
            if ok and constraints.get("released_after") is not None:
                rel = m["release"]
                if rel is None or rel.year < int(constraints["released_after"]):
                    ok = False
            if ok:
                out.append(a)
        return out

    def quality_gate(self, candidates: list[int], min_metacritic: int | None = 75,
                     min_quality_pct: float | None = None,
                     niche_max_pct: float | None = None) -> list[int]:
        """Keep acclaimed games. Two quality signals act as independent drop-filters
        (a game with no signal at all is kept — conservative):
          - min_metacritic: drop if metacritic known AND below it (30.5% coverage).
          - min_quality_pct: drop if user-score quality percentile known AND below it
            (D2 dense signal, 86.6% coverage — the one that actually bites).
        niche_max_pct: also require popularity percentile <= it (hidden-gem mode).
        """
        out = []
        for a in candidates:
            m = self.meta.get(int(a), {})
            mc = m.get("metacritic")
            if min_metacritic is not None and mc is not None and mc < min_metacritic:
                continue
            if min_quality_pct is not None:
                qp = self.quality_pct(a)
                if qp is not None and qp < min_quality_pct:
                    continue
            if niche_max_pct is not None and self.pct(a) > niche_max_pct:
                continue
            out.append(a)
        return out


def played_filter(candidates: list[int], exclude: set[int]) -> list[int]:
    """Drop games the user already owns/played/disliked (memory)."""
    ex = set(int(x) for x in exclude)
    return [a for a in candidates if int(a) not in ex]


if __name__ == "__main__":
    # sanity: constraint coverage should match the metadata inventory
    cm = CatalogMeta()
    allids = list(cm.meta.keys())
    coop = cm.constraint_filter(allids, {"coop": True})
    kor = cm.constraint_filter(allids, {"korean": True})
    cheap = cm.constraint_filter(allids, {"max_price": 10.0})
    print(f"meta games={len(allids)} | co-op={len(coop)} | korean={len(kor)} | <=$10={len(cheap)}")
    # D2: dense quality gate should bite on ~most games (vs metacritic's 30%)
    pool = list(cm.appid2row.keys())
    print(f"quality_pct coverage={len(cm._quality_pct)}/{len(pool)} "
          f"({100*len(cm._quality_pct)/len(pool):.1f}%)")
    top_q = cm.quality_gate(pool, min_metacritic=None, min_quality_pct=0.5)
    top_mc = cm.quality_gate(pool, min_metacritic=75)
    print(f"keep with user-score>=p50: {len(top_q)} | keep with metacritic>=75: {len(top_mc)}")
