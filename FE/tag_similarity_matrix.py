import pandas as pd
from pathlib import Path
import argparse
from sklearn.metrics.pairwise import cosine_similarity

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute cosine similarity between game tags from user scores")
    parser.add_argument(
        "--scores", type=str,
        default=str(PROJECT_ROOT / "outputs" / "user_game_scores.csv"),
        help="Path to user_game_scores CSV (default: outputs/user_game_scores.csv)"
    )
    parser.add_argument(
        "--tags", type=str,
        default=str(PROJECT_ROOT / "outputs" / "steam_games_tags.csv"),
        help="Path to steam_games_tags CSV (default: outputs/steam_games_tags.csv)"
    )
    parser.add_argument(
        "-o", "--output", type=str,
        default=str(PROJECT_ROOT / "outputs" / "tag_similarity_cosine.csv"),
        help="Output path for similarity CSV (default: outputs/tag_similarity_cosine.csv)"
    )
    return parser.parse_args()


args = _parse_args()

# --- 데이터 불러오기 ---
df_scores = pd.read_csv(args.scores)  # columns include: appid, steamid, s_round10_rec
df_tags = pd.read_csv(args.tags)      # columns include: appid, game_title, tags

# 태그 explode (NaN 안전 처리, 공백 제거)
tags_series = df_tags["tags"].fillna("").astype(str).str.replace(";", ",")
df_tags = df_tags.assign(tag=tags_series.str.split(",")).explode("tag")
df_tags["tag"] = df_tags["tag"].astype(str).str.strip()
df_tags = df_tags[df_tags["tag"] != ""]

# 유저-태그 점수 매트릭스 생성
value_col = "s_round10_rec" if "s_round10_rec" in df_scores.columns else (
    "game_score" if "game_score" in df_scores.columns else None
)
if value_col is None:
    raise ValueError("점수 컬럼을 찾을 수 없습니다. 's_round10_rec' 또는 'game_score'가 필요합니다.")

df = df_scores.merge(df_tags[["appid", "tag"]], on="appid", how="inner")
user_tag_matrix = df.pivot_table(index="steamid", columns="tag", values=value_col, aggfunc="sum", fill_value=0)

# --- 코사인 유사도 계산 ---
tags = user_tag_matrix.columns
similarity_matrix = cosine_similarity(user_tag_matrix.T)   # 태그 간 유사도 (전치해서 tag 기준으로)
similarity_df = pd.DataFrame(similarity_matrix, index=tags, columns=tags)

# 저장
out_path = Path(args.output)
out_path.parent.mkdir(parents=True, exist_ok=True)
similarity_df.to_csv(out_path)
print(f"✅ 저장 완료: {out_path}")
