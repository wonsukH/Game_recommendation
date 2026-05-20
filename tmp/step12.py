import numpy as np
import json
import argparse
from pathlib import Path
from typing import List, Tuple, Dict
import faiss
from sklearn.metrics.pairwise import cosine_similarity


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 12: Candidate Search with ANN")
    parser.add_argument(
        "--query-vector", type=str,
        default="outputs/query_vector.npy",
        help="Input query vector path (default: outputs/query_vector.npy)"
    )
    parser.add_argument(
        "--game-vecs", type=str,
        default="outputs/game_vecs.npy",
        help="Input game vectors path (default: outputs/game_vecs.npy)"
    )
    parser.add_argument(
        "--indexes", type=str,
        default="outputs/index_maps.json",
        help="Input index maps JSON path (default: outputs/index_maps.json)"
    )
    parser.add_argument(
        "--output", type=str,
        default="outputs/candidates.json",
        help="Output candidates JSON file (default: outputs/candidates.json)"
    )
    parser.add_argument(
        "--top-n", type=int,
        default=500,
        help="Number of top candidates to retrieve (default: 500)"
    )
    parser.add_argument(
        "--index-type", type=str,
        default="hnsw",
        choices=["hnsw", "ivf", "exact"],
        help="ANN index type (default: hnsw)"
    )
    parser.add_argument(
        "--m", type=int,
        default=32,
        help="HNSW M parameter (default: 32)"
    )
    parser.add_argument(
        "--ef-construction", type=int,
        default=200,
        help="HNSW ef_construction parameter (default: 200)"
    )
    parser.add_argument(
        "--ef-search", type=int,
        default=100,
        help="HNSW ef_search parameter (default: 100)"
    )
    return parser.parse_args()


def build_faiss_index(game_vecs: np.ndarray, index_type: str = "hnsw", 
                     m: int = 32, ef_construction: int = 200) -> faiss.Index:
    """
    Faiss 인덱스 구축
    
    Args:
        game_vecs: 게임 벡터 배열
        index_type: 인덱스 타입 ("hnsw", "ivf", "exact")
        m: HNSW M 파라미터
        ef_construction: HNSW ef_construction 파라미터
    
    Returns:
        Faiss 인덱스
    """
    print(f"[INFO] Faiss {index_type.upper()} 인덱스 구축 중...")
    
    d = game_vecs.shape[1]  # 벡터 차원
    
    if index_type == "hnsw":
        # HNSW (Hierarchical Navigable Small World) 인덱스
        index = faiss.IndexHNSWFlat(d, m)
        index.hnsw.efConstruction = ef_construction
        index.hnsw.efSearch = ef_construction
        
    elif index_type == "ivf":
        # IVF (Inverted File) 인덱스
        nlist = min(100, game_vecs.shape[0] // 10)  # 클러스터 수
        quantizer = faiss.IndexFlatIP(d)
        index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_INNER_PRODUCT)
        
    else:  # exact
        # 정확한 검색 (선형 스캔)
        index = faiss.IndexFlatIP(d)
    
    # 벡터 정규화 (코사인 유사도용)
    game_vecs_norm = game_vecs.copy()
    faiss.normalize_L2(game_vecs_norm)
    
    # 인덱스에 벡터 추가
    if index_type == "ivf":
        index.train(game_vecs_norm)
    
    index.add(game_vecs_norm)
    
    print(f"   - 인덱스 타입: {index_type.upper()}")
    print(f"   - 벡터 수: {index.ntotal}")
    print(f"   - 벡터 차원: {d}")
    
    return index


def search_candidates(query_vector: np.ndarray, index: faiss.Index, 
                     top_n: int, ef_search: int = 100) -> Tuple[np.ndarray, np.ndarray]:
    """
    ANN 검색으로 후보 게임 찾기
    
    Args:
        query_vector: 쿼리 벡터
        index: Faiss 인덱스
        top_n: 검색할 후보 수
        ef_search: HNSW ef_search 파라미터
    
    Returns:
        (거리, 인덱스) 튜플
    """
    print(f"[INFO] ANN 검색 중 (Top-{top_n})...")
    
    # 쿼리 벡터 정규화
    query_norm = query_vector.copy().reshape(1, -1)
    faiss.normalize_L2(query_norm)
    
    # HNSW 파라미터 설정
    if hasattr(index, 'hnsw'):
        index.hnsw.efSearch = ef_search
    
    # 검색 실행
    distances, indices = index.search(query_norm, top_n)
    
    print(f"   - 검색된 후보 수: {len(indices[0])}")
    print(f"   - 최고 유사도: {1 - distances[0][0]:.4f}")
    print(f"   - 최저 유사도: {1 - distances[0][-1]:.4f}")
    
    return distances[0], indices[0]


def filter_candidates_by_constraints(candidates: List[Dict], constraints: Dict,
                                   game_data: Dict) -> List[Dict]:
    """
    제약조건으로 후보 필터링
    
    Args:
        candidates: 후보 게임 리스트
        constraints: 제약조건 딕셔너리
        game_data: 게임 메타데이터
    
    Returns:
        필터링된 후보 리스트
    """
    if not constraints:
        return candidates
    
    print("[INFO] 제약조건 필터링 중...")
    
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


def main(query_vector_path: str, game_vecs_path: str, index_path: str,
         output_path: str, top_n: int, index_type: str, m: int, 
         ef_construction: int, ef_search: int):
    print(f"[INFO] 후보 검색 시작:")
    print(f"   - 쿼리 벡터: {query_vector_path}")
    print(f"   - 게임 벡터: {game_vecs_path}")
    print(f"   - 검색 방식: {index_type.upper()}")
    print(f"   - Top-N: {top_n}")
    
    # 파일 존재 확인
    required_files = [query_vector_path, game_vecs_path, index_path]
    for file_path in required_files:
        if not Path(file_path).exists():
            print(f"[ERROR] 파일이 없습니다: {file_path}")
            return
    
    # 데이터 로드
    query_vector = np.load(query_vector_path)
    game_vecs = np.load(game_vecs_path)
    
    with open(index_path, 'r', encoding='utf-8') as f:
        index_maps = json.load(f)
    
    print(f"[INFO] 데이터 크기:")
    print(f"   - 쿼리 벡터: {query_vector.shape}")
    print(f"   - 게임 벡터: {game_vecs.shape}")
    
    # Faiss 인덱스 구축
    index = build_faiss_index(game_vecs, index_type, m, ef_construction)
    
    # ANN 검색
    distances, indices = search_candidates(query_vector, index, top_n, ef_search)
    
    # 후보 게임 정보 구성
    candidates = []
    row2appid = {int(k): v for k, v in index_maps['row2appid'].items()}
    
    for i, (distance, idx) in enumerate(zip(distances, indices)):
        if idx < len(game_vecs):  # 유효한 인덱스인지 확인
            game_id = row2appid.get(idx, f"unknown_{idx}")
            similarity = 1 - distance  # 거리를 유사도로 변환
            
            candidate = {
                'rank': i + 1,
                'game_id': game_id,
                'row_index': int(idx),
                'similarity': float(similarity),
                'distance': float(distance)
            }
            candidates.append(candidate)
    
    # 결과 구성
    result = {
        'search_info': {
            'index_type': index_type,
            'total_candidates': len(candidates),
            'query_vector_shape': query_vector.shape,
            'search_parameters': {
                'top_n': top_n,
                'm': m,
                'ef_construction': ef_construction,
                'ef_search': ef_search
            }
        },
        'candidates': candidates,
        'statistics': {
            'max_similarity': float(np.max([c['similarity'] for c in candidates])),
            'min_similarity': float(np.min([c['similarity'] for c in candidates])),
            'mean_similarity': float(np.mean([c['similarity'] for c in candidates])),
            'std_similarity': float(np.std([c['similarity'] for c in candidates]))
        }
    }
    
    # 출력 폴더 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 결과 저장
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 후보 검색 완료!")
    print(f"   - 저장: {output_path}")
    print(f"   - 후보 수: {len(candidates)}")
    
    # 상위 후보 출력
    print(f"\n[INFO] Top-10 후보:")
    for i, candidate in enumerate(candidates[:10]):
        print(f"   {i+1:2d}. 게임 {candidate['game_id']}: {candidate['similarity']:.4f}")


if __name__ == "__main__":
    args = _parse_args()
    main(args.query_vector, args.game_vecs, args.indexes, args.output,
         args.top_n, args.index_type, args.m, args.ef_construction, args.ef_search)
