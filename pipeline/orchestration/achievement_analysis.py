"""Phase A — 개별 업적 분석 (P4 확장, 07-07).

집계 완료율(우리가 찾은 유일한 유효 업적신호, +0.0073)을 개별 업적 신호로
대체하면 더 나은가? 업적 텍스트로 유형 분류(스토리완주/스킬/수집/멀티) + 희귀도
depth를 per-(u,g) 선호 성분으로 만들고, 각 변형을 EASE에 태워 dev NDCG(참고) +
독립 위시리스트(판정)로 비교. 공정하게: 모든 변형은 같은 playtime base와 블렌드
하고 '업적 성분'만 교체 → 순수 업적 기여 격리.

읽기 전용, dev/fresh 패널. private/OOD 미사용.
"""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from pipeline.game_rec.data import behavioral_scores as bs  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.preference_sweep import (  # noqa: E402
    build_relevance, get_panels, graded_ndcg, load_artifacts,
    split_profile_holdout)
from pipeline.orchestration.ranker_gauntlet import EaseRanker  # noqa: E402
from pipeline.orchestration.ease_recheck import ease_reclist  # noqa: E402

log = get_logger("orchestration.achievement_analysis")
rng = np.random.default_rng(13)

# ---- 업적 유형 키워드 (display_name+description 소문자 매칭, 우선순위 순) ----
SKILL = ["without taking", "no damage", "without dying", "hardest", "nightmare",
         "insane difficulty", "flawless", "perfect run", "speedrun", "in under",
         "less than", "without using", "highest difficulty", "master difficulty",
         "permadeath", "hardcore", "iron man", "deathless", "no deaths"]
STORY = ["complete the game", "finish the game", "beat the game", "story", "campaign",
         "ending", "credits", "final boss", "final chapter", "the end", "epilogue",
         "main quest", "reach the end", "complete chapter", "complete act",
         "complete all chapters", "defeat the final", "complete the main"]
MULTI = ["multiplayer", "online match", "co-op", "cooperative", "versus", "pvp",
         "win a match", "win a game", "ranked", "with a friend", "other players",
         "matchmaking", "win an online"]
COLLECT = ["collect all", "find all", "collect every", "all collectibles",
           "complete the collection", "unlock all", "100%", "find every",
           "gather all", "kill 1000", "reach level", "accumulate", "total of"]


def classify(text: str) -> str:
    t = (text or "").lower()
    for kw in SKILL:
        if kw in t:
            return "skill"
    for kw in STORY:
        if kw in t:
            return "story"
    for kw in MULTI:
        if kw in t:
            return "multi"
    for kw in COLLECT:
        if kw in t:
            return "collect"
    return "misc"


def pboot(diff, n=5000):
    diff = np.asarray([d for d in diff if np.isfinite(d)], float)
    if not len(diff):
        return (np.nan, np.nan, np.nan)
    b = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(n)]
    return float(diff.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main() -> int:
    inter, gs, us, pool = load_artifacts()
    rel = build_relevance(inter, pool)
    panels = get_panels(rel)
    poolset = set(pool)

    # 패널 유저 = train+dev+fresh (개별 업적 조인 대상 축소)
    frozen = set(panels["train"]) | set(panels["dev"]) | set(panels["private"])
    cnt = rel.groupby("steamid").size()
    fresh = [int(u) for u in cnt[cnt >= 12].index if int(u) not in frozen]
    users = sorted(set(panels["train"]) | set(panels["dev"]) | set(fresh))
    owned = inter[inter["steamid"].isin(users) & inter["appid"].isin(poolset)]
    owned_games = sorted(owned["appid"].unique().tolist())
    log.info("패널 유저 %d명, 소유 게임 %d개", len(users), len(owned_games))

    con = sqlite3.connect(REPO / "data_collection" / "steam.db")
    # 개별 업적 정의 (소유 게임에 한정) + 유형 분류
    ga = pd.read_sql_query(
        "SELECT ach_id, appid, display_name, description, global_pct "
        "FROM game_achievement WHERE global_pct IS NOT NULL", con)
    ga = ga[ga["appid"].isin(set(owned_games))].copy()
    ga["type"] = (ga["display_name"].fillna("") + " " + ga["description"].fillna("")).map(classify)
    log.info("업적 정의 %d개 유형분포: %s", len(ga),
             dict(ga["type"].value_counts()))
    ach_type = dict(zip(ga["ach_id"], ga["type"]))
    ach_pct = dict(zip(ga["ach_id"], ga["global_pct"]))
    ach_app = dict(zip(ga["ach_id"], ga["appid"]))
    # 게임별 유형별 총 업적 수
    gt = ga.groupby(["appid", "type"]).size().unstack(fill_value=0)

    # 패널 유저 해금 (개별)
    ph = ",".join(str(int(u)) for u in users)
    ua = pd.read_sql_query(
        f"SELECT steamid, ach_id FROM user_achievement WHERE steamid IN ({ph})", con)
    con.close()
    ua = ua[ua["ach_id"].isin(ach_type)].copy()
    ua["appid"] = ua["ach_id"].map(ach_app)
    ua["type"] = ua["ach_id"].map(ach_type)
    ua["gpct"] = ua["ach_id"].map(ach_pct)
    log.info("패널 해금 %d건", len(ua))

    # per-(u,g) 개별 업적 피처
    g = ua.groupby(["steamid", "appid"])
    feat = pd.DataFrame({
        "min_gpct": g["gpct"].min(),          # 가장 희귀한 해금 (작을수록 깊음)
        "rare_frac": g["gpct"].apply(lambda s: float((s < 5).mean())),  # <5% 업적 비율
        "n_story": g.apply(lambda d: int((d["type"] == "story").sum())),
        "n_skill": g.apply(lambda d: int((d["type"] == "skill").sum())),
    }).reset_index()
    # 유형별 완료율 = 유저가 딴 유형별 수 / 게임의 유형별 총수
    feat = feat.merge(gt.reset_index(), on="appid", how="left")
    feat["story_comp"] = feat["n_story"] / feat.get("story", pd.Series(0, index=feat.index)).replace(0, np.nan)
    feat["skill_comp"] = feat["n_skill"] / feat.get("skill", pd.Series(0, index=feat.index)).replace(0, np.nan)
    feat["depth"] = 100.0 - feat["min_gpct"]   # 끝판 도달 깊이

    # inter에 붙여 per-(u,g) 성분 만들기
    d = inter[inter["appid"].isin(poolset)].merge(
        feat[["steamid", "appid", "story_comp", "skill_comp", "depth", "rare_frac"]],
        on=["steamid", "appid"], how="left")

    # 성분들을 within-game 백분위로 정규화 (공정 비교)
    def wg_pct(col):
        return bs._pos_pctl_within(d.assign(_v=d[col].fillna(0)), "_v", "appid")
    pt_p = bs._pos_pctl_within(d, "playtime_forever", "appid").fillna(0.0)
    # 완료율(baseline) per-game 백분위
    has = d["ach_total"].fillna(0) > 0
    comp = np.where(has, d["completion"].fillna(0.0), np.nan)
    comp_p = bs._pos_pctl_within(d.assign(_c=pd.Series(comp, index=d.index)).assign(_c=lambda x: x["_c"]), "_c", "appid") \
        if False else None
    # 간단화: completion 백분위
    cser = pd.Series(comp, index=d.index)
    cpos = d[cser.notna() & (cser > 0)]
    comp_p = pd.Series(np.nan, index=d.index)
    if len(cpos):
        r = cser[cpos.index].groupby(d.loc[cpos.index, "appid"]).rank(method="average")
        nn = cser[cpos.index].groupby(d.loc[cpos.index, "appid"]).transform("size")
        comp_p.loc[cpos.index] = ((r - 0.5) / nn).values

    variants = {
        "base_completion": comp_p,                         # 기존 승자 성분
        "story_completion": wg_pct("story_comp"),
        "skill_completion": wg_pct("skill_comp"),
        "rarity_depth": wg_pct("depth"),
        "rare_frac": wg_pct("rare_frac"),
    }

    # ---- 평가 준비 ----
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

    LAM = 0.5

    def eval_variant(ach_p):
        # blend: LAM*pt + (1-LAM)*ach (ach 없으면 pt만)
        blended = np.where(ach_p.notna(), LAM * pt_p + (1 - LAM) * ach_p.fillna(0), pt_p)
        sc = d[["steamid", "appid"]].copy()
        sc["s"] = np.clip(blended, 0, None).astype(np.float32)
        sc = sc[sc["s"] > 0]
        smap = {(int(u), int(a)): float(s) for u, a, s in sc[["steamid", "appid", "s"]].values}
        ez = EaseRanker(sc, panels["train"], pool, lam=100.0)
        nd = []
        for u, sp in splits.items():
            prof = {a: smap.get((u, a), 0.0) for a in sp["profile"]}
            prof = {a: w for a, w in prof.items() if w > 0} or dict(sp["profile"])
            rec = ease_reclist(ez, prof, 20, set(sp["profile"]))
            nd.append(graded_ndcg(sp["holdout"], rec, k=20))
        wlr = []
        for u, ts in tgt.items():
            prof = {a: smap.get((u, a), 0.0) for a in prof_all.get(u, {})}
            prof = {a: w for a, w in prof.items() if w > 0} or prof_all.get(u, {})
            rec = ease_reclist(ez, prof, 20, set(prof_all.get(u, {})))
            wlr.append(len(ts & set(rec[:20])) / len(ts))
        return {u: v for u, v in zip(uu, nd)}, {u: v for u, v in zip(sorted(tgt), wlr)}

    res = {}
    for name, ach_p in variants.items():
        res[name] = eval_variant(ach_p)
        log.info("%s 평가 완료", name)

    print(f"\n{'변형(업적 성분)':22s} {'devNDCG':>8s} {'wl_recall':>9s}  {'vs base(wl)':>18s}")
    base_wl = res["base_completion"][1]
    for name, (nd, wlr) in res.items():
        du = sorted(set(base_wl) & set(wlr))
        m, lo, hi = pboot([wlr[u] - base_wl[u] for u in du]) if name != "base_completion" else (0, 0, 0)
        tag = "" if name == "base_completion" else f"{m:+.4f} [{lo:+.4f},{hi:+.4f}]"
        print(f"{name:22s} {np.mean(list(nd.values())):8.4f} {np.mean(list(wlr.values())):9.4f}  {tag:>18s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
