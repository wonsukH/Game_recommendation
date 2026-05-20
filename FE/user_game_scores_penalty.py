"""
user_game_score_with_penalty.py

입력 기본: <이 파일과 같은 폴더>/user_game_matrix.csv
출력 기본: <이 파일과 같은 폴더>/outputs/user_game_scores.csv

입력 컬럼(필수):
  - appid, steamid, voted_up, playtime_forever

출력 컬럼:
  - appid, steamid, voted_up, playtime_forever
  - ptile         : 각 게임 내 percent-rank (0~1)
  - s_round10     : round(ptile*10) → 0~10 (정수)
  - vote_factor   : 추천/비추천 가중 계수(설명용)
  - s_round10_rec : s_round10 * vote_factor (0~10로 clip)
                   ↳ 이제 '추천 보너스 + 비추천 패널티' 모두 반영된 점수!
설정:
  - ALPHA10_POS : 추천 보너스 세기(기본 0.3)
  - ALPHA10_NEG : 비추천 패널티 세기(기본 0.5)
  - PENALTY_MODE: 'fixed' or 'linear' (기본 'linear')
      * fixed : 추천 → ×(1+α_pos), 비추천 → ×(1-α_neg)
      * linear: 추천 → ×(1+α_pos),
                비추천 → ×(1-α_neg * (s_round10/10))  # 오래했는데 비추면 더 크게 깎음
"""

from pathlib import Path
import os
import pandas as pd
import numpy as np

# =========================== CONFIG ===========================
SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_CSV  = Path(os.getenv("UGS_INPUT",   SCRIPT_DIR / "user_game_matrix.csv"))
OUTPUT_CSV = Path(os.getenv("UGS_OUTPUT",  SCRIPT_DIR / "outputs" / "user_game_scores.csv"))

ALPHA10_POS = float(os.getenv("UGS_ALPHA10_POS", "0.3"))  # 추천(👍) 보너스 강도
ALPHA10_NEG = float(os.getenv("UGS_ALPHA10_NEG", "0.5"))  # 비추천(👎) 패널티 강도
PENALTY_MODE = os.getenv("UGS_PENALTY_MODE", "linear").strip().lower()  # 'fixed' | 'linear'
# ==============================================================


def _coerce_voted_up(col: pd.Series) -> pd.Series:
    """voted_up을 0/1 정수로 강건하게 변환"""
    def _to01(x):
        if isinstance(x, str):
            s = x.strip().lower()
            if s in ("1","true","t","y","yes"):
                return 1
            return 0
        return int(bool(x))
    return col.apply(_to01).astype(int)


def compute_user_game_scores_round10(df_game: pd.DataFrame,
                                     alpha_pos: float = 0.3,
                                     alpha_neg: float = 0.5,
                                     penalty_mode: str = "linear") -> pd.DataFrame:
    """
    - 각 appid 내 percent-rank(ptile) = (rank-1)/(n-1), n=1이면 1.0
    - 분위수 점수: round(ptile*10) -> 0~10 (정수)
    - 추천/비추천 가중:
        fixed :  factor = 1 + alpha_pos*voted_up - alpha_neg*(1-voted_up)
        linear: factor = 1 + alpha_pos*voted_up - alpha_neg*(1-voted_up)*(s_round10/10)
      최종: s_round10_rec = clip( s_round10 * factor, 0, 10 )
    """
    df = df_game.copy()

    # voted_up 정규화
    df["voted_up"] = _coerce_voted_up(df["voted_up"])

    # 각 게임 내 rank 및 개수
    df["_rank"] = df.groupby("appid")["playtime_forever"].rank(method="average")
    df["_cnt"]  = df.groupby("appid")["playtime_forever"].transform("count")

    # percent-rank: (rank-1)/(n-1), n=1이면 1.0
    denom = (df["_cnt"] - 1)
    df["ptile"] = 0.0
    mask = denom > 0
    df.loc[mask, "ptile"] = (df.loc[mask, "_rank"] - 1) / denom[mask]
    df.loc[~mask, "ptile"] = 1.0

    # 0~10 반올림 점수
    df["s_round10"] = np.rint(df["ptile"] * 10).astype(int).clip(0, 10)

    # 추천/비추천 가중 계수 계산
    voted_up = df["voted_up"].values
    s10 = df["s_round10"].astype(float).values
    if penalty_mode == "fixed":
        # 추천: ×(1+α_pos), 비추천: ×(1-α_neg)
        vote_factor = 1.0 + alpha_pos * voted_up - alpha_neg * (1 - voted_up)
    else:
        # linear(기본): 비추천 패널티를 플레이타임 점수에 비례해 더 크게
        vote_factor = 1.0 + alpha_pos * voted_up - alpha_neg * (1 - voted_up) * (s10 / 10.0)

    # 하한 0으로 안전 클립 (음수 방지)
    vote_factor = np.maximum(vote_factor, 0.0)

    # 최종 점수(0~10)
    df["vote_factor"] = vote_factor
    df["s_round10_rec"] = np.clip(s10 * vote_factor, 0.0, 10.0)

    out = df[[
        "appid","steamid","voted_up","playtime_forever",
        "ptile","s_round10","vote_factor","s_round10_rec"
    ]].copy()

    # 임시 컬럼 제거
    df.drop(columns=["_rank","_cnt"], inplace=True, errors="ignore")

    return out


def main():
    # 입력 확인
    if not INPUT_CSV.exists():
        print(f"[ERROR] 입력 CSV가 없습니다: {INPUT_CSV}")
        print("→ INPUT_CSV 경로를 수정하거나, 환경변수 UGS_INPUT 로 지정하세요.")
        return

    # 출력 폴더 생성
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] 입력 로드: {INPUT_CSV}")
    df = pd.read_csv(INPUT_CSV)

    # 필수 컬럼 확인
    required = {"appid","steamid","voted_up","playtime_forever"}
    missing = list(required - set(df.columns))
    if missing:
        print(f"[ERROR] 입력 CSV에 다음 컬럼이 없습니다: {missing}")
        return

    print(f"[INFO] 행 개수: {len(df):,}")
    print(f"[INFO] s(u,g) 계산 ...  (ALPHA10_POS={ALPHA10_POS}, ALPHA10_NEG={ALPHA10_NEG}, MODE={PENALTY_MODE})")
    df_score = compute_user_game_scores_round10(
        df, alpha_pos=ALPHA10_POS, alpha_neg=ALPHA10_NEG, penalty_mode=PENALTY_MODE
    )

    df_score.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"[INFO] 저장 완료: {OUTPUT_CSV} (rows={len(df_score):,})")
    try:
        print(df_score.head(10).to_string(index=False))
        print("\n[INFO] s_round10_rec 통계:")
        print(df_score["s_round10_rec"].describe())
    except Exception:
        pass


if __name__ == "__main__":
    main()
