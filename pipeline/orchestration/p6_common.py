"""P6 shared machinery — frozen OOD panels, the confirmation/exploration firewall,
the pre-registered slot registry, and the metric-B (wishlist) target builder.

Everything here IMPLEMENTS `experiments/p4_sweep/P6_PREREG.md` (v3 amendments):
- slots S0a..S5c + null are the FIXED evaluation set (A1); no post-hoc additions.
- EASE slots are scored via the fair list builder `ease_reclist` (no score<=0
  cutoff — the T35 bug must not re-enter through this path).
- metric B follows the frozen operational definition (A5): target = the most
  recent <=10 in-pool NON-owned dated wishlist adds (>=3 required); input = the
  full played profile; wishlist is never a model input. OOD wishlist rows come
  from the freeze-time snapshot (outputs/p6/wishlist_ood.pkl), never the live DB.
- `assert_firewall` is called by every exploration entrypoint: confirmation and
  reserve panel users must never appear in exploration/dry-run/tuning work.

Frozen P4 code is imported, never modified.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.ease_recheck import ease_reclist  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    RP3B, build_relevance, split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import (  # noqa: E402
    EaseRanker, UserKNN, VariantCF)

log = get_logger("orchestration.p6_common")

P6_OUT = REPO_ROOT / "outputs" / "p6"
P4_OUT = REPO_ROOT / "outputs" / "p4"
P6_DIR = REPO_ROOT / "experiments" / "p6_ood"
P4_DIR = REPO_ROOT / "experiments" / "p4_sweep"
PANELS_FILE = P6_DIR / "p6_panels.json"
K = 20

# ---- pre-registered slots (P6_PREREG.md v2 table + v3 amendment A1) ----------
# key -> (preference candidate, params, ranker kind, ranker params)
SLOTS: dict[str, tuple[str, dict, str, dict]] = {
    "S0a": ("pvalue_lognorm_eb", {}, "knn", {"pop_beta": 0.2}),
    "S0b": ("pvalue_lognorm_eb", {}, "knn", {"pop_beta": 0.3}),
    "S1": ("pvalue_lognorm_eb", {}, "knn", {"pop_beta": 0.0}),
    "S2": ("pctl_game", {}, "knn", {"pop_beta": 0.0}),
    "S3": ("per_user_cap", {"base": "blend", "lam": 0.4, "alpha": 0.3}, "rp3b", {}),
    "S4": ("per_user_cap", {"base": "blend", "lam": 0.4, "alpha": 0.3}, "condcos", {}),
    "S5a": ("pvalue_lognorm_eb", {}, "ease", {"lam": 50.0}),
    "S5b": ("pvalue_lognorm_eb", {}, "ease", {"lam": 100.0}),
    "S5c": ("pvalue_lognorm_eb", {}, "ease", {"lam": 200.0}),
    "null": ("random_support", {}, "knn", {"pop_beta": 0.0}),
}


# ------------------------------------------------------------------ artifacts

def load_artifacts(out_dir: Path = P6_OUT):
    """Same shapes as preference_sweep.load_artifacts, parameterized directory."""
    inter = pd.read_pickle(out_dir / "interactions.pkl")
    game_stats = pd.read_pickle(out_dir / "game_stats.pkl")
    user_stats = pd.read_pickle(out_dir / "user_stats.pkl")
    pool = set(json.loads((out_dir / "pool.json").read_text())["pool"])
    return inter, game_stats, user_stats, pool


def sha_ids(ids) -> str:
    return hashlib.sha256(",".join(str(int(u)) for u in sorted(map(int, ids)))
                          .encode()).hexdigest()


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       cwd=REPO_ROOT).decode().strip()
    except Exception:
        return "unknown"


# ------------------------------------------------------------------ panels

def load_panels() -> dict:
    if not PANELS_FILE.exists():
        raise FileNotFoundError(f"{PANELS_FILE} missing — run p6_panel_freeze first")
    return json.loads(PANELS_FILE.read_text())


def assert_firewall(users, panels: dict | None = None) -> None:
    """Exploration work must never touch confirmation/reserve panel users."""
    panels = panels or load_panels()
    protected = set(panels["confirm"]) | set(panels["reserve"])
    leak = protected & {int(u) for u in users}
    if leak:
        raise RuntimeError(
            f"FIREWALL VIOLATION: {len(leak)} protected panel user(s) in an "
            f"exploration set (e.g. {sorted(leak)[:3]})")


def verify_panel_hashes(panels: dict) -> None:
    for key in ("confirm", "reserve"):
        h = sha_ids(panels[key])
        if h != panels[f"sha256_{key}"]:
            raise RuntimeError(f"panel '{key}' hash mismatch — file tampered/corrupted")


# ------------------------------------------------------------------ metric B

def load_wishlist_snapshot(out_dir: Path = P6_OUT) -> pd.DataFrame:
    """Freeze-time OOD wishlist snapshot (A5) — the live DB is NOT consulted."""
    return pd.read_pickle(out_dir / "wishlist_ood.pkl")


def build_wl_targets(users, pool: set[int], owned_pairs: set[tuple[int, int]],
                     wl: pd.DataFrame, max_t: int = 10, min_t: int = 3) -> dict[int, set[int]]:
    """A5 frozen operational definition (identical to audit_verify/ease_recheck):
    per user, the most recent <=max_t dated, in-pool, NON-owned wishlist adds;
    only users with >=min_t targets are metric-B eligible."""
    w = wl[wl["steamid"].isin({int(u) for u in users})
           & wl["appid"].isin(pool) & (wl["date_added"] > 0)]
    w = w.sort_values("date_added", ascending=False)
    tgt: dict[int, set[int]] = {}
    for uid, g in w.groupby("steamid"):
        t = [int(a) for a in g["appid"] if (int(uid), int(a)) not in owned_pairs][:max_t]
        if len(t) >= min_t:
            tgt[int(uid)] = set(t)
    return tgt


# ------------------------------------------------------------------ slot fitting

def fit_slot(key: str, inter, game_stats, user_stats, pool: set[int],
             graph_users: list[int], need_appids: list[int] | None = None,
             spec: tuple | None = None):
    """Fit one pre-registered slot on the given graph membership.

    Returns (rec_fn, smap): rec_fn(profile, k, exclude) -> ranked appids;
    smap[(u, a)] -> preference weight for profile construction.
    `need_appids` is required for condcos (column-chunked sim matrix).
    `spec` overrides the registered spec (V1 replication extras only).
    """
    pref, pparams, rkind, rparams = spec or SLOTS[key]
    scores = bs.compute(pref, inter, game_stats, user_stats, **pparams)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            scores[scores["s"] > 0][["steamid", "appid", "s"]].values}
    if rkind == "knn":
        m = UserKNN(scores, graph_users, pool, topk_users=25,
                    pop_beta=rparams.get("pop_beta", 0.0))
        rec_fn = m.recommend
    elif rkind == "rp3b":
        m = RP3B(scores, graph_users, pool, beta=0.6)
        rec_fn = m.recommend
    elif rkind == "ease":
        m = EaseRanker(scores, graph_users, pool, lam=rparams["lam"])
        rec_fn = lambda prof, k, excl, _m=m: ease_reclist(_m, prof, k, excl)  # noqa: E731
    elif rkind == "condcos":
        if need_appids is None:
            raise ValueError("condcos slot needs need_appids")
        m = VariantCF(scores, graph_users, pool, kind="condcos")
        S, amap = m.sim_columns(sorted(set(need_appids)))
        rec_fn = lambda prof, k, excl, _m=m, _S=S, _a=amap: _m.recommend(prof, _S, _a, k, excl)  # noqa: E731
    else:
        raise ValueError(f"unknown ranker kind {rkind}")
    return rec_fn, smap


def pop_ranker(inter, pool: set[int], graph_users: list[int]):
    """POP anchor: pool items ranked by ownership count among graph users."""
    d = inter[inter["appid"].isin(pool) & inter["steamid"].isin(set(graph_users))]
    top = d.groupby("appid").size().sort_values(ascending=False)
    ranked = [int(a) for a in top.index]

    def rec_fn(profile, k, exclude):
        out = []
        for a in ranked:
            if a in exclude or a in profile:
                continue
            out.append(a)
            if len(out) >= k:
                break
        return out
    return rec_fn


# ------------------------------------------------------------------ profiles

def graded_profile(u: int, appids, smap: dict, rel_fallback: dict | None = None):
    """fresh_panel_check/ease_recheck profile semantics: candidate weights where
    positive, else fall back to the given weights (or flat 1.0)."""
    p = {int(a): smap.get((int(u), int(a)), 0.0) for a in appids}
    p = {a: w for a, w in p.items() if w > 0}
    if p:
        return p
    if rel_fallback:
        return dict(rel_fallback)
    return {int(a): 1.0 for a in appids}


__all__ = [
    "SLOTS", "K", "P6_OUT", "P4_OUT", "P6_DIR", "P4_DIR", "PANELS_FILE",
    "load_artifacts", "load_panels", "load_wishlist_snapshot", "assert_firewall",
    "verify_panel_hashes", "build_wl_targets", "fit_slot", "pop_ranker",
    "graded_profile", "sha_ids", "git_head", "build_relevance",
    "split_profile_holdout",
]
