"""Phase B1 — 신경 CF (Mult-DAE) vs EASE (P4 확장, 07-07).

사용자가 여러 번 요청한 '진짜 딥러닝'. Mult-DAE(denoising autoencoder,
Liang et al. 2018 Mult-VAE의 비변분 형제)를 user×item에 학습 → EASE(정정된
랭커 승자)와 dev NDCG + 독립 위시리스트로 비교. 정직한 기대: 2,900명·희소는
선형(EASE)이 신경망 이기는 알려진 구간 — 확인 목적. torch CPU.
"""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    build_relevance, get_panels, graded_ndcg, load_artifacts,
    split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import EaseRanker  # noqa: E402
from pipeline.orchestration.ease_recheck import ease_reclist  # noqa: E402

log = get_logger("orchestration.dl_recommenders")
torch.manual_seed(0)
rng = np.random.default_rng(21)


class MultDAE(nn.Module):
    def __init__(self, n_items, h1=600, z=200, dropout=0.5):
        super().__init__()
        self.enc1 = nn.Linear(n_items, h1)
        self.enc2 = nn.Linear(h1, z)
        self.dec1 = nn.Linear(z, h1)
        self.dec2 = nn.Linear(h1, n_items)
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        x = F.normalize(x, p=2, dim=1)
        x = self.drop(x)
        h = torch.tanh(self.enc1(x))
        h = torch.tanh(self.enc2(h))
        h = torch.tanh(self.dec1(h))
        return self.dec2(h)  # logits


def pboot(diff, n=5000):
    diff = np.asarray([d for d in diff if np.isfinite(d)], float)
    b = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(n)]
    return float(diff.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main() -> int:
    inter, gs, us, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    poolset = set(pool)

    # 아이템 인덱스 = train 유저가 플레이한 pool 게임
    played = inter[(inter["playtime_forever"] > 0) & inter["appid"].isin(poolset)]
    tr = played[played["steamid"].isin(set(panels["train"]))]
    items = np.array(sorted(tr["appid"].unique()))
    col = {int(a): j for j, a in enumerate(items)}
    urow = {int(u): i for i, u in enumerate(sorted(tr["steamid"].unique()))}
    X = torch.zeros(len(urow), len(items))
    for u, a in tr[["steamid", "appid"]].itertuples(index=False):
        X[urow[int(u)], col[int(a)]] = 1.0
    log.info("Mult-DAE 학습행렬: %d유저 x %d아이템", *X.shape)

    model = MultDAE(len(items))
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    model.train()
    n = X.shape[0]
    for ep in range(250):
        perm = torch.randperm(n)
        for s0 in range(0, n, 256):
            idx = perm[s0:s0 + 256]
            xb = X[idx]
            logits = model(xb)
            logp = F.log_softmax(logits, dim=1)
            loss = -(logp * xb).sum(dim=1).mean()   # multinomial NLL
            opt.zero_grad(); loss.backward(); opt.step()
    model.eval()
    log.info("학습 완료 (loss=%.3f)", float(loss))

    def dae_rec(profile, k, exclude):
        v = torch.zeros(1, len(items))
        for a, w in profile.items():
            j = col.get(int(a))
            if j is not None:
                v[0, j] = 1.0
        if v.sum() == 0:
            return []
        with torch.no_grad():
            s = model(v)[0].numpy()
        for a in profile:
            j = col.get(int(a))
            if j is not None:
                s[j] = -1e9
        rec = []
        for j in np.argsort(-s):
            a = int(items[j])
            if a not in exclude:
                rec.append(a)
            if len(rec) >= k:
                break
        return rec

    # EASE 기준선 (정정 승자)
    sc = bs.compute("pvalue_lognorm_eb", inter, gs, us)
    smap = {(int(u), int(a)): float(s) for u, a, s in
            sc[sc["s"] > 0][["steamid", "appid", "s"]].values}
    ez = EaseRanker(sc, panels["train"], pool, lam=100.0)

    # ---- 평가 ----
    splits = split_profile_holdout(rel, panels["dev"], seed=42)
    uu = sorted(splits)
    con = sqlite3.connect(REPO / "data_collection" / "steam.db")
    wl = pd.read_sql_query("SELECT steamid,appid,date_added FROM wishlist WHERE date_added>0", con)
    con.close()
    ownset = set(zip(inter["steamid"].astype(int), inter["appid"].astype(int)))
    dev = set(panels["dev"])
    wl = wl[wl["steamid"].isin(dev) & wl["appid"].isin(poolset)].sort_values("date_added", ascending=False)
    tgt, prof_all = {}, {}
    for uid, gg in wl.groupby("steamid"):
        t = [int(a) for a in gg["appid"] if (int(uid), int(a)) not in ownset][:10]
        if len(t) >= 3:
            tgt[int(uid)] = set(t)
    for u, gg in rel[rel["steamid"].isin(tgt)].groupby("steamid"):
        prof_all[int(u)] = dict(zip(gg["appid"].astype(int), gg["rel"].astype(float)))

    def profw(u, ap):
        p = {a: smap.get((int(u), int(a)), 0.0) for a in ap}
        return {a: w for a, w in p.items() if w > 0} or {a: 1.0 for a in ap}

    def eval_model(fn):
        nd = []
        for u, sp in splits.items():
            rec = fn(profw(u, sp["profile"]), 20, set(sp["profile"]))
            nd.append(graded_ndcg(sp["holdout"], rec, k=20))
        wlr = []
        for u, ts in tgt.items():
            rec = fn(profw(u, prof_all.get(u, {})), 20, set(prof_all.get(u, {})))
            wlr.append(len(ts & set(rec[:20])) / len(ts))
        return nd, wlr

    nd_dae, wl_dae = eval_model(dae_rec)
    nd_ez, wl_ez = eval_model(lambda p, k, e: ease_reclist(ez, p, k, e))
    print(f"\n{'모델':16s} {'devNDCG':>8s} {'wl_recall':>9s}")
    print(f"{'Mult-DAE (신경)':16s} {np.mean(nd_dae):8.4f} {np.mean(wl_dae):9.4f}")
    print(f"{'EASE (선형)':16s} {np.mean(nd_ez):8.4f} {np.mean(wl_ez):9.4f}")
    m, lo, hi = pboot([a - b for a, b in zip(nd_dae, nd_ez)])
    print(f"  DAE - EASE [NDCG] = {m:+.4f} [{lo:+.4f},{hi:+.4f}] {'SIG' if (lo>0 or hi<0) else 'ns'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
