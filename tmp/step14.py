import numpy as np
import json
import argparse
from pathlib import Path
from typing import List, Dict, Tuple
from sklearn.metrics.pairwise import cosine_similarity


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 14: Diversity Selection with MMR")
    parser.add_argument(
        "--scored-candidates", type=str,
        default="outputs/scored_candidates.json",
        help="Input scored candidates JSON file (default: outputs/scored_candidates.json)"
    )
    parser.add_argument(
        "--game-vecs", type=str,
        default="outputs/game_vecs.npy",
        help="Input game vectors path (default: outputs/game_vecs.npy)"
    )
    parser.add_argument(
        "--output", type=str,
        default="outputs/diverse_recommendations.json",
        help="Output diverse recommendations JSON file (default: outputs/diverse_recommendations.json)"
    )
    parser.add_argument(
        "--k", type=int,
        default=10,
        help="Number of diverse recommendations (default: 10)"
    )
    parser.add_argument(
        "--lambda", type=float,
        default=0.5,
        help="MMR lambda parameter (default: 0.5)"
    )
    return parser.parse_args()


def calculate_mmr_score(candidate_idx: int, selected_indices: List[int],
                       relevance_scores: np.ndarray, similarity_matrix: np.ndarray,
                       lambda_param: float) -> float:
    """
    MMR 점수 계산
    
    Args:
        candidate_idx: 후보 인덱스
        selected_indices: 이미 선택된 인덱스 리스트
        relevance_scores: 관련성 점수 배열
        similarity_matrix: 유사도 행렬
        lambda_param: MMR 람다 파라미터
    
    Returns:
        MMR 점수
    """
    # 관련성 점수
    relevance = relevance_scores[candidate_idx]
    
    # 다양성 점수 (이미 선택된 항목들과의 최대 유사도)
    if not selected_indices:
        diversity = 0.0
    else:
        similarities = similarity_matrix[candidate_idx, selected_indices]
        diversity = np.max(similarities)
    
    # MMR 점수 = λ * 관련성 + (1-λ) * (1 - 다양성)
    mmr_score = lambda_param * relevance + (1 - lambda_param) * (1 - diversity)
    
    return mmr_score


def select_diverse_recommendations(candidates: List[Dict], game_vecs: np.ndarray,
                                 k: int, lambda_param: float) -> List[Dict]:
    """
    MMR을 사용한 다양성 있는 추천 선택
    
    Args:
        candidates: 후보 게임 리스트
        game_vecs: 게임 벡터 배열
        k: 선택할 추천 수
        lambda_param: MMR 람다 파라미터
    
    Returns:
        다양성 있는 추천 리스트
    """
    print(f"[INFO] MMR 다양성 선택 중 (K={k}, λ={lambda_param})...")
    
    if len(candidates) == 0:
        return []
    
    # 관련성 점수 추출
    relevance_scores = np.array([c['scores']['final'] for c in candidates])
    
    # 후보 게임 벡터 추출
    candidate_indices = [c['row_index'] for c in candidates]
    candidate_vectors = game_vecs[candidate_indices]
    
    # 유사도 행렬 계산
    similarity_matrix = cosine_similarity(candidate_vectors)
    
    # MMR 선택
    selected_indices = []
    remaining_indices = list(range(len(candidates)))
    
    for i in range(min(k, len(candidates))):
        # 각 후보의 MMR 점수 계산
        mmr_scores = []
        for idx in remaining_indices:
            mmr_score = calculate_mmr_score(
                idx, selected_indices, relevance_scores, 
                similarity_matrix, lambda_param
            )
            mmr_scores.append(mmr_score)
        
        # 최고 MMR 점수를 가진 후보 선택
        best_idx = remaining_indices[np.argmax(mmr_scores)]
        selected_indices.append(best_idx)
        remaining_indices.remove(best_idx)
    
    # 선택된 후보들 반환
    diverse_recommendations = [candidates[idx] for idx in selected_indices]
    
    # MMR 점수 정보 추가
    for i, rec in enumerate(diverse_recommendations):
        rec['mmr_rank'] = i + 1
        rec['mmr_info'] = {
            'lambda': lambda_param,
            'relevance_score': rec['scores']['final'],
            'diversity_contribution': 1 - rec['scores']['final']  # 간단한 추정
        }
    
    print(f"   - 선택된 추천 수: {len(diverse_recommendations)}")
    print(f"   - 평균 관련성: {np.mean([r['scores']['final'] for r in diverse_recommendations]):.4f}")
    
    return diverse_recommendations


def calculate_diversity_metrics(recommendations: List[Dict], game_vecs: np.ndarray) -> Dict:
    """
    다양성 메트릭 계산
    
    Args:
        recommendations: 추천 리스트
        game_vecs: 게임 벡터 배열
    
    Returns:
        다양성 메트릭 딕셔너리
    """
    if len(recommendations) < 2:
        return {
            'intra_list_similarity': 0.0,
            'coverage': 0.0,
            'novelty': 0.0
        }
    
    # 추천 게임 벡터
    rec_indices = [r['row_index'] for r in recommendations]
    rec_vectors = game_vecs[rec_indices]
    
    # 1. Intra-list Similarity (추천 내 유사도)
    similarity_matrix = cosine_similarity(rec_vectors)
    # 대각선 제외한 평균 유사도
    upper_tri = similarity_matrix[np.triu_indices(len(similarity_matrix), k=1)]
    intra_list_similarity = np.mean(upper_tri) if len(upper_tri) > 0 else 0.0
    
    # 2. Coverage (태그 커버리지)
    all_tags = set()
    rec_tags = set()
    
    for rec in recommendations:
        # 게임의 태그 정보가 있다면 사용 (실제로는 게임 메타데이터 필요)
        rec_tags.add(rec['game_id'])  # 간단한 예시
    
    coverage = len(rec_tags) / len(recommendations) if len(recommendations) > 0 else 0.0
    
    # 3. Novelty (신선도)
    novelty_scores = [r['scores']['novelty'] for r in recommendations]
    novelty = np.mean(novelty_scores) if novelty_scores else 0.0
    
    return {
        'intra_list_similarity': float(intra_list_similarity),
        'coverage': float(coverage),
        'novelty': float(novelty),
        'diversity_score': float(1 - intra_list_similarity)  # 유사도가 낮을수록 다양성 높음
    }


def main(scored_candidates_path: str, game_vecs_path: str, output_path: str,
         k: int, lambda_param: float):
    print(f"[INFO] 다양성 선택 시작:")
    print(f"   - 스코어링된 후보: {scored_candidates_path}")
    print(f"   - 게임 벡터: {game_vecs_path}")
    print(f"   - 선택 수: {k}")
    print(f"   - MMR λ: {lambda_param}")
    
    # 파일 존재 확인
    required_files = [scored_candidates_path, game_vecs_path]
    for file_path in required_files:
        if not Path(file_path).exists():
            print(f"[ERROR] 파일이 없습니다: {file_path}")
            return
    
    # 데이터 로드
    with open(scored_candidates_path, 'r', encoding='utf-8') as f:
        scored_data = json.load(f)
    
    game_vecs = np.load(game_vecs_path)
    
    print(f"[INFO] 데이터 크기:")
    print(f"   - 후보 수: {len(scored_data['candidates'])}")
    print(f"   - 게임 벡터: {game_vecs.shape}")
    
    # MMR 다양성 선택
    diverse_recommendations = select_diverse_recommendations(
        scored_data['candidates'], game_vecs, k, lambda_param
    )
    
    if not diverse_recommendations:
        print("[ERROR] 다양성 선택 결과가 없습니다.")
        return
    
    # 다양성 메트릭 계산
    diversity_metrics = calculate_diversity_metrics(diverse_recommendations, game_vecs)
    
    # 결과 구성
    result = {
        'mmr_info': {
            'k': k,
            'lambda': lambda_param,
            'total_candidates': len(scored_data['candidates']),
            'selected_recommendations': len(diverse_recommendations)
        },
        'diversity_metrics': diversity_metrics,
        'recommendations': diverse_recommendations,
        'selection_process': {
            'original_scoring_weights': scored_data['scoring_info']['weights'],
            'mmr_parameters': {
                'lambda': lambda_param,
                'relevance_weight': lambda_param,
                'diversity_weight': 1 - lambda_param
            }
        }
    }
    
    # 출력 폴더 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 결과 저장
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 다양성 선택 완료!")
    print(f"   - 저장: {output_path}")
    print(f"   - 추천 수: {len(diverse_recommendations)}")
    
    # 다양성 메트릭 출력
    print(f"\n[INFO] 다양성 메트릭:")
    print(f"   - Intra-list Similarity: {diversity_metrics['intra_list_similarity']:.4f}")
    print(f"   - Coverage: {diversity_metrics['coverage']:.4f}")
    print(f"   - Novelty: {diversity_metrics['novelty']:.4f}")
    print(f"   - Diversity Score: {diversity_metrics['diversity_score']:.4f}")
    
    # 추천 결과 출력
    print(f"\n[INFO] 다양성 추천 결과:")
    for i, rec in enumerate(diverse_recommendations):
        scores = rec['scores']
        print(f"   {i+1:2d}. 게임 {rec['game_id']}: {scores['final']:.4f}")
        print(f"       (태그: {scores['tag_match']:.3f}, 신선도: {scores['novelty']:.3f}, "
              f"최신성: {scores['recency']:.3f}, 인기도: {scores['popularity']:.3f})")


if __name__ == "__main__":
    args = _parse_args()
    main(args.scored_candidates, args.game_vecs, args.output, args.k, args.lambda)
