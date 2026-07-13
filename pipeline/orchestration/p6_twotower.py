"""E6 — two-tower retrieval models (industry architecture benchmark).

PRE-REGISTERED PREDICTIONS (written before any run; calibration record):
  P1  Overall NDCG: EASE wins at EVERY graph size we can reach (deep two-tower
      does not cross within our data range). Basis: Mult-DAE lost -0.15 SIG at
      this scale; sparse-implicit literature (MSD 34M interactions) still
      favors linear.
  P2  Scaling slope: two-tower's NDCG-vs-graph-size slope <= EASE's slope
      (no extrapolable crossover from our ladder).
  P3  Cold-item slice (holdout items with graph support < 3): two-tower
      recall > EASE (EASE structurally cannot rank unseen-in-graph items;
      feature towers can).

Design (feature-based towers -> cold-start capable, user-id-free -> works for
unseen users natively):
  item input  = L1-normalized SteamSpy tag-vote vector over a top-N tag vocab.
  user input  = relevance-weighted mean of profile items' tag vectors
                (training excludes the positive item from its own pooling).
  T1 shallow  = single linear map per tower (LightFM-class).
  T2 deep     = 2-layer MLP per tower (in-batch sampled-softmax, the standard
                retrieval recipe, scaled down).
Training: in-batch softmax CE over positives (u, i, w=rel) from GRAPH users
only; panel/eval users never appear in training. CPU-sized (dim 64).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.p6_twotower")
DB = REPO_ROOT / "data_collection" / "steam.db"
SEED = 20260714


def load_tag_features(pool: set[int], n_tags: int = 300):
    """appid -> L1-normalized tag-vote vector over the top-n_tags vocabulary."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT appid, tags_json FROM steamspy WHERE tags_json IS NOT NULL").fetchall()
    con.close()
    votes: dict[str, float] = {}
    parsed = []
    for appid, tj in rows:
        if int(appid) not in pool:
            continue
        try:
            tags = json.loads(tj)
        except Exception:
            continue
        if not isinstance(tags, dict) or not tags:
            continue
        parsed.append((int(appid), tags))
        for t, v in tags.items():
            votes[t] = votes.get(t, 0.0) + float(v)
    vocab = [t for t, _ in sorted(votes.items(), key=lambda x: -x[1])[:n_tags]]
    tidx = {t: i for i, t in enumerate(vocab)}
    feats = {}
    for appid, tags in parsed:
        v = np.zeros(n_tags, dtype=np.float32)
        for t, w in tags.items():
            j = tidx.get(t)
            if j is not None:
                v[j] = float(w)
        s = v.sum()
        if s > 0:
            feats[appid] = v / s
    log.info("tag features: %d items, vocab=%d", len(feats), n_tags)
    return feats, vocab


class Tower(nn.Module):
    def __init__(self, in_dim: int, out_dim: int, deep: bool):
        super().__init__()
        if deep:
            self.net = nn.Sequential(nn.Linear(in_dim, 128), nn.ReLU(),
                                     nn.Linear(128, out_dim))
        else:
            self.net = nn.Linear(in_dim, out_dim, bias=False)

    def forward(self, x):
        z = self.net(x)
        return z / (z.norm(dim=-1, keepdim=True) + 1e-8)


class TwoTower:
    """Trainable feature two-tower; recommend() plugs into the P6 harness."""

    def __init__(self, scores: pd.DataFrame, graph_users: list[int],
                 pool: set[int], feats: dict[int, np.ndarray], deep: bool,
                 dim: int = 64, epochs: int = 6, batch: int = 1024,
                 lr: float = 3e-3, temp: float = 0.07, seed: int = SEED):
        torch.manual_seed(seed)
        np.random.seed(seed % (2 ** 31))
        t0 = time.time()
        d = scores[(scores["s"] > 0) & scores["appid"].isin(set(feats))]
        d = d[d["steamid"].isin(set(graph_users))]
        self.items = np.array(sorted(set(feats) & pool))
        self.col = {a: j for j, a in enumerate(self.items)}
        self.F = torch.tensor(np.stack([feats[a] for a in self.items]))
        self.feats = feats
        in_dim = self.F.shape[1]
        self.user_tower = Tower(in_dim, dim, deep)
        self.item_tower = Tower(in_dim, dim, deep)
        self.temp = temp

        # training triples (u, item_col, w) + per-user pooled feature sums
        u_ids = d["steamid"].astype(int).values
        i_cols = d["appid"].astype(int).map(self.col).values
        w = d["s"].astype(np.float32).values
        urow_map = {u: k for k, u in enumerate(sorted(set(u_ids)))}
        u_rows = np.array([urow_map[u] for u in u_ids])
        n_u = len(urow_map)
        usum = np.zeros((n_u, in_dim), dtype=np.float32)
        utot = np.zeros(n_u, dtype=np.float32)
        Fnp = self.F.numpy()
        np.add.at(utot, u_rows, w)
        for k in range(len(u_rows)):
            usum[u_rows[k]] += w[k] * Fnp[i_cols[k]]
        usum_t, utot_t = torch.tensor(usum), torch.tensor(utot)

        params = list(self.user_tower.parameters()) + list(self.item_tower.parameters())
        opt = torch.optim.Adam(params, lr=lr)
        n = len(u_rows)
        rng = np.random.default_rng(seed)
        for ep in range(epochs):
            perm = rng.permutation(n)
            tot_loss, nb = 0.0, 0
            for s0 in range(0, n, batch):
                idx = perm[s0:s0 + batch]
                if len(idx) < 8:
                    continue
                ur, ic = u_rows[idx], i_cols[idx]
                wt = torch.tensor(w[idx])
                # leave-one-out pooling: subtract the positive from its own user input
                pooled = (usum_t[ur] - wt[:, None] * self.F[ic])
                denom = (utot_t[ur] - wt).clamp(min=1e-6)[:, None]
                uin = pooled / denom
                uvec = self.user_tower(uin)
                ivec = self.item_tower(self.F[ic])
                logits = (uvec @ ivec.T) / self.temp
                loss = nn.functional.cross_entropy(
                    logits, torch.arange(len(idx)), reduction="mean")
                opt.zero_grad()
                loss.backward()
                opt.step()
                tot_loss += float(loss)
                nb += 1
            log.info("twotower(%s) epoch %d/%d loss=%.4f",
                     "deep" if deep else "shallow", ep + 1, epochs, tot_loss / max(nb, 1))
        with torch.no_grad():
            self.I = self.item_tower(self.F)  # item index (n_items x dim)
        log.info("twotower fit: %d users, %d pos, %d items (%.0fs)",
                 n_u, n, len(self.items), time.time() - t0)

    def recommend(self, profile: dict[int, float], k: int, exclude: set[int]) -> list[int]:
        num = np.zeros(self.F.shape[1], dtype=np.float32)
        tot = 0.0
        for a, w in profile.items():
            f = self.feats.get(int(a))
            if f is not None and w > 0:
                num += w * f
                tot += w
        if tot <= 0:
            return []
        with torch.no_grad():
            uvec = self.user_tower(torch.tensor(num / tot)[None, :])
            scores = (self.I @ uvec[0]).numpy()
        for a in profile:
            j = self.col.get(int(a))
            if j is not None:
                scores[j] = -np.inf
        rec = []
        for j in np.argsort(-scores):
            a = int(self.items[j])
            if a not in exclude:
                rec.append(a)
            if len(rec) >= k:
                break
        return rec
