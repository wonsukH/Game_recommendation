"""Two recommenders for the agentic-value A/B — deterministic core (no LLM noise).

The "agentic" substance being tested is the ORCHESTRATION (multi-entity fusion +
under-fill refine loop), not LLM-ness. So both pipelines take already-structured
input (libraries, constraints) and we compare the orchestration directly. The LLM
router/explanation is the serving interface (Phase E) + a separate routing-accuracy
test — kept out of here so the agentic-vs-not comparison isn't confounded by LLM
parse quality.

- NonAgentic : single pass over ONE library — cf top-window -> constraint filter ->
  top-K. No multi-entity, no refine. (What a naive CF+filter pipeline does.)
- Agentic    : multi-entity fusion (good for ALL entities) over the FULL scored
  pool + critic/refine loop (if <K after filtering, relax the softest constraint).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.agent.tools import played_filter  # noqa: E402

# Order in which the agent relaxes constraints when results are too few
# (keep the user's explicit intent — coop/korean — longest; drop soft prefs first).
_RELAX_ORDER = ["quality", "released_after", "max_price", "free",
                "single_player", "multiplayer", "coop", "korean"]


def _relax(constraints: dict):
    """Remove/loosen the softest active constraint. Returns (new, what_removed)."""
    c = dict(constraints)
    for key in _RELAX_ORDER:
        if key == "max_price" and c.get("max_price") is not None:
            c["max_price"] = float(c["max_price"]) * 1.5  # loosen, don't drop
            return c, "max_price×1.5"
        if c.get(key):
            c.pop(key)
            return c, f"drop:{key}"
    return c, None


class NonAgentic:
    name = "non_agentic"

    def __init__(self, cf, meta, candidate_window: int = 200):
        self.cf, self.meta, self.w = cf, meta, candidate_window

    def recommend(self, libraries: dict, constraints: dict, k: int = 10,
                  exclude: set | None = None) -> dict:
        # single library only (the primary/first entity) — ignores others by design
        primary = next(iter(libraries.values()))
        acc = self.cf.score(primary)
        order = np.argsort(-acc)
        cand = [self.cf.inv_col[int(j)] for j in order[: self.w] if acc[int(j)] > 0]
        excl = (exclude or set()) | set(int(a) for a in primary)
        cand = played_filter(cand, excl)
        cand = self.meta.constraint_filter(cand, constraints)  # quality_gate not applied (naive)
        return {"recs": cand[:k], "n_valid": len(cand), "trace": {"window": self.w}}


class Agentic:
    name = "agentic"

    def __init__(self, cf, meta, max_refine: int = 2, fusion: str = "interleave"):
        self.cf, self.meta, self.max_refine, self.fusion = cf, meta, max_refine, fusion

    def _norm_accs(self, libraries: dict) -> list[np.ndarray]:
        out = []
        for lib in libraries.values():
            a = self.cf.score(lib)
            m = a.max()
            out.append(a / m if m > 0 else a)
        return out

    def _combine(self, accs: list[np.ndarray]) -> np.ndarray:
        """Score-based multi-entity fusion (single entity -> passthrough)."""
        if len(accs) == 1:
            return accs[0]
        if self.fusion == "min":            # 'good for ALL' (harsh)
            return np.minimum.reduce(accs)
        if self.fusion == "geomean":        # shared taste, smoother than min
            stacked = np.stack(accs)
            return np.exp(np.log(stacked + 1e-9).mean(axis=0)) - 1e-9
        if self.fusion == "balanced":       # high total but penalize imbalance
            stacked = np.stack(accs)
            return stacked.mean(axis=0) - 0.5 * stacked.std(axis=0)
        return np.minimum.reduce(accs)      # default

    def _ranked_full(self, score: np.ndarray, excl: set) -> list[int]:
        order = np.argsort(-score)
        out = []
        for j in order:
            if score[int(j)] <= 0:
                break
            a = self.cf.inv_col.get(int(j))
            if a is not None and a not in excl:
                out.append(a)
        return out

    def recommend(self, libraries: dict, constraints: dict, k: int = 10,
                  exclude: set | None = None) -> dict:
        accs = self._norm_accs(libraries)
        excl = set(exclude or set())
        for lib in libraries.values():
            excl |= set(int(a) for a in lib)

        if self.fusion == "interleave" and len(accs) > 1:
            # round-robin each entity's personalized ranking -> both represented
            per = [self._ranked_full(a, excl) for a in accs]
            full, seen, idx = [], set(), 0
            while any(idx < len(p) for p in per):
                for p in per:
                    if idx < len(p) and p[idx] not in seen:
                        full.append(p[idx]); seen.add(p[idx])
                idx += 1
        else:
            full = self._ranked_full(self._combine(accs), excl)

        # critic + refine: filter; if under-filled, relax softest constraint
        cons, relaxed = dict(constraints), []
        filt = self.meta.constraint_filter(full, cons)
        it = 0
        while len(filt) < k and cons and it < self.max_refine:
            cons, removed = _relax(cons)
            if removed is None:
                break
            relaxed.append(removed)
            filt = self.meta.constraint_filter(full, cons)
            it += 1
        return {"recs": filt[:k], "n_valid": len(filt),
                "trace": {"relaxed": relaxed, "n_entities": len(libraries), "fusion": self.fusion}}
