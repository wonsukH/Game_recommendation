import numpy as np
import json
import argparse
from pathlib import Path
from typing import List, Dict, Tuple
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 13: Filter & Scoring")
    parser.add_argument(
        "--candidates", type=str,
        default="outputs/candidates.json",
        help="Input candidates JSON file (default: outputs/candidates.json)"
    )
    parser.add_argument(
        "--intent", type=str,
        default="outputs/parsed_intent.json",
        help="Input parsed intent JSON file (default: outputs/parsed_intent.json)"
    )
    parser.add_argument(
        "--game-tag-matrix", type=str,
        default="outputs/X_game_tag_csr.npz",
        help="Input game-tag matrix path (default: outputs/X_game_tag_csr.npz)"
    )
    parser.add_argument(
        "--game-weight", type=str,
        default="outputs/game_weight.npy",
        help="Input game weight path (default: outputs/game_weight.npy)"
    )
    parser.add_argument(
        "--output", type=str,
        default="outputs/scored_candidates.json",
        help="Output scored candidates JSON file (default: outputs/scored_candidates.json)"
    )
    parser.add_argument(
        "--alpha", type=float,
        default=0.4,
        help="Tag match weight (default: 0.4)"
    )
    parser.add_argument(
        "--beta", type=float,
        default=0.2,
        help="Novelty weight (default: 0.2)"
    )
    parser.add_argument(
        "--gamma", type=float,
        default=0.2,
        help="Recency weight (default: 0.2)"
    )
    parser.add_argument(
        "--delta", type=float,
        default=0.2,
        help="Popularity weight (default: 0.2)"
    )
    return parser.parse_args()


def calculate_tag_match_score(candidate_game_ids: List[int], target_tags: List[str],
                            avoid_tags: List[str], game_tag_matrix: csr_matrix,
                            tag2idx: Dict[str, int]) -> np.ndarray:
    """
    태그 매칭 점수 계산
    
    Args:
        candidate_game_ids: 후보 게임 ID 리스트
        target_tags: 원하는 태그 리스트
        avoid_tags: 피할 태그 리스트
        game_tag_matrix: 게임-태그 행렬
        tag2idx: 태그→인덱스 매핑
    
    Returns:
        태그 매칭 점수 배열
    """
    print("[INFO] 태그 매칭 점수 계산 중...")
    
    scores = np.zeros(len(candidate_game_ids))
    
    # 태그 인덱스 변환
    target_tag_indices = [tag2idx.get(tag, -1) for tag in target_tags]
    avoid_tag_indices = [tag2idx.get(tag, -1) for tag in avoid_tags]
    
    # 유효한 태그만 필터링
    target_tag_indices = [idx for idx in target_tag_indices if idx != -1]
    avoid_tag_indices = [idx for idx in avoid_tag_indices if idx != -1]
    
    for i, game_id in enumerate(candidate_game_ids):
        # 게임의 태그 인덱스 찾기
        game_row = game_tag_matrix[game_id]
        game_tag_indices = game_row.indices
        
        # 원하는 태그 매칭 점수
        target_matches = len(set(game_tag_indices) & set(target_tag_indices))
        target_score = target_matches / max(len(target_tag_indices), 1)
        
        # 피할 태그 페널티
        avoid_matches = len(set(game_tag_indices) & set(avoid_tag_indices))
        avoid_penalty = avoid_matches * 0.5  # 피할 태그당 0.5점 감점
        
        # 최종 태그 점수
        tag_score = max(0, target_score - avoid_penalty)
        scores[i] = tag_score
    
    print(f"   - 평균 태그 점수: {np.mean(scores):.4f}")
    print(f"   - 최고 태그 점수: {np.max(scores):.4f}")
    
    return scores


def calculate_novelty_score(candidate_game_ids: List[int], 
                          game_tag_matrix: csr_matrix) -> np.ndarray:
    """
    신선도 점수 계산 (태그 조합의 독특성)
    
    Args:
        candidate_game_ids: 후보 게임 ID 리스트
        game_tag_matrix: 게임-태그 행렬
    
    Returns:
        신선도 점수 배열
    """
    print("[INFO] 신선도 점수 계산 중...")
    
    scores = np.zeros(len(candidate_game_ids))
    
    # 전체 게임의 태그 빈도 계산
    all_tag_counts = np.array(game_tag_matrix.sum(axis=0)).flatten()
    total_games = game_tag_matrix.shape[0]
    
    for i, game_id in enumerate(candidate_game_ids):
        game_row = game_tag_matrix[game_id]
        game_tag_indices = game_row.indices
        
        if len(game_tag_indices) == 0:
            scores[i] = 0.0
            continue
        
        # 게임의 태그들의 평균 빈도
        tag_frequencies = all_tag_counts[game_tag_indices] / total_games
        
        # 신선도 = 1 - 평균 빈도 (낮은 빈도일수록 높은 신선도)
        novelty = 1 - np.mean(tag_frequencies)
        scores[i] = novelty
    
    print(f"   - 평균 신선도: {np.mean(scores):.4f}")
    print(f"   - 최고 신선도: {np.max(scores):.4f}")
    
    return scores


def calculate_recency_score(candidate_game_ids: List[int], 
                          game_weights: np.ndarray) -> np.ndarray:
    """
    최신성 점수 계산 (게임 가중치 기반)
    
    Args:
        candidate_game_ids: 후보 게임 ID 리스트
        game_weights: 게임 가중치 배열
    
    Returns:
        최신성 점수 배열
    """
    print("[INFO] 최신성 점수 계산 중...")
    
    scores = np.zeros(len(candidate_game_ids))
    
    for i, game_id in enumerate(candidate_game_ids):
        if game_id < len(game_weights):
            # 게임 가중치를 최신성 점수로 사용
            scores[i] = game_weights[game_id]
        else:
            scores[i] = 0.0
    
    # 정규화 (0-1 범위로)
    if np.max(scores) > 0:
        scores = scores / np.max(scores)
    
    print(f"   - 평균 최신성: {np.mean(scores):.4f}")
    print(f"   - 최고 최신성: {np.max(scores):.4f}")
    
    return scores


def calculate_popularity_score(candidate_game_ids: List[int],
                             game_tag_matrix: csr_matrix) -> np.ndarray:
    """
    인기도 점수 계산 (태그 수 기반)
    
    Args:
        candidate_game_ids: 후보 게임 ID 리스트
        game_tag_matrix: 게임-태그 행렬
    
    Returns:
        인기도 점수 배열
    """
    print("[INFO] 인기도 점수 계산 중...")
    
    scores = np.zeros(len(candidate_game_ids))
    
    # 전체 게임의 태그 수 분포
    all_tag_counts = np.array(game_tag_matrix.sum(axis=1)).flatten()
    max_tags = np.max(all_tag_counts)
    
    for i, game_id in enumerate(candidate_game_ids):
        if game_id < len(all_tag_counts):
            # 태그 수를 인기도로 사용 (정규화)
            tag_count = all_tag_counts[game_id]
            popularity = tag_count / max_tags if max_tags > 0 else 0
            scores[i] = popularity
        else:
            scores[i] = 0.0
    
    print(f"   - 평균 인기도: {np.mean(scores):.4f}")
    print(f"   - 최고 인기도: {np.max(scores):.4f}")
    
    return scores


def apply_hard_constraints(candidates: List[Dict], constraints: Dict,
                          game_data: Dict) -> List[Dict]:
    """
    하드 제약조건 적용
    
    Args:
        candidates: 후보 게임 리스트
        constraints: 제약조건 딕셔너리
        game_data: 게임 메타데이터
    
    Returns:
        필터링된 후보 리스트
    """
    if not constraints:
        return candidates
    
    print("[INFO] 하드 제약조건 필터링 중...")
    
    filtered_candidates = []
    
    for candidate in candidates:
        game_id = candidate['game_id']
        game_info = game_data.get(str(game_id), {})
        
        # 제약조건 검사
        passed = True
        
        for constraint_key, constraint_value in constraints.items():
            if constraint_key == 'price_max':
                game_price = game_info.get('price', float('inf'))
                if game_price > constraint_value:
                    passed = False
                    break
            
            elif constraint_key == 'price_min':
                game_price = game_info.get('price', 0)
                if game_price < constraint_value:
                    passed = False
                    break
            
            elif constraint_key == 'platform':
                game_platforms = game_info.get('platforms', [])
                if constraint_value not in game_platforms:
                    passed = False
                    break
            
            elif constraint_key == 'language':
                game_languages = game_info.get('languages', [])
                if constraint_value not in game_languages:
                    passed = False
                    break
            
            elif constraint_key == 'age_rating':
                game_age = game_info.get('age_rating', 0)
                if game_age > constraint_value:
                    passed = False
                    break
        
        if passed:
            filtered_candidates.append(candidate)
    
    print(f"   - 필터링 전: {len(candidates)}개")
    print(f"   - 필터링 후: {len(filtered_candidates)}개")
    
    return filtered_candidates


def calculate_final_score(tag_scores: np.ndarray, novelty_scores: np.ndarray,
                         recency_scores: np.ndarray, popularity_scores: np.ndarray,
                         alpha: float, beta: float, gamma: float, delta: float) -> np.ndarray:
    """
    최종 점수 계산
    
    Args:
        tag_scores: 태그 매칭 점수
        novelty_scores: 신선도 점수
        recency_scores: 최신성 점수
        popularity_scores: 인기도 점수
        alpha, beta, gamma, delta: 가중치
    
    Returns:
        최종 점수 배열
    """
    print("[INFO] 최종 점수 계산 중...")
    
    # 가중합 계산
    final_scores = (alpha * tag_scores + 
                   beta * novelty_scores + 
                   gamma * recency_scores + 
                   delta * popularity_scores)
    
    # 정규화 (0-1 범위로)
    if np.max(final_scores) > 0:
        final_scores = final_scores / np.max(final_scores)
    
    print(f"   - 가중치: α={alpha}, β={beta}, γ={gamma}, δ={delta}")
    print(f"   - 평균 최종 점수: {np.mean(final_scores):.4f}")
    print(f"   - 최고 최종 점수: {np.max(final_scores):.4f}")
    
    return final_scores


def main(candidates_path: str, intent_path: str, game_tag_matrix_path: str,
         game_weight_path: str, output_path: str, alpha: float, beta: float,
         gamma: float, delta: float):
    print(f"[INFO] 필터 & 스코어링 시작:")
    print(f"   - 후보: {candidates_path}")
    print(f"   - 의도: {intent_path}")
    print(f"   - 게임-태그 행렬: {game_tag_matrix_path}")
    
    # 파일 존재 확인
    required_files = [candidates_path, intent_path, game_tag_matrix_path, game_weight_path]
    for file_path in required_files:
        if not Path(file_path).exists():
            print(f"[ERROR] 파일이 없습니다: {file_path}")
            return
    
    # 데이터 로드
    with open(candidates_path, 'r', encoding='utf-8') as f:
        candidates_data = json.load(f)
    
    with open(intent_path, 'r', encoding='utf-8') as f:
        intent_data = json.load(f)
    
    game_tag_matrix = csr_matrix.load_npz(game_tag_matrix_path)
    game_weights = np.load(game_weight_path)
    
    # 인덱스 맵 로드
    index_maps_path = Path("outputs/index_maps.json")
    if not index_maps_path.exists():
        print(f"[ERROR] 인덱스 맵 파일이 없습니다: {index_maps_path}")
        return
    
    with open(index_maps_path, 'r', encoding='utf-8') as f:
        index_maps = json.load(f)
    
    # 태그 사전 로드
    tag_vocab_path = Path("outputs/tag_vocab.json")
    if not tag_vocab_path.exists():
        print(f"[ERROR] 태그 사전 파일이 없습니다: {tag_vocab_path}")
        return
    
    with open(tag_vocab_path, 'r', encoding='utf-8') as f:
        tag_vocab = json.load(f)
    
    print(f"[INFO] 데이터 크기:")
    print(f"   - 후보 수: {len(candidates_data['candidates'])}")
    print(f"   - 게임-태그 행렬: {game_tag_matrix.shape}")
    print(f"   - 게임 가중치: {game_weights.shape}")
    
    # 후보 게임 ID 추출
    candidates = candidates_data['candidates']
    candidate_game_ids = [c['row_index'] for c in candidates]
    
    # 하드 제약조건 필터링
    filtered_candidates = apply_hard_constraints(
        candidates, intent_data['constraints'], {}
    )
    
    if not filtered_candidates:
        print("[ERROR] 제약조건을 만족하는 후보가 없습니다.")
        return
    
    # 필터링된 후보 ID 업데이트
    candidate_game_ids = [c['row_index'] for c in filtered_candidates]
    
    # 각종 점수 계산
    tag2idx = tag_vocab.get('tag2idx', {})
    
    tag_scores = calculate_tag_match_score(
        candidate_game_ids, intent_data['target_tags'], 
        intent_data['avoid_tags'], game_tag_matrix, tag2idx
    )
    
    novelty_scores = calculate_novelty_score(candidate_game_ids, game_tag_matrix)
    recency_scores = calculate_recency_score(candidate_game_ids, game_weights)
    popularity_scores = calculate_popularity_score(candidate_game_ids, game_tag_matrix)
    
    # 최종 점수 계산
    final_scores = calculate_final_score(
        tag_scores, novelty_scores, recency_scores, popularity_scores,
        alpha, beta, gamma, delta
    )
    
    # 점수 정보를 후보에 추가
    for i, candidate in enumerate(filtered_candidates):
        candidate['scores'] = {
            'tag_match': float(tag_scores[i]),
            'novelty': float(novelty_scores[i]),
            'recency': float(recency_scores[i]),
            'popularity': float(popularity_scores[i]),
            'final': float(final_scores[i])
        }
    
    # 최종 점수로 정렬
    filtered_candidates.sort(key=lambda x: x['scores']['final'], reverse=True)
    
    # 결과 구성
    result = {
        'scoring_info': {
            'weights': {
                'alpha': alpha,
                'beta': beta,
                'gamma': gamma,
                'delta': delta
            },
            'total_candidates': len(filtered_candidates),
            'filtered_from': len(candidates)
        },
        'candidates': filtered_candidates,
        'score_statistics': {
            'tag_match': {
                'mean': float(np.mean(tag_scores)),
                'std': float(np.std(tag_scores)),
                'max': float(np.max(tag_scores))
            },
            'novelty': {
                'mean': float(np.mean(novelty_scores)),
                'std': float(np.std(novelty_scores)),
                'max': float(np.max(novelty_scores))
            },
            'recency': {
                'mean': float(np.mean(recency_scores)),
                'std': float(np.std(recency_scores)),
                'max': float(np.max(recency_scores))
            },
            'popularity': {
                'mean': float(np.mean(popularity_scores)),
                'std': float(np.std(popularity_scores)),
                'max': float(np.max(popularity_scores))
            },
            'final': {
                'mean': float(np.mean(final_scores)),
                'std': float(np.std(final_scores)),
                'max': float(np.max(final_scores))
            }
        }
    }
    
    # 출력 폴더 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 결과 저장
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 필터 & 스코어링 완료!")
    print(f"   - 저장: {output_path}")
    print(f"   - 최종 후보 수: {len(filtered_candidates)}")
    
    # 상위 후보 출력
    print(f"\n[INFO] Top-10 스코어링 결과:")
    for i, candidate in enumerate(filtered_candidates[:10]):
        scores = candidate['scores']
        print(f"   {i+1:2d}. 게임 {candidate['game_id']}: {scores['final']:.4f}")
        print(f"       (태그: {scores['tag_match']:.3f}, 신선도: {scores['novelty']:.3f}, "
              f"최신성: {scores['recency']:.3f}, 인기도: {scores['popularity']:.3f})")


if __name__ == "__main__":
    args = _parse_args()
    main(args.candidates, args.intent, args.game_tag_matrix, args.game_weight,
         args.output, args.alpha, args.beta, args.gamma, args.delta)
