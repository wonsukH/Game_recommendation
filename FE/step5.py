import pandas as pd
import numpy as np
import argparse
from pathlib import Path
from scipy.sparse import csr_matrix, load_npz
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
import json


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 5: Ridge regression to learn tag effects β")
    parser.add_argument(
        "--matrix", type=str,
        default=str(Path("outputs/X_game_tag_csr.npz")),
        help="Input CSR matrix path (default: outputs/X_game_tag_csr.npz)"
    )
    parser.add_argument(
        "--indexes", type=str,
        default=str(Path("outputs/index_maps.json")),
        help="Input index maps JSON path (default: outputs/index_maps.json)"
    )
    parser.add_argument(
        "--scores", type=str,
        default=str(Path("outputs/user_game_scores.csv")),
        help="Input game scores CSV path (default: outputs/user_game_scores.csv)"
    )
    parser.add_argument(
        "--score-col", type=str,
        default="s_round10_rec",
        help="Score column to use (default: s_round10_rec)"
    )
    parser.add_argument(
        "--alpha", type=float,
        default=1.0,
        help="Ridge regularization strength (default: 1.0)"
    )
    parser.add_argument(
        "--output", type=str,
        default=str(Path("outputs/tag_beta.npy")),
        help="Output tag beta coefficients path (default: outputs/tag_beta.npy)"
    )
    parser.add_argument(
        "--stats", type=str,
        default=str(Path("outputs/tag_beta_stats.json")),
        help="Output statistics JSON path (default: outputs/tag_beta_stats.json)"
    )
    return parser.parse_args()


def prepare_regression_data(X: csr_matrix, scores_df: pd.DataFrame, 
                          row2appid: dict, score_col: str) -> tuple:
    """
    회귀 분석을 위한 데이터 준비
    
    Args:
        X: 게임×태그 행렬
        scores_df: 게임 점수 데이터프레임
        row2appid: 행 인덱스 → appid 매핑
        score_col: 점수 컬럼명
    
    Returns:
        (X_reg, y_reg): 회귀용 특성 행렬과 타겟 벡터
    """
    print("[INFO] 회귀 데이터 준비 중...")
    
    # 게임별 평균 점수 계산
    game_scores = scores_df.groupby('appid')[score_col].mean().reset_index()
    game_scores = game_scores.sort_values('appid')
    
    # CSR 행렬의 게임 순서에 맞춰 점수 정렬
    y_reg = []
    valid_indices = []
    
    for i in range(X.shape[0]):
        game_id = row2appid[i]
        game_score = game_scores[game_scores['appid'] == game_id]
        
        if len(game_score) > 0:
            y_reg.append(game_score[score_col].iloc[0])
            valid_indices.append(i)
        else:
            # 점수가 없는 게임은 제외
            continue
    
    # 유효한 게임들만 선택
    X_reg = X[valid_indices, :]
    y_reg = np.array(y_reg)
    
    print(f"[INFO] 회귀 데이터 크기:")
    print(f"   - 특성 행렬: {X_reg.shape}")
    print(f"   - 타겟 벡터: {y_reg.shape}")
    print(f"   - 유효한 게임 수: {len(valid_indices)}")
    
    return X_reg, y_reg


def main(matrix_path: str, index_path: str, scores_path: str, score_col: str, 
         alpha: float, output_path: str, stats_path: str):
    print(f"[INFO] 입력 파일 로드:")
    print(f"   - CSR 행렬: {matrix_path}")
    print(f"   - 인덱스 맵: {index_path}")
    print(f"   - 게임 점수: {scores_path}")
    print(f"   - 점수 컬럼: {score_col}")
    print(f"   - Ridge alpha: {alpha}")
    
    # 데이터 로드
    X = load_npz(matrix_path)
    scores_df = pd.read_csv(scores_path)
    
    with open(index_path, 'r', encoding='utf-8') as f:
        index_maps = json.load(f)
    
    tag2idx = index_maps['tag2idx']
    idx2tag = {int(k): v for k, v in index_maps['idx2tag'].items()}
    row2appid = {int(k): v for k, v in index_maps['row2appid'].items()}
    
    print(f"[INFO] 데이터 크기:")
    print(f"   - 게임×태그 행렬: {X.shape}")
    print(f"   - 점수 데이터: {len(scores_df):,}개 행")
    print(f"   - 태그 수: {len(tag2idx)}")
    
    # 점수 컬럼 확인
    if score_col not in scores_df.columns:
        available_cols = [col for col in scores_df.columns if 'score' in col.lower() or 's_' in col]
        print(f"[ERROR] 점수 컬럼 '{score_col}'을 찾을 수 없습니다.")
        print(f"[INFO] 사용 가능한 컬럼: {available_cols}")
        return
    
    # 회귀 데이터 준비
    X_reg, y_reg = prepare_regression_data(X, scores_df, row2appid, score_col)
    
    # 특성 스케일링 (희소 행렬이므로 표준화)
    print("[INFO] 특성 스케일링 중...")
    scaler = StandardScaler(with_mean=False)  # 희소 행렬이므로 평균 제거 안함
    X_scaled = scaler.fit_transform(X_reg)
    
    # Ridge 회귀 학습
    print(f"[INFO] Ridge 회귀 학습 중 (alpha={alpha})...")
    ridge = Ridge(alpha=alpha, random_state=42)
    ridge.fit(X_scaled, y_reg)
    
    # 태그 효과 추출
    tag_beta = ridge.coef_
    
    print(f"[INFO] Ridge 회귀 결과:")
    print(f"   - R² 점수: {ridge.score(X_scaled, y_reg):.4f}")
    print(f"   - 절편: {ridge.intercept_:.4f}")
    print(f"   - 계수 개수: {len(tag_beta)}")
    print(f"   - 최대 계수: {tag_beta.max():.4f}")
    print(f"   - 최소 계수: {tag_beta.min():.4f}")
    print(f"   - 평균 계수: {tag_beta.mean():.4f}")
    print(f"   - 계수 표준편차: {tag_beta.std():.4f}")
    
    # 출력 폴더 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(stats_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 태그 효과 저장
    np.save(output_path, tag_beta)
    
    # 통계 정보 저장
    stats = {
        "regression_info": {
            "r2_score": float(ridge.score(X_scaled, y_reg)),
            "intercept": float(ridge.intercept_),
            "num_coefficients": len(tag_beta)
        },
        "coefficient_stats": {
            "max": float(tag_beta.max()),
            "min": float(tag_beta.min()),
            "mean": float(tag_beta.mean()),
            "std": float(tag_beta.std())
        },
        "parameters": {
            "alpha": alpha,
            "score_column": score_col,
            "random_state": 42
        },
        "data_info": {
            "num_games": X_reg.shape[0],
            "num_tags": X_reg.shape[1],
            "target_stats": {
                "mean": float(y_reg.mean()),
                "std": float(y_reg.std()),
                "min": float(y_reg.min()),
                "max": float(y_reg.max())
            }
        }
    }
    
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 저장 완료:")
    print(f"   - 태그 효과: {output_path}")
    print(f"   - 통계 정보: {stats_path}")
    print(f"   - 계수 크기: {tag_beta.shape}")
    
    # 상위/하위 태그 효과 확인
    print(f"\n[INFO] 태그 효과 상위 10개:")
    top_indices = np.argsort(tag_beta)[-10:][::-1]
    for i, idx in enumerate(top_indices):
        tag_name = idx2tag[idx]
        beta_val = tag_beta[idx]
        print(f"   {i+1:2d}. {tag_name:20s}: {beta_val:8.4f}")
    
    print(f"\n[INFO] 태그 효과 하위 10개:")
    bottom_indices = np.argsort(tag_beta)[:10]
    for i, idx in enumerate(bottom_indices):
        tag_name = idx2tag[idx]
        beta_val = tag_beta[idx]
        print(f"   {i+1:2d}. {tag_name:20s}: {beta_val:8.4f}")


if __name__ == "__main__":
    args = _parse_args()
    main(args.matrix, args.indexes, args.scores, args.score_col, 
         args.alpha, args.output, args.stats)
