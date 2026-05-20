import pandas as pd
import numpy as np
import argparse
from pathlib import Path
from sklearn.preprocessing import MinMaxScaler


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 3: Normalize game scores with min-max and gamma correction")
    parser.add_argument(
        "--input", type=str,
        default=str(Path("outputs/user_game_scores.csv")),
        help="Input CSV path (default: outputs/user_game_scores.csv)"
    )
    parser.add_argument(
        "--score-col", type=str,
        default="s_round10_rec",
        help="Score column to normalize (default: s_round10_rec)"
    )
    parser.add_argument(
        "--gamma", type=float,
        default=0.5,
        help="Gamma correction value (default: 0.5)"
    )
    parser.add_argument(
        "--output", type=str,
        default=str(Path("outputs/game_weight.npy")),
        help="Output numpy array path (default: outputs/game_weight.npy)"
    )
    parser.add_argument(
        "--stats", type=str,
        default=str(Path("outputs/game_weight_stats.json")),
        help="Output statistics JSON path (default: outputs/game_weight_stats.json)"
    )
    return parser.parse_args()


def normalize_scores(scores: np.ndarray, gamma: float = 0.5) -> np.ndarray:
    """
    Min-max 정규화 + gamma 보정으로 [0,1] 범위로 변환
    
    Args:
        scores: 원본 점수 배열
        gamma: gamma 보정 값 (0.5 = 제곱근, 1.0 = 선형, 2.0 = 제곱)
    
    Returns:
        정규화된 점수 배열 [0,1]
    """
    # Min-max 정규화
    scaler = MinMaxScaler()
    scores_norm = scaler.fit_transform(scores.reshape(-1, 1)).flatten()
    
    # Gamma 보정
    scores_gamma = np.power(scores_norm, gamma)
    
    return scores_gamma


def main(input_csv: str, score_col: str, gamma: float, output_path: str, stats_path: str):
    print(f"[INFO] 입력 파일 로드: {input_csv}")
    print(f"[INFO] 점수 컬럼: {score_col}")
    print(f"[INFO] Gamma 값: {gamma}")
    
    # 데이터 로드
    df = pd.read_csv(input_csv)
    
    # 점수 컬럼 확인
    if score_col not in df.columns:
        available_cols = [col for col in df.columns if 'score' in col.lower() or 's_' in col]
        print(f"[ERROR] 점수 컬럼 '{score_col}'을 찾을 수 없습니다.")
        print(f"[INFO] 사용 가능한 컬럼: {available_cols}")
        return
    
    # 게임별 평균 점수 계산
    game_scores = df.groupby('appid')[score_col].mean().reset_index()
    game_scores = game_scores.sort_values('appid')
    
    print(f"[INFO] 게임 수: {len(game_scores):,}개")
    print(f"[INFO] 원본 점수 통계:")
    print(f"   - 최소값: {game_scores[score_col].min():.4f}")
    print(f"   - 최대값: {game_scores[score_col].max():.4f}")
    print(f"   - 평균값: {game_scores[score_col].mean():.4f}")
    print(f"   - 표준편차: {game_scores[score_col].std():.4f}")
    
    # 정규화
    scores_array = game_scores[score_col].values
    normalized_scores = normalize_scores(scores_array, gamma)
    
    print(f"[INFO] 정규화 후 통계:")
    print(f"   - 최소값: {normalized_scores.min():.4f}")
    print(f"   - 최대값: {normalized_scores.max():.4f}")
    print(f"   - 평균값: {normalized_scores.mean():.4f}")
    print(f"   - 표준편차: {normalized_scores.std():.4f}")
    
    # 출력 폴더 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(stats_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 저장
    np.save(output_path, normalized_scores)
    
    # 통계 정보 저장
    import json
    stats = {
        "original_stats": {
            "min": float(game_scores[score_col].min()),
            "max": float(game_scores[score_col].max()),
            "mean": float(game_scores[score_col].mean()),
            "std": float(game_scores[score_col].std())
        },
        "normalized_stats": {
            "min": float(normalized_scores.min()),
            "max": float(normalized_scores.max()),
            "mean": float(normalized_scores.mean()),
            "std": float(normalized_scores.std())
        },
        "parameters": {
            "score_column": score_col,
            "gamma": gamma,
            "num_games": len(game_scores)
        },
        "game_ids": game_scores['appid'].tolist()
    }
    
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 저장 완료:")
    print(f"   - 게임 가중치: {output_path}")
    print(f"   - 통계 정보: {stats_path}")
    print(f"   - 배열 크기: {normalized_scores.shape}")


if __name__ == "__main__":
    args = _parse_args()
    main(args.input, args.score_col, args.gamma, args.output, args.stats)
