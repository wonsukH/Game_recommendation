import numpy as np
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 11: Query Vector Generation")
    parser.add_argument(
        "--intent", type=str,
        default="outputs/parsed_intent.json",
        help="Input parsed intent JSON file (default: outputs/parsed_intent.json)"
    )
    parser.add_argument(
        "--game-vecs", type=str,
        default="outputs/game_vecs.npy",
        help="Input game vectors path (default: outputs/game_vecs.npy)"
    )
    parser.add_argument(
        "--tag-vecs", type=str,
        default="outputs/tag_vecs.npy",
        help="Input tag vectors path (default: outputs/tag_vecs.npy)"
    )
    parser.add_argument(
        "--indexes", type=str,
        default="outputs/index_maps.json",
        help="Input index maps JSON path (default: outputs/index_maps.json)"
    )
    parser.add_argument(
        "--align", type=str,
        default="outputs/W_align.npy",
        help="Input alignment matrix path (default: outputs/W_align.npy)"
    )
    parser.add_argument(
        "--output", type=str,
        default="outputs/query_vector.npy",
        help="Output query vector path (default: outputs/query_vector.npy)"
    )
    parser.add_argument(
        "--model", type=str,
        default="all-MiniLM-L6-v2",
        help="Sentence transformer model (default: all-MiniLM-L6-v2)"
    )
    return parser.parse_args()


def generate_similar_query_vector(games: List[int], game_vecs: np.ndarray, 
                                index_maps: Dict) -> np.ndarray:
    """
    Similar 모드: 시드 게임 벡터의 평균
    
    Args:
        games: 시드 게임 ID 리스트
        game_vecs: 게임 벡터 배열
        index_maps: 인덱스 매핑
    
    Returns:
        쿼리 벡터
    """
    print("[INFO] Similar 모드: 시드 게임 벡터 평균 계산 중...")
    
    appid2row = {int(k): v for k, v in index_maps['appid2row'].items()}
    game_vectors = []
    
    for game_id in games:
        if game_id in appid2row:
            row_idx = appid2row[game_id]
            game_vectors.append(game_vecs[row_idx])
        else:
            print(f"[WARNING] 게임 ID {game_id}를 찾을 수 없습니다.")
    
    if not game_vectors:
        raise ValueError("유효한 시드 게임이 없습니다.")
    
    # 평균 계산
    query_vector = np.mean(game_vectors, axis=0)
    
    # L2 정규화
    norm = np.linalg.norm(query_vector)
    if norm > 0:
        query_vector = query_vector / norm
    
    print(f"   - 시드 게임 수: {len(game_vectors)}")
    print(f"   - 쿼리 벡터 크기: {query_vector.shape}")
    
    return query_vector


def generate_vibe_query_vector(phrases: List[str], tag_vecs: np.ndarray,
                             W_align: np.ndarray, model: SentenceTransformer) -> np.ndarray:
    """
    Vibe 모드: 자연어 → W_align 투영 → 태그 벡터
    
    Args:
        phrases: 자연어 표현 리스트
        tag_vecs: 태그 벡터 배열
        W_align: 정렬 행렬
        model: 문장 임베딩 모델
    
    Returns:
        쿼리 벡터
    """
    print("[INFO] Vibe 모드: 자연어 → 태그 벡터 변환 중...")
    
    if not phrases:
        raise ValueError("자연어 표현이 없습니다.")
    
    # 자연어 임베딩
    phrase_embeddings = model.encode(phrases)
    
    # W_align을 통한 투영
    projected_vectors = []
    for phrase_emb in phrase_embeddings:
        projected = phrase_emb @ W_align
        projected_vectors.append(projected)
    
    # 평균 계산
    query_vector = np.mean(projected_vectors, axis=0)
    
    # L2 정규화
    norm = np.linalg.norm(query_vector)
    if norm > 0:
        query_vector = query_vector / norm
    
    print(f"   - 자연어 표현 수: {len(phrases)}")
    print(f"   - 쿼리 벡터 크기: {query_vector.shape}")
    
    return query_vector


def generate_hybrid_query_vector(similar_vector: np.ndarray, vibe_vector: np.ndarray,
                               weights: Dict[str, float]) -> np.ndarray:
    """
    Hybrid 모드: similar과 vibe 벡터의 가중합
    
    Args:
        similar_vector: similar 모드 쿼리 벡터
        vibe_vector: vibe 모드 쿼리 벡터
        weights: 가중치 딕셔너리
    
    Returns:
        하이브리드 쿼리 벡터
    """
    print("[INFO] Hybrid 모드: 가중합 계산 중...")
    
    # 가중치 정규화
    similar_weight = weights.get('similar', 0.5)
    vibe_weight = weights.get('vibe', 0.5)
    
    # 가중합 계산
    query_vector = similar_weight * similar_vector + vibe_weight * vibe_vector
    
    # L2 정규화
    norm = np.linalg.norm(query_vector)
    if norm > 0:
        query_vector = query_vector / norm
    
    print(f"   - Similar 가중치: {similar_weight}")
    print(f"   - Vibe 가중치: {vibe_weight}")
    print(f"   - 쿼리 벡터 크기: {query_vector.shape}")
    
    return query_vector


def main(intent_path: str, game_vecs_path: str, tag_vecs_path: str, 
         index_path: str, align_path: str, output_path: str, model_name: str):
    print(f"[INFO] 쿼리 벡터 생성 시작:")
    print(f"   - 의도 파일: {intent_path}")
    print(f"   - 게임 벡터: {game_vecs_path}")
    print(f"   - 태그 벡터: {tag_vecs_path}")
    print(f"   - 정렬 행렬: {align_path}")
    
    # 파일 존재 확인
    required_files = [intent_path, game_vecs_path, tag_vecs_path, index_path]
    for file_path in required_files:
        if not Path(file_path).exists():
            print(f"[ERROR] 파일이 없습니다: {file_path}")
            return
    
    # 데이터 로드
    with open(intent_path, 'r', encoding='utf-8') as f:
        intent_data = json.load(f)
    
    game_vecs = np.load(game_vecs_path)
    tag_vecs = np.load(tag_vecs_path)
    
    with open(index_path, 'r', encoding='utf-8') as f:
        index_maps = json.load(f)
    
    # 정렬 행렬 로드 (vibe 모드용)
    W_align = None
    if Path(align_path).exists():
        W_align = np.load(align_path)
    
    print(f"[INFO] 데이터 크기:")
    print(f"   - 게임 벡터: {game_vecs.shape}")
    print(f"   - 태그 벡터: {tag_vecs.shape}")
    if W_align is not None:
        print(f"   - 정렬 행렬: {W_align.shape}")
    
    # 모드별 쿼리 벡터 생성
    mode = intent_data['mode']
    query_vector = None
    
    if mode == 'similar':
        query_vector = generate_similar_query_vector(
            intent_data['games'], game_vecs, index_maps
        )
    
    elif mode == 'vibe':
        if W_align is None:
            print("[ERROR] Vibe 모드에는 정렬 행렬이 필요합니다.")
            return
        
        # 문장 임베딩 모델 로드
        model = SentenceTransformer(model_name)
        
        query_vector = generate_vibe_query_vector(
            intent_data['phrases'], tag_vecs, W_align, model
        )
    
    elif mode == 'hybrid':
        # Similar 벡터 생성
        similar_vector = generate_similar_query_vector(
            intent_data['games'], game_vecs, index_maps
        )
        
        # Vibe 벡터 생성
        if W_align is None:
            print("[ERROR] Hybrid 모드에는 정렬 행렬이 필요합니다.")
            return
        
        model = SentenceTransformer(model_name)
        vibe_vector = generate_vibe_query_vector(
            intent_data['phrases'], tag_vecs, W_align, model
        )
        
        # 하이브리드 벡터 생성
        query_vector = generate_hybrid_query_vector(
            similar_vector, vibe_vector, intent_data.get('weights', {})
        )
    
    else:
        print(f"[ERROR] 알 수 없는 모드: {mode}")
        return
    
    # 출력 폴더 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 쿼리 벡터 저장
    np.save(output_path, query_vector)
    
    print(f"✅ 쿼리 벡터 생성 완료!")
    print(f"   - 모드: {mode}")
    print(f"   - 저장: {output_path}")
    print(f"   - 벡터 크기: {query_vector.shape}")
    
    # 벡터 통계
    print(f"\n[INFO] 쿼리 벡터 통계:")
    print(f"   - 평균: {np.mean(query_vector):.4f}")
    print(f"   - 표준편차: {np.std(query_vector):.4f}")
    print(f"   - 최소값: {np.min(query_vector):.4f}")
    print(f"   - 최대값: {np.max(query_vector):.4f}")
    print(f"   - L2 노름: {np.linalg.norm(query_vector):.4f}")


if __name__ == "__main__":
    args = _parse_args()
    main(args.intent, args.game_vecs, args.tag_vecs, args.indexes,
         args.align, args.output, args.model)
