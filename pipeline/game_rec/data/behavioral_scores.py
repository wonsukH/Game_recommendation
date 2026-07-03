"""P4 Step 2 — pluggable behavioral preference-score candidates (the registry).

Each candidate turns the extracted tables (interactions / game_stats / user_stats)
into a graded per-(user,game) preference s>=0. The sweep harness consumes the
DataFrame contract and converts to the legacy {steamid: {appid: s}} shape at the
graph boundary (same seam as evaluation/coplay_labels.load_liked).

Contract:
    fn(inter: DataFrame, game_stats: DataFrame, user_stats: DataFrame, **params)
        -> DataFrame[steamid, appid, s]   (rows with s>0 carry signal)

Registry entries carry family/hypothesis metadata so the exploration journal can
record WHY each candidate exists. New candidates are appended round by round by
the evolutionary loop (never edit past entries' semantics — add variants).

Design notes (from the approved plan):
- per-game normalization is the unifying principle (F2P/whale/type absorbed).
- zero playtime rows -> s=0 (intent tier deliberately excluded by default).
- achievement channels: completion multiplier / within-game completion pctl /
  JOINT AFK gate. Achievement-less games stay NEUTRAL (never penalized).
- RANDOM anchor ships every round (metric health check, F2).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-9


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _pos_pctl_within(df: pd.DataFrame, value_col: str, by: str) -> pd.Series:
    """Hazen mid-rank percentile of value_col among POSITIVE values within `by`.

    Zero/negative rows get NaN (caller decides their s). Single-owner groups
    get 0.5 (uninformative middle).
    """
    pos = df[df[value_col] > 0]
    r = pos.groupby(by)[value_col].rank(method="average")
    n = pos.groupby(by)[value_col].transform("size")
    pct = (r - 0.5) / n
    out = pd.Series(np.nan, index=df.index)
    out.loc[pos.index] = pct
    return out


def _merge_game(inter: pd.DataFrame, game_stats: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return inter.merge(game_stats[["appid"] + cols], on="appid", how="left")


def _out(df: pd.DataFrame, s: pd.Series) -> pd.DataFrame:
    o = df[["steamid", "appid"]].copy()
    o["s"] = s.fillna(0.0).clip(lower=0.0).astype(np.float32)
    return o


# --------------------------------------------------------------------------
# candidates — Round 0 seeds
# --------------------------------------------------------------------------

def anchor_binary(inter, game_stats, user_stats, floor_min: float = 60.0):
    """Behavioral-binary anchor: liked = pt >= max(game positive-median, floor)."""
    d = _merge_game(inter, game_stats, ["pt_pos_median"])
    thr = np.maximum(d["pt_pos_median"].fillna(floor_min), floor_min)
    s = (d["playtime_forever"] >= thr).astype(float)
    return _out(d, s)


def pctl_game(inter, game_stats, user_stats):
    """Per-game ECDF percentile of playtime (rank-robust: whale/F2P immune)."""
    s = _pos_pctl_within(inter, "playtime_forever", "appid")
    return _out(inter, s)


def logratio_median(inter, game_stats, user_stats, cap: float = 4.0):
    """log1p(pt / game positive-median), capped — magnitude-keeping baseline."""
    d = _merge_game(inter, game_stats, ["pt_pos_median"])
    ref = d["pt_pos_median"].replace(0, np.nan)
    s = np.log1p(d["playtime_forever"] / ref).clip(upper=cap) / cap
    s[d["playtime_forever"] <= 0] = 0.0
    return _out(d, s)


def pvalue_lognorm_eb(inter, game_stats, user_stats, k_shrink: float = 20.0):
    """Upper-tail probability under per-game lognormal, EB-shrunk to global.

    s = 1 - p_upper = CDF position of the user's log-playtime in the game's
    (shrunk) lognormal — the user's original p-value seed idea.
    """
    from scipy.stats import norm

    pos = inter[inter["playtime_forever"] > 0].copy()
    pos["lg"] = np.log(pos["playtime_forever"])
    g = pos.groupby("appid")["lg"]
    mu_g, sd_g, n_g = g.mean(), g.std(ddof=0), g.size()
    mu0, sd0 = pos["lg"].mean(), pos["lg"].std(ddof=0)
    w = n_g / (n_g + k_shrink)
    mu = w * mu_g + (1 - w) * mu0
    sd = (w * sd_g.fillna(sd0) + (1 - w) * sd0).clip(lower=0.25)
    d = pos.merge(mu.rename("mu"), on="appid").merge(sd.rename("sd"), on="appid")
    z = (d["lg"] - d["mu"]) / d["sd"]
    s_pos = pd.Series(norm.cdf(z), index=d.index)
    out = inter[["steamid", "appid"]].copy()
    out["s"] = 0.0
    out.loc[pos.index, "s"] = s_pos.values
    out["s"] = out["s"].astype(np.float32)
    return out


def pctl_user(inter, game_stats, user_stats):
    """Within-user percentile of playtime (removes user scale; whale-flood control)."""
    s = _pos_pctl_within(inter, "playtime_forever", "steamid")
    return _out(inter, s)


def double_quantile(inter, game_stats, user_stats):
    """User-then-game double quantile: r1 = within-user pctl, s = within-game pctl of r1."""
    d = inter.copy()
    d["r1"] = _pos_pctl_within(d, "playtime_forever", "steamid")
    d2 = d[d["r1"].notna()].copy()
    r = d2.groupby("appid")["r1"].rank(method="average")
    n = d2.groupby("appid")["r1"].transform("size")
    s2 = (r - 0.5) / n
    out = d[["steamid", "appid"]].copy()
    out["s"] = 0.0
    out.loc[d2.index, "s"] = s2.values
    out["s"] = out["s"].astype(np.float32)
    return out


def ach_completion_mult(inter, game_stats, user_stats, gamma: float = 0.4):
    """pctl_game x bounded completion multiplier (B1): attenuates idle rows.

    eng = gamma + (1-gamma)*completion for achievement games; neutral 1 otherwise.
    """
    base = _pos_pctl_within(inter, "playtime_forever", "appid")
    has = inter["ach_total"].fillna(0) > 0
    eng = pd.Series(1.0, index=inter.index)
    eng[has] = gamma + (1 - gamma) * inter.loc[has, "completion"].fillna(0.0)
    return _out(inter, base * eng)


def ach_completion_pctl_blend(inter, game_stats, user_stats, lam: float = 0.6):
    """lam * pt-pctl + (1-lam) * within-game completion-pctl (B2, difficulty-agnostic)."""
    pt_p = _pos_pctl_within(inter, "playtime_forever", "appid")
    has = inter["ach_total"].fillna(0) > 0
    comp = inter.copy()
    comp["c"] = np.where(has, inter["completion"].fillna(0.0), np.nan)
    cpos = comp[comp["c"].notna()].copy()
    r = cpos.groupby("appid")["c"].rank(method="average")
    n = cpos.groupby("appid")["c"].transform("size")
    c_p = pd.Series(np.nan, index=comp.index)
    c_p.loc[cpos.index] = ((r - 0.5) / n).values
    s = np.where(c_p.notna(), lam * pt_p.fillna(0) + (1 - lam) * c_p.fillna(0), pt_p)
    return _out(inter, pd.Series(s, index=inter.index))


def afk_joint_gate(inter, game_stats, user_stats, hi_pctl: float = 0.8, floor: float = 0.25):
    """pctl_game x JOINT AFK downweight (A family): high pt-rank AND zero unlocks.

    Only fires on achievement-bearing games (75.7%); discount-only, never boosts.
    """
    pt_p = _pos_pctl_within(inter, "playtime_forever", "appid")
    has = inter["ach_total"].fillna(0) > 0
    suspicious = has & (inter["ach_unlocked"].fillna(0) == 0) & (pt_p >= hi_pctl)
    gate = pd.Series(1.0, index=inter.index)
    gate[suspicious] = floor
    return _out(inter, pt_p * gate)


def random_s(inter, game_stats, user_stats, seed: int = 42):
    """Weights-null probe: random s on REAL played support.

    NOT a full null — the co-play support structure stays intact, so this
    measures how much *weighting* adds over raw support (smoke01 finding)."""
    rng = np.random.default_rng(seed)
    s = pd.Series(0.0, index=inter.index)
    played = inter["playtime_forever"] > 0
    s[played] = rng.random(int(played.sum()))
    return _out(inter, s)


def random_support(inter, game_stats, user_stats, seed: int = 42):
    """TRUE null anchor (F2 metric-health): shuffle appids within each user.

    Destroys the real co-play support (library size distribution preserved) —
    if this ranks near real candidates, the metric/harness is broken."""
    rng = np.random.default_rng(seed)
    played = inter[inter["playtime_forever"] > 0]
    all_apps = played["appid"].values
    perm = rng.permutation(all_apps)  # global shuffle preserves app popularity
    out = played[["steamid"]].copy()
    out["appid"] = perm
    out["s"] = rng.random(len(out)).astype(np.float32)
    out = out.drop_duplicates(["steamid", "appid"])
    return out[["steamid", "appid", "s"]]


# --------------------------------------------------------------------------
# Round 1 candidates (hypothesis-driven from round00 findings)
# --------------------------------------------------------------------------

def comp_afk_combo(inter, game_stats, user_stats, lam: float = 0.6,
                   hi_pctl: float = 0.8, floor: float = 0.25):
    """H1: round00 1위(완료율 blend) x 3위(AFK 게이트) 결합 — 두 업적 채널 합산."""
    blend = ach_completion_pctl_blend(inter, game_stats, user_stats, lam=lam)
    pt_p = _pos_pctl_within(inter, "playtime_forever", "appid")
    has = inter["ach_total"].fillna(0) > 0
    suspicious = has & (inter["ach_unlocked"].fillna(0) == 0) & (pt_p >= hi_pctl)
    gate = pd.Series(1.0, index=inter.index)
    gate[suspicious] = floor
    blend["s"] = (blend["s"].values * gate.values).astype(np.float32)
    return blend


def resid2way_completion(inter, game_stats, user_stats, lam: float = 0.6,
                         k_user: float = 5.0):
    """H1/C-family: 완료율에서 user(완료성향)·game(난이도) 주효과 제거한 residual.

    100%-완료성향 유저의 100%는 정보 0, 대충 하는 유저의 100%는 강신호 —
    residual을 within-game pctl로 랭크해 blend."""
    has = inter["ach_total"].fillna(0) > 0
    d = inter.copy()
    d["c"] = np.where(has, d["completion"].fillna(0.0), np.nan)
    grand = d["c"].mean()
    g_mean = d.groupby("appid")["c"].transform("mean")
    u_sum = d.groupby("steamid")["c"].transform("sum")
    u_n = d.groupby("steamid")["c"].transform("count")
    u_mean_shrunk = (u_sum + k_user * grand) / (u_n + k_user)  # EB shrink
    d["resid"] = d["c"] - u_mean_shrunk - g_mean + grand
    rpos = d[d["resid"].notna()].copy()
    r = rpos.groupby("appid")["resid"].rank(method="average")
    n = rpos.groupby("appid")["resid"].transform("size")
    r_p = pd.Series(np.nan, index=d.index)
    r_p.loc[rpos.index] = ((r - 0.5) / n).values
    pt_p = _pos_pctl_within(inter, "playtime_forever", "appid")
    s = np.where(r_p.notna(), lam * pt_p.fillna(0) + (1 - lam) * r_p.fillna(0), pt_p)
    return _out(inter, pd.Series(s, index=inter.index))


def bm25_sat(inter, game_stats, user_stats, k: float = 1.0):
    """H3 탐험(rank 밖 family): BM25식 포화 s = pt/(pt + k*game_median) — 연속·유계."""
    d = _merge_game(inter, game_stats, ["pt_pos_median"])
    ref = d["pt_pos_median"].replace(0, np.nan).fillna(60.0)
    s = d["playtime_forever"] / (d["playtime_forever"] + k * ref)
    s[d["playtime_forever"] <= 0] = 0.0
    return _out(d, s)


def per_user_cap(inter, game_stats, user_stats, base: str = "pctl_game",
                 alpha: float = 0.5, lam: float = 0.6):
    """Robustness(#28, R1 winner +0.0161 SIG): per-user L1 mass cap over a base score.

    s <- s / sum_u(s) * n_lib^alpha — 파밍/whale 계정의 그래프 총 질량을 캡.
    alpha=0.5(=sqrt, R1 원형) / 0=완전 균등 / 1=캡 없음과 등가.
    base: pctl_game | blend(완료율) | double_quantile | logratio."""
    if base == "blend":
        b = ach_completion_pctl_blend(inter, game_stats, user_stats, lam=lam)
    elif base == "double_quantile":
        b = double_quantile(inter, game_stats, user_stats)
    elif base == "logratio":
        b = logratio_median(inter, game_stats, user_stats)
    elif base == "pvalue":
        b = pvalue_lognorm_eb(inter, game_stats, user_stats)
    else:
        b = pctl_game(inter, game_stats, user_stats)
    tot = b.groupby("steamid")["s"].transform("sum").replace(0, np.nan)
    n_lib = b.groupby("steamid")["s"].transform("size")
    b["s"] = (b["s"] / tot * np.power(n_lib, alpha)).fillna(0).astype(np.float32)
    return b


# --------------------------------------------------------------------------
# Round 3 — D-family (unlocktime temporal) on top of current best
# --------------------------------------------------------------------------

def pvalue_comp_blend(inter, game_stats, user_stats, lam: float = 0.6):
    """R5: 두 승자 신호 결합 — lam*pvalue + (1-lam)*완료율-pctl (S1 강화 가설)."""
    pv = pvalue_lognorm_eb(inter, game_stats, user_stats)
    has = inter["ach_total"].fillna(0) > 0
    comp = inter.copy()
    comp["c"] = np.where(has, inter["completion"].fillna(0.0), np.nan)
    cpos = comp[comp["c"].notna()].copy()
    r = cpos.groupby("appid")["c"].rank(method="average")
    n = cpos.groupby("appid")["c"].transform("size")
    c_p = pd.Series(np.nan, index=comp.index)
    c_p.loc[cpos.index] = ((r - 0.5) / n).values
    s = np.where(c_p.notna(), lam * pv["s"].values + (1 - lam) * c_p.fillna(0).values,
                 pv["s"].values)
    return _out(inter, pd.Series(s, index=inter.index))


def cap_blend_recency(inter, game_stats, user_stats, lam: float = 0.4,
                      alpha: float = 0.3, tau_days: float = 365.0, beta: float = 0.5):
    """D: unlock recency multiplier on best(cap x blend) — 최근 실진행 게임 부스트.

    anchor = 데이터 내 최신 unlocktime(재현 결정성 — wall clock 미사용)."""
    b = per_user_cap(inter, game_stats, user_stats, base="blend", alpha=alpha, lam=lam)
    anchor = float(np.nanmax(inter["unlock_last"].values))
    age_days = (anchor - inter["unlock_last"]) / 86400.0
    rec = np.exp(-age_days.clip(lower=0) / tau_days)
    mult = np.where(inter["unlock_last"].notna(), beta + (1 - beta) * rec, 1.0)
    b["s"] = (b["s"].values * mult).astype(np.float32)
    return b


def cap_blend_span(inter, game_stats, user_stats, lam: float = 0.4,
                   alpha: float = 0.3, w_span: float = 0.3):
    """D: 참여 시간폭(첫~마지막 해금, within-game pctl) 부스트 — 주말벼락 vs 장기 재방문."""
    b = per_user_cap(inter, game_stats, user_stats, base="blend", alpha=alpha, lam=lam)
    d = inter.copy()
    span = (d["unlock_last"] - d["unlock_first"]) / 86400.0
    d["sp"] = np.where(d["n_unlocks_t"].fillna(0) >= 2, span, np.nan)
    spos = d[d["sp"].notna()]
    r = spos.groupby("appid")["sp"].rank(method="average")
    n = spos.groupby("appid")["sp"].transform("size")
    sp_p = pd.Series(np.nan, index=d.index)
    sp_p.loc[spos.index] = ((r - 0.5) / n).values
    mult = 1.0 + w_span * sp_p.fillna(0.0)
    b["s"] = (b["s"].values * mult.values).astype(np.float32)
    return b


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------

def rarity_mastery_blend(inter, game_stats, user_stats, lam: float = 0.4):
    """E1 (games-크롤 후): rarity-가중 mastery — 해금 업적의 평균 surprisal
    (-ln global_pct)의 within-game pctl을 완료율 자리에 blend.

    가설: 희귀도는 코호트-독립(Steam-global)이라 완료율보다 overfit-무관 mastery 축.
    형태는 승자 blend(ach_completion_pctl_blend)와 동형 → 직접 비교 가능."""
    pt_p = _pos_pctl_within(inter, "playtime_forever", "appid").fillna(0.0)
    rs_p = _pos_pctl_within(inter, "rar_mean_surp", "appid")
    s = np.where(rs_p.notna(), lam * pt_p + (1 - lam) * rs_p.fillna(0),
                 pt_p)
    return _out(inter, pd.Series(s, index=inter.index))


def rarity_depth_blend(inter, game_stats, user_stats, lam: float = 0.4):
    """E2: 끝판-도달 depth — 해금한 가장 희귀한 업적(min global_pct)의 깊이
    (100-min_pct)의 within-game pctl을 blend. '얼마나 깊이 갔나' 단일축."""
    d = inter.copy()
    d["depth"] = np.where(d["rar_min_pct"].notna(), 100.0 - d["rar_min_pct"], np.nan)
    pt_p = _pos_pctl_within(d, "playtime_forever", "appid").fillna(0.0)
    dp_p = _pos_pctl_within(d, "depth", "appid")
    s = np.where(dp_p.notna(), lam * pt_p + (1 - lam) * dp_p.fillna(0), pt_p)
    return _out(d, pd.Series(s, index=d.index))


def pvalue_eb_intent0(inter, game_stats, user_stats, eps: float = 0.05,
                      cont_thr: float = 0.98, min_own: int = 3):
    """의도 tier ablation(#11): owned-0분을 ε 약긍정으로 — 팩블록 병합 전처리 필수.

    전처리(플랜 확정): 소유 co-occurrence 봉쇄율 cont(i,j)=cooc/min(n_i,n_j) >=
    cont_thr 인 (played i, 0분 j) 쌍 = 팩/에피소드 형제 → j의 ε 부여 제외
    (취향 신호 아닌 팩 구조물 소거). 나머지 0분 소유 = 돈 낸 의도 → s=eps.
    채택 기준: 주축(played holdout) 유의 상승 시만 — 입증 책임은 포함 쪽.
    """
    base = pvalue_lognorm_eb(inter, game_stats, user_stats)
    from scipy import sparse as sp

    own = inter[["steamid", "appid", "playtime_forever"]]
    uids = {u: i for i, u in enumerate(own["steamid"].unique())}
    aids = sorted(own["appid"].unique())
    col = {a: j for j, a in enumerate(aids)}
    X = sp.csr_matrix(
        (np.ones(len(own), np.float32),
         (own["steamid"].map(uids).values, own["appid"].map(col).values)),
        shape=(len(uids), len(aids)))
    n_own = np.asarray(X.sum(axis=0)).ravel()
    C = (X.T @ X).tocoo()
    mn = np.minimum(n_own[C.row], n_own[C.col])
    mask = ((C.data >= cont_thr * mn) & (C.row != C.col)
            & (n_own[C.row] >= min_own) & (n_own[C.col] >= min_own))
    partners: dict[int, set] = {}
    for r_, c_ in zip(C.row[mask], C.col[mask]):
        partners.setdefault(c_, set()).add(r_)

    played_by_u: dict[int, set] = {}
    for u, a, pt in own.itertuples(index=False):
        if pt > 0:
            played_by_u.setdefault(u, set()).add(col[a])

    s = base["s"].values.copy()
    zero_idx = np.where(inter["playtime_forever"].values == 0)[0]
    granted = blocked = 0
    for i in zero_idx:
        u, a = inter["steamid"].iat[i], inter["appid"].iat[i]
        j = col[a]
        sib = partners.get(j)
        if sib and sib & played_by_u.get(u, set()):
            blocked += 1
            continue
        s[i] = eps
        granted += 1
    out = base.copy()
    out["s"] = s.astype(np.float32)
    out.attrs["intent0_granted"] = granted
    out.attrs["intent0_blocked_pack"] = blocked
    return out


REGISTRY: dict[str, dict] = {
    "anchor_binary": dict(fn=anchor_binary, family="anchor", hypothesis="구 review-liked의 행동 등가물 — 그레이드가 이걸 이겨야 magnitude가 정당"),
    "random_s": dict(fn=random_s, family="anchor", hypothesis="가중치-널 프로브 — support 대비 weighting의 한계기여 측정(완전 널 아님, smoke01 발견)"),
    "random_support": dict(fn=random_support, family="anchor", hypothesis="진짜 널(F2 지표건강) — support 파괴; 진짜 후보와 붙으면 하니스 고장"),
    "pctl_game": dict(fn=pctl_game, family="rank", hypothesis="per-game 순위가 whale/F2P/타입을 전부 흡수(통일 원리) — 게이트 유력"),
    "logratio_median": dict(fn=logratio_median, family="magnitude", hypothesis="rank가 버리는 절대 몰입량이 신호일 수 있음(반대 가설 대표)"),
    "pvalue_lognorm_eb": dict(fn=pvalue_lognorm_eb, family="parametric", hypothesis="사용자 p-value seed — 분포 적합이 ECDF보다 저오너 게임에서 안정(EB shrink)"),
    "pctl_user": dict(fn=pctl_user, family="rank-user", hypothesis="유저 스케일 제거 — whale 계정의 그래프 flooding 통제"),
    "double_quantile": dict(fn=double_quantile, family="rank-double", hypothesis="유저·게임 두 confound 동시 제거(이론상 가장 깨끗, 과평탄 위험)"),
    "ach_completion_mult": dict(fn=ach_completion_mult, family="achievement-B", hypothesis="완료율 multiplier가 idle 행 감쇠 — 업적 값어치 조기 판정용"),
    "ach_completion_pctl_blend": dict(fn=ach_completion_pctl_blend, family="achievement-B", hypothesis="난이도-불변 완료율 percentile 블렌드 — 완료율의 독립 기여 측정"),
    "afk_joint_gate": dict(fn=afk_joint_gate, family="achievement-A", hypothesis="JOINT(고pt∧0해금) 다운웨이트 — 실측 7.3k 꼬리 제거의 recall 효과"),
    # ---- Round 1 (round00 발견 기반) ----
    "comp_afk_combo": dict(fn=comp_afk_combo, family="achievement-AB", hypothesis="R0 발견: 완료율(1위)과 AFK게이트(3위)가 서로 다른 행을 고침 → 결합 시 가산 리프트 가설"),
    "resid2way_completion": dict(fn=resid2way_completion, family="achievement-C", hypothesis="완료성향(유저)·난이도(게임) 주효과 제거 — 완료율 신호의 순도를 높이면 blend 리프트 증폭 가설"),
    "bm25_sat": dict(fn=bm25_sat, family="magnitude-sat", hypothesis="탐험쿼터: rank 밖 연속-포화 family — R0에서 magnitude가 죽은 게 포화 부재 탓인지 검증"),
    "per_user_cap": dict(fn=per_user_cap, family="robustness", hypothesis="탐험쿼터+#28 실증근거: 파밍/whale 계정의 그래프 질량 캡이 support 오염을 줄이는지"),
    "pvalue_comp_blend": dict(fn=pvalue_comp_blend, family="parametric-achievement", hypothesis="R5: S1(pvalue)에 유일한 유효 업적신호(완료율) 결합 — userknn에서 가산 리프트 가설"),
    # ---- Round 3 (D가족 — unlocktime) ----
    "cap_blend_recency": dict(fn=cap_blend_recency, family="temporal-D", hypothesis="최근 실진행(해금) 게임이 현재 취향을 더 예측 — best 위 recency 승수"),
    "cap_blend_span": dict(fn=cap_blend_span, family="temporal-D", hypothesis="장기 재방문(해금 시간폭)=durable 애착 — 주말벼락과 구분되면 리프트"),
    # ---- E가족 (games-크롤 완주 후, 07-04) ----
    "rarity_mastery_blend": dict(fn=rarity_mastery_blend, family="rarity-E", hypothesis="희귀도(코호트-독립)가 완료율보다 overfit-무관 mastery 신호인가 — 동형 blend 직접 비교"),
    "rarity_depth_blend": dict(fn=rarity_depth_blend, family="rarity-E", hypothesis="끝판 도달(최희귀 해금 깊이) 단일축 — 완주와 다른 '몰입 깊이' 변별 가설"),
    # ---- #11 의도 tier ablation ----
    "pvalue_eb_intent0": dict(fn=pvalue_eb_intent0, family="intent-tier", hypothesis="owned-0분=돈 낸 의도(팩블록 병합 후) ε 약긍정 — 주축 유의 상승 시만 채택(기본 제외 뒤집기, 입증책임=포함측)"),
}


def compute(name: str, inter, game_stats, user_stats, **params) -> pd.DataFrame:
    spec = REGISTRY[name]
    return spec["fn"](inter, game_stats, user_stats, **params)


def to_liked_dict(scores: pd.DataFrame, pool: set[int], min_s: float = 0.0) -> dict[str, dict[int, float]]:
    """DataFrame contract -> legacy {steamid: {appid: s}} shape, pool-filtered."""
    d = scores[(scores["s"] > min_s) & scores["appid"].isin(pool)]
    out: dict[str, dict[int, float]] = {}
    for sid, grp in d.groupby("steamid"):
        out[str(sid)] = dict(zip(grp["appid"].astype(int), grp["s"].astype(float)))
    return out
