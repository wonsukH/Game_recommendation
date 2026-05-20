import pandas as pd
import numpy as np
import argparse
from pathlib import Path
import json
from sklearn.metrics.pairwise import cosine_similarity
from scipy.stats import entropy


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 9: Quality checks and evaluation")
    parser.add_argument(
        "--tag-vecs", type=str,
        default=str(Path("outputs/tag_vecs.npy")),
        help="Input tag vectors path (default: outputs/tag_vecs.npy)"
    )
    parser.add_argument(
        "--game-vecs", type=str,
        default=str(Path("outputs/game_vecs.npy")),
        help="Input game vectors path (default: outputs/game_vecs.npy)"
    )
    parser.add_argument(
        "--indexes", type=str,
        default=str(Path("outputs/index_maps.json")),
        help="Input index maps JSON path (default: outputs/index_maps.json)"
    )
    parser.add_argument(
        "--tag-beta", type=str,
        default=str(Path("outputs/tag_beta.npy")),
        help="Input tag beta coefficients path (default: outputs/tag_beta.npy)"
    )
    parser.add_argument(
        "--tag-beta-stats", type=str,
        default=str(Path("outputs/tag_beta_stats.json")),
        help="Input tag beta statistics path (default: outputs/tag_beta_stats.json)"
    )
    parser.add_argument(
        "--output", type=str,
        default=str(Path("outputs/quality_report.json")),
        help="Output quality report path (default: outputs/quality_report.json)"
    )
    parser.add_argument(
        "--top-k", type=int,
        default=10,
        help="Top-k for similarity checks (default: 10)"
    )
    return parser.parse_args()


def tag_neighborhood_spotcheck(tag_vecs: np.ndarray, idx2tag: dict, top_k: int = 10) -> dict:
    """
    태그 이웃 스팟체크
    
    Args:
        tag_vecs: 태그 벡터
        idx2tag: 인덱스→태그 매핑
        top_k: Top-k 유사 태그
    
    Returns:
        스팟체크 결과
    """
    print("[INFO] 태그 이웃 스팟체크 중...")
    
    # 테스트 태그들
    test_tags = ["cozy", "roguelike", "soulslike", "horror", "open-world"]
    
    results = {}
    
    for test_tag in test_tags:
        # 테스트 태그 인덱스 찾기
        tag_idx = None
        for idx, tag_name in idx2tag.items():
            if test_tag.lower() in tag_name.lower():
                tag_idx = idx
                break
        
        if tag_idx is None:
            print(f"   [WARNING] 태그 '{test_tag}'을 찾을 수 없습니다.")
            continue
        
        # 코사인 유사도 계산
        tag_vec = tag_vecs[tag_idx]
        similarities = []
        
        for i, other_vec in enumerate(tag_vecs):
            if i != tag_idx:
                similarity = np.dot(tag_vec, other_vec) / (np.linalg.norm(tag_vec) * np.linalg.norm(other_vec))
                similarities.append((i, similarity))
        
        # Top-k 유사 태그
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_similar = similarities[:top_k]
        
        results[test_tag] = {
            "tag_idx": tag_idx,
            "top_similar": [(idx2tag[idx], sim) for idx, sim in top_similar]
        }
        
        print(f"   - {test_tag}:")
        for i, (idx, sim) in enumerate(top_similar):
            name = idx2tag[idx]
            print(f"     {i+1:2d}. {name:20s}: {sim:.4f}")
    
    return results


def game_similarity_spotcheck(game_vecs: np.ndarray, row2appid: dict, top_k: int = 10) -> dict:
    """
    게임 유사도 스팟체크
    
    Args:
        game_vecs: 게임 벡터
        row2appid: 행→appid 매핑
        top_k: Top-k 유사 게임
    
    Returns:
        스팟체크 결과
    """
    print("[INFO] 게임 유사도 스팟체크 중...")
    
    # 대표 게임들 (처음 20개)
    num_test_games = min(20, len(game_vecs))
    test_games = list(range(num_test_games))
    
    results = {}
    
    for game_idx in test_games:
        game_id = row2appid[game_idx]
        game_vec = game_vecs[game_idx]
        
        # 코사인 유사도 계산
        similarities = []
        for i, other_vec in enumerate(game_vecs):
            if i != game_idx:
                similarity = np.dot(game_vec, other_vec) / (np.linalg.norm(game_vec) * np.linalg.norm(other_vec))
                similarities.append((i, similarity))
        
        # Top-k 유사 게임
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_similar = similarities[:top_k]
        
        results[f"game_{game_id}"] = {
            "game_idx": game_idx,
            "top_similar": [(row2appid[idx], sim) for idx, sim in top_similar]
        }
        
        if game_idx < 5:  # 처음 5개만 출력
            print(f"   - 게임 {game_id}:")
            for i, (similar_game_id, sim) in enumerate(top_similar[:5]):
                print(f"     {i+1:2d}. 게임 {similar_game_id}: {sim:.4f}")
    
    return results


def analyze_hubness(vectors: np.ndarray, name: str) -> dict:
    """
    허브니스 분석
    
    Args:
        vectors: 벡터 배열
        name: 벡터 이름
    
    Returns:
        허브니스 분석 결과
    """
    print(f"[INFO] {name} 허브니스 분석 중...")
    
    # 코사인 유사도 행렬
    similarities = cosine_similarity(vectors)
    
    # 각 벡터가 다른 벡터의 Top-k에 등장하는 횟수
    k = 10
    hubness_scores = np.sum(similarities > np.sort(similarities, axis=1)[:, -k-1][:, np.newaxis], axis=0)
    
    # 허브니스 통계
    hubness_stats = {
        "mean_hubness": float(np.mean(hubness_scores)),
        "std_hubness": float(np.std(hubness_scores)),
        "max_hubness": int(np.max(hubness_scores)),
        "min_hubness": int(np.min(hubness_scores)),
        "hubness_entropy": float(entropy(np.bincount(hubness_scores.astype(int)))),
        "hubness_distribution": np.bincount(hubness_scores.astype(int)).tolist()
    }
    
    print(f"   - 평균 허브니스: {hubness_stats['mean_hubness']:.2f}")
    print(f"   - 허브니스 표준편차: {hubness_stats['std_hubness']:.2f}")
    print(f"   - 최대 허브니스: {hubness_stats['max_hubness']}")
    print(f"   - 허브니스 엔트로피: {hubness_stats['hubness_entropy']:.4f}")
    
    return hubness_stats


def evaluate_regression_fitness(tag_beta_stats_path: str) -> dict:
    """
    회귀 적합도 평가
    
    Args:
        tag_beta_stats_path: 태그 베타 통계 파일 경로
    
    Returns:
        회귀 적합도 결과
    """
    print("[INFO] 회귀 적합도 평가 중...")
    
    if not Path(tag_beta_stats_path).exists():
        print(f"   [WARNING] {tag_beta_stats_path} 파일이 없습니다.")
        return {}
    
    with open(tag_beta_stats_path, 'r', encoding='utf-8') as f:
        stats = json.load(f)
    
    regression_info = stats.get("regression_info", {})
    
    results = {
        "r2_score": regression_info.get("r2_score", 0.0),
        "num_coefficients": regression_info.get("num_coefficients", 0),
        "coefficient_stats": stats.get("coefficient_stats", {}),
        "overfitting_assessment": "Unknown"
    }
    
    # 과적합 평가
    r2 = results["r2_score"]
    if r2 > 0.9:
        results["overfitting_assessment"] = "High risk of overfitting"
    elif r2 > 0.7:
        results["overfitting_assessment"] = "Moderate risk of overfitting"
    elif r2 > 0.5:
        results["overfitting_assessment"] = "Good fit"
    else:
        results["overfitting_assessment"] = "Poor fit"
    
    print(f"   - R² 점수: {r2:.4f}")
    print(f"   - 계수 개수: {results['num_coefficients']}")
    print(f"   - 과적합 평가: {results['overfitting_assessment']}")
    
    return results


def main(tag_vecs_path: str, game_vecs_path: str, index_path: str, tag_beta_path: str,
         tag_beta_stats_path: str, output_path: str, top_k: int):
    print(f"[INFO] 품질 점검 시작:")
    print(f"   - 태그 벡터: {tag_vecs_path}")
    print(f"   - 게임 벡터: {game_vecs_path}")
    print(f"   - Top-k: {top_k}")
    
    # 데이터 로드
    tag_vecs = np.load(tag_vecs_path)
    game_vecs = np.load(game_vecs_path)
    tag_beta = np.load(tag_beta_path)
    
    with open(index_path, 'r', encoding='utf-8') as f:
        index_maps = json.load(f)
    
    idx2tag = {int(k): v for k, v in index_maps['idx2tag'].items()}
    row2appid = {int(k): v for k, v in index_maps['row2appid'].items()}
    
    print(f"[INFO] 데이터 크기:")
    print(f"   - 태그 벡터: {tag_vecs.shape}")
    print(f"   - 게임 벡터: {game_vecs.shape}")
    print(f"   - 태그 효과: {tag_beta.shape}")
    
    # 1. 태그 이웃 스팟체크
    print(f"\n[INFO] 1. 태그 이웃 스팟체크")
    tag_neighborhood_results = tag_neighborhood_spotcheck(tag_vecs, idx2tag, top_k)
    
    # 2. 게임 유사도 스팟체크
    print(f"\n[INFO] 2. 게임 유사도 스팟체크")
    game_similarity_results = game_similarity_spotcheck(game_vecs, row2appid, top_k)
    
    # 3. 허브니스 분석
    print(f"\n[INFO] 3. 허브니스 분석")
    tag_hubness = analyze_hubness(tag_vecs, "태그")
    game_hubness = analyze_hubness(game_vecs, "게임")
    
    # 4. 회귀 적합도 평가
    print(f"\n[INFO] 4. 회귀 적합도 평가")
    regression_fitness = evaluate_regression_fitness(tag_beta_stats_path)
    
    # 결과 통합
    quality_report = {
        "timestamp": pd.Timestamp.now().isoformat(),
        "tag_neighborhood_spotcheck": tag_neighborhood_results,
        "game_similarity_spotcheck": game_similarity_results,
        "hubness_analysis": {
            "tag_hubness": tag_hubness,
            "game_hubness": game_hubness
        },
        "regression_fitness": regression_fitness,
        "summary": {
            "total_tags": len(tag_vecs),
            "total_games": len(game_vecs),
            "embedding_dim": tag_vecs.shape[1]
        }
    }
    
    # 출력 폴더 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 결과 저장
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(quality_report, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 품질 점검 완료!")
    print(f"   - 보고서 저장: {output_path}")
    
    # 요약 출력
    print(f"\n[INFO] 품질 점검 요약:")
    print(f"   - 태그 이웃 체크: {len(tag_neighborhood_results)}개 태그")
    print(f"   - 게임 유사도 체크: {len(game_similarity_results)}개 게임")
    print(f"   - 태그 허브니스: {tag_hubness['mean_hubness']:.2f} (평균)")
    print(f"   - 게임 허브니스: {game_hubness['mean_hubness']:.2f} (평균)")
    if regression_fitness:
        print(f"   - 회귀 R²: {regression_fitness['r2_score']:.4f}")


if __name__ == "__main__":
    args = _parse_args()
    main(args.tag_vecs, args.game_vecs, args.indexes, args.tag_beta,
         args.tag_beta_stats, args.output, args.top_k)
