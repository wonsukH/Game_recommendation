"""Phase B2 — 업적-피처 신경 랭커 (P4 확장, 07-07).

개별 업적이 학습형 랭커 위에서 이득을 주나? 업적 콘텐츠를 두 갈래로 투입:
  · 유저 업적스타일(소유 게임 해금에서): 완료성향·희귀도추구·스토리/스킬 성향
  · 아이템 업적프로파일(후보 게임에서, 비소유도 가능): 난이도분포·유형믹스
CF 기반점수(EASE) + 이 콘텐츠 피처를 torch MLP로 학습 → EASE 대비 dev NDCG +
독립 위시리스트. 정직한 기대: 앞선 학습형 리랭커가 음성이었고 EASE가 압도라
기대 낮음 — 개별 업적 콘텐츠가 그걸 뒤집는지 직접 시험. torch CPU.
"""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    build_relevance, get_panels, graded_ndcg, load_artifacts,
    split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import EaseRanker  # noqa: E402
from pipeline.orchestration.ease_recheck import ease_reclist  # noqa: E402
from pipeline.orchestration.achievement_analysis import classify  # noqa: E402

log = get_logger("orchestration.dl_ach_ranker")
torch.manual_seed(0)
rng = np.random.default_rng(31)


def ease_score_vec(ez, profile):
    x = np.zeros(len(ez.items))
    for a, w in profile.items():
        j = ez.col.get(int(a))
        if j is not None:
            x[j] = w
    if x.sum() == 0:
        return None
    xXt = ez.X @ x
    return x - ((x - xXt @ ez.V) / ez.lam) / ez.diagP


def pboot(diff, n=5000):
    diff = np.asarray([d for d in diff if np.isfinite(d)], float)
    b = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(n)]
    return float(diff.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


class MLP(nn.Module):
    def __init__(self, d, h=64):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d, h), nn.ReLU(), nn.Linear(h, h), nn.ReLU(), nn.Linear(h, 1))

    def forward(self, x):
        return self.net(x).squeeze(-1)


def main() -> int:
    inter, gs, us, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    poolset = set(pool)
    lib = inter.groupby("steamid").size().to_dict()

    ez = EaseRanker(bs.compute("pvalue_lognorm_eb", inter, gs, us), panels["train"], pool, lam=100.0)
    items = ez.items
    i_pop = np.asarray((ez.X > 0).sum(axis=0)).ravel().astype(float) if hasattr(ez, "X") else None
    # 인기 백분위 (train 소유수 기반)
    tr_played = inter[(inter["playtime_forever"] > 0) & inter["steamid"].isin(set(panels["train"]))]
    powner = tr_played.groupby("appid").size()
    pop_pct = pd.Series(powner.reindex(items).fillna(0).rank(pct=True).values, index=items).to_dict()

    # ---- 업적 콘텐츠 (아이템 프로파일 + 유저 스타일) ----
    con = sqlite3.connect(REPO / "data_collection" / "steam.db")
    ga = pd.read_sql_query("SELECT ach_id, appid, display_name, description, global_pct "
                           "FROM game_achievement WHERE global_pct IS NOT NULL", con)
    ga = ga[ga["appid"].isin(poolset)].copy()
    ga["type"] = (ga["display_name"].fillna("") + " " + ga["description"].fillna("")).map(classify)
    # 아이템 프로파일 (모든 업적 있는 게임)
    prof_rows = []
    for a, d in ga.groupby("appid"):
        n = len(d); vc = d["type"].value_counts()
        prof_rows.append((int(a), d["global_pct"].median(), float((d["global_pct"] < 5).mean()),
                          vc.get("story", 0) / n, vc.get("skill", 0) / n, vc.get("multi", 0) / n, n))
    iprof = pd.DataFrame(prof_rows, columns=["appid", "med_gpct", "rarefrac", "story_sh", "skill_sh", "multi_sh", "n_ach"]).set_index("appid")
    ach_type = dict(zip(ga["ach_id"], ga["type"])); ach_app = dict(zip(ga["ach_id"], ga["appid"])); ach_pct = dict(zip(ga["ach_id"], ga["global_pct"]))

    users = sorted(set(panels["train"]) | set(panels["dev"]) |
                   {int(u) for u in rel.groupby("steamid").size().index})
    ph = ",".join(str(int(u)) for u in users)
    ua = pd.read_sql_query(f"SELECT steamid, ach_id FROM user_achievement WHERE steamid IN ({ph})", con)
    con.close()
    ua = ua[ua["ach_id"].isin(ach_type)].copy()
    ua["appid"] = ua["ach_id"].map(ach_app); ua["type"] = ua["ach_id"].map(ach_type); ua["gpct"] = ua["ach_id"].map(ach_pct)
    # 유저 스타일 (소유 게임 해금 요약)
    style = {}
    for u, d in ua.groupby("steamid"):
        gp = d["gpct"]
        style[int(u)] = np.array([
            float((gp < 5).mean()),                 # 희귀 추구
            float((100 - gp.min()) / 100),          # 최고 깊이
            float((d["type"] == "story").mean()),   # 스토리 성향
            float((d["type"] == "skill").mean()),   # 스킬 성향
            float(len(d) / max(1, d["appid"].nunique())),  # 게임당 해금 밀도
        ], dtype=np.float32)
    STYLE_D = 5
    def user_style(u):
        return style.get(int(u), np.zeros(STYLE_D, np.float32))
    IPROF_COLS = ["med_gpct", "rarefrac", "story_sh", "skill_sh", "multi_sh", "n_ach"]
    iprof_norm = iprof.copy()
    iprof_norm["med_gpct"] = iprof_norm["med_gpct"] / 100.0
    iprof_norm["n_ach"] = np.log1p(iprof_norm["n_ach"]) / 6.0
    iprof_map = {int(a): row.values.astype(np.float32) for a, row in iprof_norm[IPROF_COLS].iterrows()}
    IPROF_D = len(IPROF_COLS)
    zero_ip = np.zeros(IPROF_D, np.float32)

    def feats(u, cand_ids, escore):
        us_ = user_style(u)
        rows = []
        for a in cand_ids:
            j = ez.col.get(int(a))
            es = escore[j] if j is not None else 0.0
            ip = iprof_map.get(int(a), zero_ip)
            rows.append(np.concatenate([[es, pop_pct.get(int(a), 0.0), np.log1p(lib.get(int(u), 1)) / 8.0], us_, ip]))
        return np.array(rows, dtype=np.float32)

    def profw(u, ap):
        smap = ez  # placeholder
        p = {a: 1.0 for a in ap}
        return p

    # smap for profile weights (pvalue s)
    sc = bs.compute("pvalue_lognorm_eb", inter, gs, us)
    smap = {(int(u), int(a)): float(s) for u, a, s in sc[sc["s"] > 0][["steamid", "appid", "s"]].values}
    def prof_of(u, ap):
        p = {a: smap.get((int(u), int(a)), 0.0) for a in ap}
        return {a: w for a, w in p.items() if w > 0} or {a: 1.0 for a in ap}

    # ---- 학습 데이터 (train 유저) ----
    tr_splits = split_profile_holdout(rel, panels["train"], seed=1)
    Xtr, ytr = [], []
    for u, sp in tr_splits.items():
        prof = prof_of(u, sp["profile"])
        esc = ease_score_vec(ez, prof)
        if esc is None:
            continue
        excl = set(sp["profile"])
        cand = [int(items[j]) for j in np.argsort(-esc)[:80] if int(items[j]) not in excl]
        pos = [a for a in sp["holdout"] if a in ez.col and a not in excl]
        cand = sorted(set(cand) | set(pos))
        if not cand:
            continue
        Xtr.append(feats(u, cand, esc))
        ytr.append(np.array([sp["holdout"].get(int(a), 0.0) for a in cand], np.float32))
    Xtr = np.vstack(Xtr); ytr = np.concatenate(ytr)
    log.info("학습행 %d (%.1f%% 양성), 피처 %d", len(ytr), 100 * (ytr > 0).mean(), Xtr.shape[1])
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    Xn = torch.tensor((Xtr - mu) / sd); yt = torch.tensor(ytr)
    model = MLP(Xtr.shape[1]); opt = torch.optim.Adam(model.parameters(), lr=2e-3, weight_decay=1e-4)
    model.train()
    for ep in range(120):
        perm = torch.randperm(len(yt))
        for s0 in range(0, len(yt), 4096):
            idx = perm[s0:s0 + 4096]
            pred = model(Xn[idx]); loss = ((pred - yt[idx]) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
    model.eval()
    log.info("MLP 학습 완료 loss=%.4f", float(loss))

    def rerank(u, prof, k, excl):
        esc = ease_score_vec(ez, prof)
        if esc is None:
            return []
        cand = np.array([int(items[j]) for j in np.argsort(-esc)[:120] if int(items[j]) not in excl])
        with torch.no_grad():
            pr = model(torch.tensor((feats(u, cand, esc) - mu) / sd)).numpy()
        return [int(cand[i]) for i in np.argsort(-pr)[:k]]

    # ---- 평가 ----
    splits = split_profile_holdout(rel, panels["dev"], seed=42)
    con = sqlite3.connect(REPO / "data_collection" / "steam.db")
    wl = pd.read_sql_query("SELECT steamid,appid,date_added FROM wishlist WHERE date_added>0", con); con.close()
    ownset = set(zip(inter["steamid"].astype(int), inter["appid"].astype(int)))
    dev = set(panels["dev"]); wl = wl[wl["steamid"].isin(dev) & wl["appid"].isin(poolset)].sort_values("date_added", ascending=False)
    tgt, prof_all = {}, {}
    for uid, gg in wl.groupby("steamid"):
        t = [int(a) for a in gg["appid"] if (int(uid), int(a)) not in ownset][:10]
        if len(t) >= 3:
            tgt[int(uid)] = set(t)
    for u, gg in rel[rel["steamid"].isin(tgt)].groupby("steamid"):
        prof_all[int(u)] = dict(zip(gg["appid"].astype(int), gg["rel"].astype(float)))

    def eval_fn(fn):
        nd = [graded_ndcg(sp["holdout"], fn(u, prof_of(u, sp["profile"]), 20, set(sp["profile"])), k=20) for u, sp in splits.items()]
        wlr = [len(ts & set(fn(u, prof_of(u, prof_all.get(u, {})), 20, set(prof_all.get(u, {})))[:20])) / len(ts) for u, ts in tgt.items()]
        return nd, wlr
    nd_r, wl_r = eval_fn(rerank)
    nd_e, wl_e = eval_fn(lambda u, p, k, e: ease_reclist(ez, p, k, e))
    print(f"\n{'모델':22s} {'devNDCG':>8s} {'wl_recall':>9s}")
    print(f"{'업적-신경 리랭커':22s} {np.mean(nd_r):8.4f} {np.mean(wl_r):9.4f}")
    print(f"{'EASE (기준)':22s} {np.mean(nd_e):8.4f} {np.mean(wl_e):9.4f}")
    m, lo, hi = pboot([a - b for a, b in zip(nd_r, nd_e)])
    print(f"  리랭커 - EASE [NDCG] = {m:+.4f} [{lo:+.4f},{hi:+.4f}] {'SIG' if (lo>0 or hi<0) else 'ns'}")
    mw, lw, hw = pboot([a - b for a, b in zip(wl_r, wl_e)])
    print(f"  리랭커 - EASE [wishlist] = {mw:+.4f} [{lw:+.4f},{hw:+.4f}] {'SIG' if (lw>0 or hw<0) else 'ns'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
