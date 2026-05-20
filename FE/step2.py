import pandas as pd
import numpy as np
import json
import argparse
from pathlib import Path
from scipy.sparse import csr_matrix, save_npz


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 2: Create Game×Tag binary matrix from steam_games_tags.csv")
    parser.add_argument(
        "--input", type=str,
        default=str(Path("outputs/steam_games_tags.csv")),
        help="Input CSV path (default: outputs/steam_games_tags.csv)"
    )
    parser.add_argument(
        "--matrix", type=str,
        default=str(Path("outputs/X_game_tag_csr.npz")),
        help="Output CSR matrix path (default: outputs/X_game_tag_csr.npz)"
    )
    parser.add_argument(
        "--indexes", type=str,
        default=str(Path("outputs/index_maps.json")),
        help="Output index maps JSON path (default: outputs/index_maps.json)"
    )
    return parser.parse_args()


def main(input_csv: str, matrix_path: str, index_path: str):
    print(f"[INFO] 입력 파일 로드: {input_csv}")
    
    # -------------------------------
    # 1. 데이터 로드
    # -------------------------------
    df = pd.read_csv(input_csv)  # appid, game_title, tags, tag_count
    
    # 태그 파싱 (NaN 안전 처리)
    def parse_tags(tags_str):
        if pd.isna(tags_str) or not tags_str:
            return []
        return [t.strip().lower() for t in str(tags_str).split(",") if t.strip()]
    
    df["tags"] = df["tags"].fillna("").apply(parse_tags)
    
    # 빈 태그 행 제거
    df = df[df["tags"].apply(len) > 0].reset_index(drop=True)
    
    print(f"[INFO] 처리할 게임 수: {len(df):,}개")
    
    # -------------------------------
    # 2. 태그 vocabulary 만들기
    # -------------------------------
    all_tags = sorted({tag for tags in df["tags"] for tag in tags})
    tag2idx = {tag: i for i, tag in enumerate(all_tags)}
    idx2tag = {i: tag for tag, i in tag2idx.items()}
    
    print(f"[INFO] 고유 태그 수: {len(all_tags):,}개")
    
    # -------------------------------
    # 3. 게임 인덱스 만들기
    # -------------------------------
    games = df["appid"].unique()
    appid2row = {int(appid): i for i, appid in enumerate(games)}
    row2appid = {i: int(appid) for appid, i in appid2row.items()}
    
    print(f"[INFO] 고유 게임 수: {len(games):,}개")
    
    # -------------------------------
    # 4. 행렬 좌표 만들기 (게임-태그 관계)
    # -------------------------------
    rows, cols, data = [], [], []
    for _, row in df.iterrows():
        g = appid2row[row["appid"]]
        for t in row["tags"]:
            if t in tag2idx:  # 안전 체크
                rows.append(g)
                cols.append(tag2idx[t])
                data.append(1)
    
    print(f"[INFO] 게임-태그 관계 수: {len(data):,}개")
    
    # -------------------------------
    # 5. CSR 행렬로 변환
    # -------------------------------
    X = csr_matrix((data, (rows, cols)), shape=(len(games), len(all_tags)), dtype=np.int8)
    
    # -------------------------------
    # 6. 저장
    # -------------------------------
    # 출력 폴더 생성
    Path(matrix_path).parent.mkdir(parents=True, exist_ok=True)
    Path(index_path).parent.mkdir(parents=True, exist_ok=True)
    
    save_npz(matrix_path, X)
    
    index_maps = {
        "appid2row": appid2row,
        "row2appid": row2appid,
        "tag2idx": tag2idx,
        "idx2tag": idx2tag,
        "matrix_shape": X.shape,
        "total_relations": len(data)
    }
    
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_maps, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 저장 완료:")
    print(f"   - CSR 행렬: {matrix_path}")
    print(f"   - 인덱스 맵: {index_path}")
    print(f"   - 행렬 크기: {X.shape}")
    print(f"   - 밀도: {X.nnz / (X.shape[0] * X.shape[1]):.4f}")


if __name__ == "__main__":
    args = _parse_args()
    main(args.input, args.matrix, args.indexes)
