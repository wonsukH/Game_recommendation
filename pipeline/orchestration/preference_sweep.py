"""P4 Step 3 — evolutionary preference-sweep harness (funnel evaluator).

Evaluates behavioral preference-score candidates (behavioral_scores.REGISTRY)
through the approved funnel on frozen user panels, with the fixed neutral
target and the [F6] discipline. One invocation = one evaluation batch; the
LLM loop reads the leaderboard/journal between batches and appends candidates.

Fixed design (plan recursive-dreaming-moore.md):
- fitness: graded NDCG@20 on a NEUTRAL relevance target (per-game engagement
  percentile, completion-aware via max(pt_pctl, completion_pctl) — self-adapting
  across game types, no explicit type branching) + recall@20 + SNIPS-debiased
  recall@20 (popularity-propensity, clipped) + long-tail recall + Spearman.
- panels [F1/F6]: users split ONCE into train / dev / private (frozen json).
  Graphs are built on TRAIN users only (leave-panel-out). Common seed, common
  per-user 70/30 profile/holdout across all candidates (paired comparisons).
- rankers: weighted conditional-cosine co-play CF (graded X = s; per-edge
  support floor on UNWEIGHTED co-counts >= min_cooc) and RP3beta (binary walk,
  popularity^beta discount) for the dual screening gate.
- anchors every round [F2]: ORACLE (holdout itself), POP, and the random_s
  registry candidate. If random_s ranks near real candidates the metric is broken.

Memory-safe scoring: sim columns are computed only for the union of panel
profiles (chunked sparse matmuls) — the full item x item C is never materialized.

Outputs per round under experiments/p4_sweep/rounds/<round>/:
  leaderboard.csv, per_user_<cand>.csv, config.json
plus cumulative experiments/p4_sweep/LEADERBOARD.md and registry.jsonl lines.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.evaluation.stats import bootstrap_ci, paired_bootstrap_diff  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.preference_sweep")

P4 = REPO_ROOT / "experiments" / "p4_sweep"
OUT = REPO_ROOT / "outputs" / "p4"
MIN_COOC = 3
DEBIAS_CLIP = 10.0


# ---------------------------------------------------------------- artifacts

def load_artifacts():
    inter = pd.read_pickle(OUT / "interactions.pkl")
    game_stats = pd.read_pickle(OUT / "game_stats.pkl")
    user_stats = pd.read_pickle(OUT / "user_stats.pkl")
    pool = set(json.loads((OUT / "pool.json").read_text())["pool"])
    return inter, game_stats, user_stats, pool


def build_relevance(inter: pd.DataFrame, pool: set[int]) -> pd.DataFrame:
    """Neutral graded target: max(per-game pt pctl, per-game completion pctl)."""
    d = inter[inter["appid"].isin(pool)].copy()
    pt_p = bs._pos_pctl_within(d, "playtime_forever", "appid")
    has = d["ach_total"].fillna(0) > 0
    tmp = d.copy()
    tmp["c"] = np.where(has, d["completion"].fillna(0.0), np.nan)
    cpos = tmp[tmp["c"].notna()]
    r = cpos.groupby("appid")["c"].rank(method="average")
    n = cpos.groupby("appid")["c"].transform("size")
    c_p = pd.Series(np.nan, index=tmp.index)
    c_p.loc[cpos.index] = ((r - 0.5) / n).values
    rel = pd.concat([pt_p, c_p], axis=1).max(axis=1)
    out = d[["steamid", "appid"]].copy()
    out["rel"] = rel.fillna(0.0).astype(np.float32)
    return out[out["rel"] > 0]


def get_panels(rel: pd.DataFrame, seed: int = 42, dev_n: int = 200, priv_n: int = 150,
               min_items: int = 12) -> dict:
    """Frozen train/dev/private user split (created once, reused every round)."""
    path = P4 / "panels.json"
    if path.exists():
        return json.loads(path.read_text())
    cnt = rel.groupby("steamid").size()
    eligible = sorted(int(u) for u in cnt[cnt >= min_items].index)
    rng = np.random.default_rng(seed)
    rng.shuffle(eligible)
    panels = {
        "seed": seed, "min_items": min_items,
        "dev": eligible[:dev_n],
        "private": eligible[dev_n:dev_n + priv_n],
    }
    all_users = set(int(u) for u in rel["steamid"].unique())
    panels["train"] = sorted(all_users - set(panels["dev"]) - set(panels["private"]))
    path.write_text(json.dumps(panels), encoding="utf-8")
    log.info("panels frozen: train=%d dev=%d private=%d (eligible=%d)",
             len(panels["train"]), len(panels["dev"]), len(panels["private"]), len(eligible))
    return panels


def split_profile_holdout(rel: pd.DataFrame, users: list[int], seed: int = 42,
                          frac: float = 0.7) -> dict:
    """Per-user common split over positive-relevance pool items."""
    out = {}
    rel_u = rel[rel["steamid"].isin(users)]
    for uid, grp in rel_u.groupby("steamid"):
        items = grp[["appid", "rel"]].values
        rng = np.random.default_rng(seed + int(uid) % (2 ** 31))
        idx = rng.permutation(len(items))
        n_prof = max(1, int(round(len(items) * frac)))
        prof = items[idx[:n_prof]]
        hold = items[idx[n_prof:]]
        if len(hold) == 0:
            continue
        out[int(uid)] = {
            "profile": {int(a): float(r) for a, r in prof},
            "holdout": {int(a): float(r) for a, r in hold},
        }
    return out


# ---------------------------------------------------------------- rankers

class GradedCF:
    """Weighted conditional-cosine co-play CF with unweighted support floor.

    Column-chunked: sim columns computed only for `need_items`.
    """

    def __init__(self, scores: pd.DataFrame, train_users: list[int], pool: set[int],
                 min_cooc: int = MIN_COOC, graph_mode: str = "weighted"):
        t = time.time()
        d = scores[(scores["s"] > 0) & scores["appid"].isin(pool)]
        d = d[d["steamid"].isin(set(train_users))]
        self.items = np.array(sorted(d["appid"].unique()))
        self.col = {a: j for j, a in enumerate(self.items)}
        urow = {u: i for i, u in enumerate(sorted(d["steamid"].unique()))}
        r = d["steamid"].map(urow).values
        c = d["appid"].map(self.col).values
        # graph_mode="binary": s gates MEMBERSHIP only (edge weights all-ones),
        # while profile w_p stays graded — the two-knob attribution ablation.
        v = (np.ones(len(d), np.float32) if graph_mode == "binary"
             else d["s"].values.astype(np.float32))
        n_u, n_i = len(urow), len(self.items)
        self.Xw = sparse.csr_matrix((v, (r, c)), shape=(n_u, n_i))
        self.Xb = sparse.csr_matrix((np.ones_like(v), (r, c)), shape=(n_u, n_i))
        self.deg_w = np.asarray(self.Xw.multiply(self.Xw).sum(axis=0)).ravel()
        self.min_cooc = min_cooc
        log.info("GradedCF graph: %d train users x %d items, nnz=%d (%.1fs)",
                 n_u, n_i, self.Xw.nnz, time.time() - t)

    def sim_columns(self, need_appids: list[int]) -> tuple[sparse.csr_matrix, dict]:
        cols = [self.col[a] for a in need_appids if a in self.col]
        amap = {a: k for k, a in enumerate([a for a in need_appids if a in self.col])}
        if not cols:
            return sparse.csr_matrix((len(self.items), 0)), amap
        Cw = (self.Xw.T @ self.Xw[:, cols]).tocsr()
        Cb = (self.Xb.T @ self.Xb[:, cols]).tocsr()
        Cw = Cw.multiply(Cb >= self.min_cooc)
        dw = np.sqrt(np.maximum(self.deg_w, 1e-12))
        inv_rows = sparse.diags(1.0 / dw)
        inv_cols = sparse.diags(1.0 / dw[cols])
        S = (inv_rows @ Cw @ inv_cols).tocsc()
        return S, amap

    def recommend(self, profile: dict[int, float], S, amap, k: int, exclude: set[int]) -> list[int]:
        use = [(a, w) for a, w in profile.items() if a in amap]
        if not use:
            return []
        acc = np.zeros(S.shape[0], dtype=np.float64)
        for a, w in use:
            j = amap[a]
            colv = S.getcol(j)
            acc[colv.indices] += w * colv.data
        for a, _ in use:
            if a in self.col:
                acc[self.col[a]] = 0.0
        order = np.argsort(-acc)
        rec = []
        for j in order[: k * 3]:
            if acc[j] <= 0:
                break
            a = int(self.items[j])
            if a in exclude:
                continue
            rec.append(a)
            if len(rec) >= k:
                break
        return rec


class RP3B:
    """Weighted 2-step random walk with popularity^beta discount (dual gate ranker).

    Uses the CANDIDATE's graded s as transition weights (true second ranker-view
    of the same preference — a binary walk would be candidate-blind)."""

    def __init__(self, scores: pd.DataFrame, train_users: list[int], pool: set[int],
                 beta: float = 0.6):
        d = scores[(scores["s"] > 0) & scores["appid"].isin(pool)]
        d = d[d["steamid"].isin(set(train_users))]
        self.items = np.array(sorted(d["appid"].unique()))
        self.col = {a: j for j, a in enumerate(self.items)}
        urow = {u: i for i, u in enumerate(sorted(d["steamid"].unique()))}
        r = d["steamid"].map(urow).values
        c = d["appid"].map(self.col).values
        X = sparse.csr_matrix((d["s"].values.astype(np.float32), (r, c)),
                              shape=(len(urow), len(self.items)))
        u_deg = np.asarray(X.sum(axis=1)).ravel()
        i_deg = np.asarray(X.sum(axis=0)).ravel()
        self.Pu = sparse.diags(1.0 / np.maximum(u_deg, 1)) @ X       # user -> item
        self.PiT = (sparse.diags(1.0 / np.maximum(i_deg, 1)) @ X.T).tocsr()  # item -> user
        self.pop_disc = 1.0 / np.power(np.maximum(i_deg, 1), beta)

    def recommend(self, profile: dict[int, float], k: int, exclude: set[int]) -> list[int]:
        v = np.zeros(len(self.items), dtype=np.float64)
        hits = 0
        for a, w in profile.items():
            j = self.col.get(a)
            if j is not None:
                v[j] = w
                hits += 1
        if hits == 0:
            return []
        # item -> user -> item random walk: (n_i,)->(n_u,)->(n_i,)
        walk = self.Pu.T @ (self.PiT.T @ v)
        walk = np.asarray(walk).ravel() * self.pop_disc
        for a in profile:
            j = self.col.get(a)
            if j is not None:
                walk[j] = 0.0
        order = np.argsort(-walk)
        rec = []
        for j in order[: k * 3]:
            if walk[j] <= 0:
                break
            a = int(self.items[j])
            if a not in exclude:
                rec.append(a)
            if len(rec) >= k:
                break
        return rec


# ---------------------------------------------------------------- metrics

def graded_ndcg(holdout: dict[int, float], rec: list[int], k: int) -> float:
    gains = [holdout.get(a, 0.0) for a in rec[:k]]
    dcg = sum(g / np.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted(holdout.values(), reverse=True)[:k]
    idcg = sum(g / np.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def recall_at(holdout: dict[int, float], rec: list[int], k: int) -> float:
    hs = set(holdout)
    return len(hs & set(rec[:k])) / len(hs) if hs else np.nan


def snips_recall(holdout: dict[int, float], rec: list[int], k: int,
                 prop: dict[int, float]) -> float:
    hs = set(holdout)
    if not hs:
        return np.nan
    w = {a: min(1.0 / max(prop.get(a, 1e-6), 1e-6), DEBIAS_CLIP) for a in hs}
    tot = sum(w.values())
    hit = sum(w[a] for a in hs & set(rec[:k]))
    return hit / tot if tot > 0 else np.nan


def longtail_recall(holdout: dict[int, float], rec: list[int], k: int,
                    pop_pct: dict[int, float]) -> float:
    lt = {a for a in holdout if pop_pct.get(a, 0.0) < 0.5}
    return len(lt & set(rec[:k])) / len(lt) if lt else np.nan


# ---------------------------------------------------------------- funnel ⓪

def intrinsic_prefilter(scores: pd.DataFrame, inter: pd.DataFrame,
                        family: str = "") -> tuple[bool, str]:
    """Conservative pathology cut only (user-confirmed): variance collapse or
    AFK-pathology (suspicious rows scored clearly ABOVE clean rows).

    anchor/binary families are exempt from the variance check — constant s is
    their intended design (membership-only), not a degenerate graded score."""
    pos = scores[scores["s"] > 0]["s"]
    if len(pos) < 1000:
        return False, f"too-few-rows n={len(pos)}"
    if family not in ("anchor", "binary") and float(pos.std()) < 1e-3:
        return False, f"variance-collapse std={pos.std():.2e} n={len(pos)}"
    d = scores.merge(inter[["steamid", "appid", "playtime_forever", "ach_unlocked", "ach_total"]],
                     on=["steamid", "appid"], how="left")
    has = d["ach_total"].fillna(0) > 0
    pt_p = bs._pos_pctl_within(d, "playtime_forever", "appid")
    susp = has & (d["ach_unlocked"].fillna(0) == 0) & (pt_p >= 0.8)
    clean = has & (d["ach_unlocked"].fillna(0) > 0) & (pt_p >= 0.8)
    if susp.sum() > 200 and clean.sum() > 200:
        m_s, m_c = d.loc[susp, "s"].mean(), d.loc[clean, "s"].mean()
        if m_s > m_c * 1.25:
            return False, f"AFK-pathology susp_mean={m_s:.3f} > clean_mean={m_c:.3f}x1.25"
    return True, "pass"


# ---------------------------------------------------------------- round runner

def eval_candidate(name: str, params: dict, inter, game_stats, user_stats, pool,
                   rel, panels, splits, prop, pop_pct, k: int, panel_users: list[int],
                   rankers=("cf",), graph_mode: str = "weighted",
                   wp_mode: str = "graded") -> dict:
    t0 = time.time()
    scores = bs.compute(name, inter, game_stats, user_stats, **(params or {}))
    fam = bs.REGISTRY.get(name, {}).get("family", "")
    ok, why = intrinsic_prefilter(scores, inter, family=fam)
    row = {"candidate": name, "params": json.dumps(params or {}), "prefilter": why}
    if not ok:
        row.update({"status": "cut-prefilter"})
        return row

    smap = {(int(u), int(a)): float(s) for u, a, s in
            scores[scores["s"] > 0][["steamid", "appid", "s"]].values}
    per_user = []
    for ranker in rankers:
        if ranker == "cf":
            model = GradedCF(scores, panels["train"], pool, graph_mode=graph_mode)
            need = sorted({a for u in panel_users for a in splits[u]["profile"]})
            S, amap = model.sim_columns(need)
        else:
            model = RP3B(scores, panels["train"], pool)
        col = f"ndcg_{ranker}"
        for u in panel_users:
            sp = splits[u]
            if wp_mode == "flat":
                prof_w = {a: 1.0 for a in sp["profile"]
                          if smap.get((u, a), 0.0) > 0} or {a: 1.0 for a in sp["profile"]}
            else:
                prof_w = {a: smap.get((u, a), 0.0) for a in sp["profile"]}
                prof_w = {a: w for a, w in prof_w.items() if w > 0} or dict(sp["profile"])
            excl = set(sp["profile"])
            rec = (model.recommend(prof_w, S, amap, k, excl) if ranker == "cf"
                   else model.recommend(prof_w, k, excl))
            per_user.append({
                "steamid": u, "ranker": ranker,
                "ndcg": graded_ndcg(sp["holdout"], rec, k),
                "recall": recall_at(sp["holdout"], rec, k),
                "snips": snips_recall(sp["holdout"], rec, k, prop),
                "longtail": longtail_recall(sp["holdout"], rec, k, pop_pct),
            })
    pu = pd.DataFrame(per_user)
    for ranker in rankers:
        sub = pu[pu["ranker"] == ranker]
        for m in ["ndcg", "recall", "snips", "longtail"]:
            ci = bootstrap_ci(sub[m].dropna().values)
            row[f"{m}_{ranker}"] = round(ci["mean"], 4)
            row[f"{m}_{ranker}_ci"] = f"[{ci['lo']:.3f},{ci['hi']:.3f}]"
    row.update({"status": "ok", "sec": round(time.time() - t0, 1),
                "n_users": int(pu["steamid"].nunique())})
    row["_per_user"] = pu
    return row


def run_round(round_name: str, cand_specs: list[tuple[str, dict]], panel: str = "dev",
              k: int = 20, dual_gate: bool = True, seed: int = 42) -> pd.DataFrame:
    inter, game_stats, user_stats, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel, seed=seed)
    users = panels[panel] if panel in ("dev", "private") else panels["dev"][:50]
    splits = split_profile_holdout(rel, users, seed=seed)
    users = sorted(splits)
    n_users_total = inter["steamid"].nunique()
    own_cnt = inter.groupby("appid").size()
    prop = (own_cnt / n_users_total).to_dict()
    own_pool = own_cnt[own_cnt.index.isin(pool)]
    pop_pct = own_pool.rank(pct=True).to_dict()  # popularity percentile WITHIN pool

    rankers = ("cf", "rp3b") if dual_gate else ("cf",)
    rows, per_user_frames = [], {}
    for spec in cand_specs:
        name, params = spec["name"], spec.get("params") or {}
        alias = spec.get("alias") or name
        log.info("== evaluating %s %s on %s(%d users) rankers=%s",
                 alias, params, panel, len(users), rankers)
        try:
            row = eval_candidate(name, params, inter, game_stats, user_stats, pool,
                                 rel, panels, splits, prop, pop_pct, k, users, rankers,
                                 graph_mode=spec.get("graph", "weighted"),
                                 wp_mode=spec.get("wp", "graded"))
        except Exception as e:  # 자율운행: 기록 후 계속
            log.exception("candidate %s failed", alias)
            row = {"candidate": alias, "params": json.dumps(params),
                   "status": f"error: {type(e).__name__}: {e}"}
        row["candidate"] = alias
        pu = row.pop("_per_user", None)
        if pu is not None:
            per_user_frames[alias] = pu
        rows.append(row)

    lb = pd.DataFrame(rows).sort_values(
        by=[c for c in ["ndcg_cf"] if c in pd.DataFrame(rows).columns] or ["candidate"],
        ascending=False)
    rdir = P4 / "rounds" / round_name
    rdir.mkdir(parents=True, exist_ok=True)
    lb.to_csv(rdir / "leaderboard.csv", index=False)
    for name, pu in per_user_frames.items():
        pu.to_csv(rdir / f"per_user_{name}.csv", index=False)
    (rdir / "config.json").write_text(json.dumps({
        "round": round_name, "panel": panel, "k": k, "seed": seed,
        "dual_gate": dual_gate, "candidates": cand_specs,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }), encoding="utf-8")
    log.info("round %s done -> %s", round_name, rdir)
    return lb


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--round", type=str, required=True)
    ap.add_argument("--candidates", type=str, default="ALL",
                    help="comma list or ALL (registry)")
    ap.add_argument("--spec-file", type=Path, default=None,
                    help="JSON list of {name, params, alias} — overrides --candidates")
    ap.add_argument("--panel", type=str, default="dev", choices=["dev", "private", "small"])
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--no-dual", action="store_true")
    args = ap.parse_args()
    if args.spec_file:
        specs = json.loads(args.spec_file.read_text(encoding="utf-8"))
    else:
        names = list(bs.REGISTRY) if args.candidates == "ALL" else args.candidates.split(",")
        specs = [{"name": n} for n in names]
    lb = run_round(args.round, specs, panel=args.panel, k=args.k,
                   dual_gate=not args.no_dual)
    cols = [c for c in ["candidate", "status", "ndcg_cf", "recall_cf", "snips_cf",
                        "longtail_cf", "ndcg_rp3b", "recall_rp3b", "sec"] if c in lb.columns]
    print(lb[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
