import pandas as pd
import numpy as np
import argparse
from pathlib import Path
from scipy.sparse import csr_matrix, load_npz
from sklearn.preprocessing import StandardScaler
import json


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 6: Synthesize game vectors from tag vectors with β weights")
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
        "--tag-vecs", type=str,
        default=str(Path("outputs/tag_vecs.npy")),
        help="Input tag vectors path (default: outputs/tag_vecs.npy)"
    )
    parser.add_argument(
        "--tag-beta", type=str,
        default=str(Path("outputs/tag_beta.npy")),
        help="Input tag beta coefficients path (default: outputs/tag_beta.npy)"
    )
    parser.add_argument(
        "--output", type=str,
        default=str(Path("outputs/game_vecs.npy")),
        help="Output game vectors path (default: outputs/game_vecs.npy)"
    )
    parser.add_argument(
        "--stats", type=str,
        default=str(Path("outputs/game_vecs_stats.json")),
        help="Output statistics JSON path (default: outputs/game_vecs_stats.json)"
    )
    parser.add_argument(
        "--kappa", type=float,
        default=1.0,
        help="Softmax kappa parameter (default: 1.0)"
    )
    parser.add_argument(
        "--alpha", type=float,
        default=0.5,
        help="Tag count compensation alpha (default: 0.5)"
    )
    parser.add_argument(
        "--eta", type=float,
        default=0.2,
        help="β-axis steering eta (default: 0.2)"
    )
    return parser.parse_args()


def softmax_kappa(x: np.ndarray, kappa: float = 1.0) -> np.ndarray:
    """
    Softmax with kappa parameter
    
    Args:
        x: 입력 배열
        kappa: kappa 파라미터 (0.5~1.5)
    
    Returns:
        Softmax_kappa 적용된 배열
    """
    x_scaled = x / kappa
    exp_x = np.exp(x_scaled - np.max(x_scaled))  # 수치 안정성
    return exp_x / np.sum(exp_x)


def compute_beta_axis(tag_vecs: np.ndarray, tag_beta: np.ndarray) -> np.ndarray:
    """
    β-축 계산: d_β = normalize(Σ_t β_t · tag_vecs[t])
    
    Args:
        tag_vecs: 태그 임베딩 벡터
        tag_beta: 태그 효과 계수
    
    Returns:
        β-축 방향 벡터
    """
    # ReLU 적용
    beta_relu = np.maximum(tag_beta, 0)
    
    # β-축 계산
    d_beta = np.sum(beta_relu[:, np.newaxis] * tag_vecs, axis=0)
    
    # 정규화
    norm = np.linalg.norm(d_beta)
    if norm > 0:
        d_beta = d_beta / norm
    
    return d_beta


def synthesize_game_vectors(X: csr_matrix, tag_vecs: np.ndarray, tag_beta: np.ndarray, 
                          kappa: float = 1.0, alpha: float = 0.5, eta: float = 0.2) -> np.ndarray:
    """
    게임 벡터 합성: 원래 설명에 따른 구현
    
    Args:
        X: 게임×태그 이진 행렬 (sparse)
        tag_vecs: 태그 임베딩 벡터 (태그 수 × 임베딩 차원)
        tag_beta: 태그 효과 계수 (태그 수 × 1)
        kappa: softmax kappa 파라미터
        alpha: 태그 수 완충 파라미터
        eta: β-축 스티어링 파라미터
    
    Returns:
        게임 임베딩 벡터 (게임 수 × 임베딩 차원)
    """
    print("[INFO] 게임 벡터 합성 중...")
    
    num_games, num_tags = X.shape
    embedding_dim = tag_vecs.shape[1]
    
    print(f"[INFO] 합성 파라미터:")
    print(f"   - 게임 수: {num_games}")
    print(f"   - 태그 수: {num_tags}")
    print(f"   - 임베딩 차원: {embedding_dim}")
    print(f"   - kappa: {kappa}")
    print(f"   - alpha: {alpha}")
    print(f"   - eta: {eta}")
    
    # β-축 계산
    print("[INFO] β-축 계산 중...")
    d_beta = compute_beta_axis(tag_vecs, tag_beta)
    
    # ReLU 적용된 β 값들
    beta_relu = np.maximum(tag_beta, 0)
    max_beta = np.max(beta_relu) if np.max(beta_relu) > 0 else 1.0
    
    game_vecs = np.zeros((num_games, embedding_dim))
    
    for i in range(num_games):
        # 게임 i의 태그들
        game_tags = X[i, :].toarray().flatten()
        tag_indices = np.where(game_tags > 0)[0]
        
        if len(tag_indices) == 0:
            # 태그가 없는 게임은 0 벡터
            continue
        
        # 해당 게임의 태그 효과들
        game_betas = beta_relu[tag_indices]
        
        # 6-1) 게임별 태그 가중치 계산
        # b_t = ReLU(β_t) (이미 위에서 계산됨)
        # a_{g,t} = softmax_kappa(b_t / max(b))
        normalized_betas = game_betas / max_beta
        weights = softmax_kappa(normalized_betas, kappa)
        
        # 태그 수 완충 (선택사항)
        tag_count = len(tag_indices)
        if tag_count > 1 and alpha > 0:
            weights = weights / (tag_count ** alpha)
        
        # 6-2) 게임 벡터 합성
        # v_g = normalize(Σ_{t∈T_g} a_{g,t} · tag_vecs[t])
        game_tag_vecs = tag_vecs[tag_indices, :]
        game_vec = np.average(game_tag_vecs, axis=0, weights=weights)
        
        # 정규화
        norm = np.linalg.norm(game_vec)
        if norm > 0:
            game_vec = game_vec / norm
        
        # β-축 스티어링 (선택사항)
        if eta > 0:
            # v_g ← normalize(v_g + η · ⟨v_g, d_β⟩ · d_β)
            dot_product = np.dot(game_vec, d_beta)
            game_vec = game_vec + eta * dot_product * d_beta
            
            # 다시 정규화
            norm = np.linalg.norm(game_vec)
            if norm > 0:
                game_vec = game_vec / norm
        
        game_vecs[i, :] = game_vec
    
    print(f"[INFO] 합성 완료:")
    print(f"   - 게임 벡터 크기: {game_vecs.shape}")
    print(f"   - 평균 L2 노름: {np.mean(np.linalg.norm(game_vecs, axis=1)):.4f}")
    print(f"   - 0 벡터 게임 수: {np.sum(np.all(game_vecs == 0, axis=1))}")
    
    return game_vecs


def main(matrix_path: str, index_path: str, tag_vecs_path: str, tag_beta_path: str,
         output_path: str, stats_path: str, kappa: float, alpha: float, eta: float):
    print(f"[INFO] 입력 파일 로드:")
    print(f"   - CSR 행렬: {matrix_path}")
    print(f"   - 인덱스 맵: {index_path}")
    print(f"   - 태그 벡터: {tag_vecs_path}")
    print(f"   - 태그 효과: {tag_beta_path}")
    print(f"   - kappa: {kappa}, alpha: {alpha}, eta: {eta}")
    
    # 데이터 로드
    X = load_npz(matrix_path)
    tag_vecs = np.load(tag_vecs_path)
    tag_beta = np.load(tag_beta_path)
    
    with open(index_path, 'r', encoding='utf-8') as f:
        index_maps = json.load(f)
    
    tag2idx = index_maps['tag2idx']
    idx2tag = {int(k): v for k, v in index_maps['idx2tag'].items()}
    row2appid = {int(k): v for k, v in index_maps['row2appid'].items()}
    
    print(f"[INFO] 데이터 크기:")
    print(f"   - 게임×태그 행렬: {X.shape}")
    print(f"   - 태그 벡터: {tag_vecs.shape}")
    print(f"   - 태그 효과: {tag_beta.shape}")
    print(f"   - 태그 수: {len(tag2idx)}")
    
    # 크기 일치 확인
    if X.shape[1] != tag_vecs.shape[0] or X.shape[1] != len(tag_beta):
        print(f"[ERROR] 태그 수가 일치하지 않습니다:")
        print(f"   - CSR 행렬 태그 수: {X.shape[1]}")
        print(f"   - 태그 벡터 태그 수: {tag_vecs.shape[0]}")
        print(f"   - 태그 효과 태그 수: {len(tag_beta)}")
        return
    
    # 게임 벡터 합성
    game_vecs = synthesize_game_vectors(X, tag_vecs, tag_beta, kappa, alpha, eta)
    
    # 출력 폴더 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(stats_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 게임 벡터 저장
    np.save(output_path, game_vecs)
    
    # 통계 정보 저장
    stats = {
        "game_vectors_info": {
            "shape": game_vecs.shape,
            "embedding_dim": game_vecs.shape[1],
            "num_games": game_vecs.shape[0]
        },
        "synthesis_parameters": {
            "kappa": kappa,
            "alpha": alpha,
            "eta": eta,
            "tag_count_compensation": alpha > 0,
            "beta_axis_steering": eta > 0
        },
        "vector_stats": {
            "mean_norm": float(np.mean(np.linalg.norm(game_vecs, axis=1))),
            "std_norm": float(np.std(np.linalg.norm(game_vecs, axis=1))),
            "min_norm": float(np.min(np.linalg.norm(game_vecs, axis=1))),
            "max_norm": float(np.max(np.linalg.norm(game_vecs, axis=1))),
            "zero_vectors": int(np.sum(np.all(game_vecs == 0, axis=1)))
        },
        "input_info": {
            "matrix_shape": X.shape,
            "tag_vecs_shape": tag_vecs.shape,
            "tag_beta_shape": tag_beta.shape
        }
    }
    
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 저장 완료:")
    print(f"   - 게임 벡터: {output_path}")
    print(f"   - 통계 정보: {stats_path}")
    print(f"   - 벡터 크기: {game_vecs.shape}")
    
    # 샘플 게임 벡터 확인
    print(f"\n[INFO] 샘플 게임 벡터 (처음 5개 게임):")
    for i in range(min(5, game_vecs.shape[0])):
        game_id = row2appid[i]
        game_vec = game_vecs[i]
        norm = np.linalg.norm(game_vec)
        print(f"   - 게임 {game_id}: 노름={norm:.4f}, 벡터=[{game_vec[0]:.4f}, {game_vec[1]:.4f}, ..., {game_vec[-1]:.4f}]")
    
    # 코사인 유사도 계산 예시
    print(f"\n[INFO] 코사인 유사도 계산 예시 (게임 0과 다른 게임들):")
    if game_vecs.shape[0] > 1:
        game_0_vec = game_vecs[0]
        similarities = []
        for i in range(1, min(6, game_vecs.shape[0])):
            game_i_vec = game_vecs[i]
            similarity = np.dot(game_0_vec, game_i_vec) / (np.linalg.norm(game_0_vec) * np.linalg.norm(game_i_vec))
            similarities.append((i, similarity))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        for i, (game_idx, sim) in enumerate(similarities):
            game_id = row2appid[game_idx]
            print(f"   {i+1}. 게임 {game_id}: 유사도={sim:.4f}")


if __name__ == "__main__":
    args = _parse_args()
    main(args.matrix, args.indexes, args.tag_vecs, args.tag_beta,
         args.output, args.stats, args.kappa, args.alpha, args.eta)
