import pandas as pd
import numpy as np
import argparse
from pathlib import Path
from scipy.sparse import csr_matrix, load_npz
from sklearn.decomposition import TruncatedSVD
import json


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 4: Tag embedding learning with PPMI + SVD")
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
        "--weights", type=str,
        default=str(Path("outputs/game_weight.npy")),
        help="Input game weights path (default: outputs/game_weight.npy)"
    )
    parser.add_argument(
        "--output", type=str,
        default=str(Path("outputs/tag_vecs.npy")),
        help="Output tag vectors path (default: outputs/tag_vecs.npy)"
    )
    parser.add_argument(
        "--dim", type=int,
        default=128,
        help="Embedding dimension (default: 128)"
    )
    parser.add_argument(
        "--stats", type=str,
        default=str(Path("outputs/tag_embedding_stats.json")),
        help="Output statistics JSON path (default: outputs/tag_embedding_stats.json)"
    )
    return parser.parse_args()


def compute_ppmi_matrix(X: csr_matrix, game_weights: np.ndarray) -> csr_matrix:
    """
    게임 가중치를 반영한 PPMI 행렬 계산
    
    Args:
        X: 게임×태그 이진 행렬 (sparse)
        game_weights: 게임별 가중치 배열 (√s)
    
    Returns:
        PPMI 행렬 (sparse)
    """
    print("[INFO] 공존 행렬 계산 중...")
    
    # 게임 가중치를 대각 행렬로 변환
    W = np.sqrt(game_weights)  # √s 적용
    W_diag = csr_matrix((W, (np.arange(len(W)), np.arange(len(W)))), shape=(len(W), len(W)))
    
    # 가중치가 적용된 게임×태그 행렬: X_weighted = W * X
    X_weighted = W_diag @ X
    
    # 공존 행렬: C = X_weighted^T * X_weighted
    C = X_weighted.T @ X_weighted
    
    print(f"[INFO] 공존 행렬 크기: {C.shape}")
    print(f"[INFO] 공존 행렬 밀도: {C.nnz / (C.shape[0] * C.shape[1]):.6f}")
    
    # PMI 계산을 위한 확률 분포
    total_cooccurrences = C.sum()
    row_sums = np.array(C.sum(axis=1)).flatten()
    col_sums = np.array(C.sum(axis=0)).flatten()
    
    # PMI = log(P(x,y) / (P(x) * P(y)))
    # P(x,y) = C[x,y] / total
    # P(x) = row_sums[x] / total
    # P(y) = col_sums[y] / total
    
    print("[INFO] PMI 계산 중...")
    
    # 희소 행렬에서 PMI 계산
    rows, cols, data = [], [], []
    
    for i in range(C.shape[0]):
        for j in range(C.shape[1]):
            if C[i, j] > 0:  # 공존이 있는 경우만
                p_xy = C[i, j] / total_cooccurrences
                p_x = row_sums[i] / total_cooccurrences
                p_y = col_sums[j] / total_cooccurrences
                
                if p_x > 0 and p_y > 0:
                    pmi = np.log(p_xy / (p_x * p_y))
                    ppmi = max(0, pmi)  # PPMI: 음수는 0으로
                    
                    if ppmi > 0:
                        rows.append(i)
                        cols.append(j)
                        data.append(ppmi)
    
    # PPMI 행렬 생성
    ppmi_matrix = csr_matrix((data, (rows, cols)), shape=C.shape)
    
    print(f"[INFO] PPMI 행렬 밀도: {ppmi_matrix.nnz / (ppmi_matrix.shape[0] * ppmi_matrix.shape[1]):.6f}")
    
    return ppmi_matrix


def main(matrix_path: str, index_path: str, weight_path: str, output_path: str, dim: int, stats_path: str):
    print(f"[INFO] 입력 파일 로드:")
    print(f"   - CSR 행렬: {matrix_path}")
    print(f"   - 인덱스 맵: {index_path}")
    print(f"   - 게임 가중치: {weight_path}")
    
    # 데이터 로드
    X = load_npz(matrix_path)
    game_weights = np.load(weight_path)
    
    with open(index_path, 'r', encoding='utf-8') as f:
        index_maps = json.load(f)
    
    tag2idx = index_maps['tag2idx']
    idx2tag = {int(k): v for k, v in index_maps['idx2tag'].items()}
    appid2row = {int(k): v for k, v in index_maps['appid2row'].items()}
    row2appid = {int(k): v for k, v in index_maps['row2appid'].items()}
    
    print(f"[INFO] 데이터 크기:")
    print(f"   - 게임×태그 행렬: {X.shape}")
    print(f"   - 게임 가중치: {game_weights.shape}")
    print(f"   - 태그 수: {len(tag2idx)}")
    
    # 게임 수 일치 확인 및 필터링
    if X.shape[0] != len(game_weights):
        print(f"[WARNING] 게임 수가 일치하지 않습니다: 행렬={X.shape[0]}, 가중치={len(game_weights)}")
        print("[INFO] CSR 행렬에 있는 게임만 사용하여 가중치를 필터링합니다.")
        
        # CSR 행렬에 있는 게임 ID들
        csr_game_ids = set(row2appid.values())
        
        # 가중치 파일에서 게임 ID 정보를 가져오기 위해 user_game_scores.csv 로드
        try:
            scores_df = pd.read_csv("outputs/user_game_scores.csv")
            weight_game_ids = scores_df['appid'].unique()
            
            # 교집합 계산
            common_game_ids = csr_game_ids.intersection(set(weight_game_ids))
            print(f"[INFO] 공통 게임 수: {len(common_game_ids)}")
            
            # 가중치를 공통 게임에 맞게 필터링
            filtered_weights = []
            for game_id in sorted(csr_game_ids):
                if game_id in weight_game_ids:
                    # 해당 게임의 평균 점수 가중치 찾기
                    game_weight = scores_df[scores_df['appid'] == game_id]['s_round10_rec'].mean()
                    filtered_weights.append(game_weight)
                else:
                    # 가중치가 없는 게임은 기본값 0.5 사용
                    filtered_weights.append(0.5)
            
            game_weights = np.array(filtered_weights)
            print(f"[INFO] 필터링된 가중치 크기: {game_weights.shape}")
            
        except Exception as e:
            print(f"[ERROR] 가중치 필터링 중 오류 발생: {e}")
            print("[INFO] 모든 게임에 동일한 가중치 1.0을 적용합니다.")
            game_weights = np.ones(X.shape[0])
    
    # PPMI 행렬 계산
    ppmi_matrix = compute_ppmi_matrix(X, game_weights)
    
    # TruncatedSVD 적용
    print(f"[INFO] TruncatedSVD 적용 중 (d={dim})...")
    svd = TruncatedSVD(n_components=dim, random_state=42)
    tag_embeddings = svd.fit_transform(ppmi_matrix)
    
    print(f"[INFO] SVD 결과:")
    print(f"   - 설명된 분산 비율: {svd.explained_variance_ratio_.sum():.4f}")
    print(f"   - 특이값 개수: {len(svd.singular_values_)}")
    print(f"   - 최대 특이값: {svd.singular_values_[0]:.4f}")
    print(f"   - 최소 특이값: {svd.singular_values_[-1]:.4f}")
    
    # 출력 폴더 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(stats_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 태그 임베딩 저장
    np.save(output_path, tag_embeddings)
    
    # 통계 정보 저장
    stats = {
        "embedding_info": {
            "shape": tag_embeddings.shape,
            "dimension": dim,
            "num_tags": len(tag2idx)
        },
        "svd_info": {
            "explained_variance_ratio": float(svd.explained_variance_ratio_.sum()),
            "singular_values": svd.singular_values_.tolist(),
            "components_shape": svd.components_.shape
        },
        "ppmi_info": {
            "matrix_shape": ppmi_matrix.shape,
            "density": float(ppmi_matrix.nnz / (ppmi_matrix.shape[0] * ppmi_matrix.shape[1])),
            "max_value": float(ppmi_matrix.max()),
            "min_value": float(ppmi_matrix.min())
        },
        "parameters": {
            "embedding_dim": dim,
            "random_state": 42
        }
    }
    
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 저장 완료:")
    print(f"   - 태그 임베딩: {output_path}")
    print(f"   - 통계 정보: {stats_path}")
    print(f"   - 임베딩 크기: {tag_embeddings.shape}")
    
    # 샘플 태그 임베딩 확인
    print(f"\n[INFO] 샘플 태그 임베딩 (처음 5개 태그):")
    for i in range(min(5, len(idx2tag))):
        tag_name = idx2tag[i]
        embedding = tag_embeddings[i]
        print(f"   - {tag_name}: [{embedding[0]:.4f}, {embedding[1]:.4f}, ..., {embedding[-1]:.4f}]")


if __name__ == "__main__":
    args = _parse_args()
    main(args.matrix, args.indexes, args.weights, args.output, args.dim, args.stats)
