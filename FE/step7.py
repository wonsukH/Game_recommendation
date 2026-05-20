import pandas as pd
import numpy as np
import argparse
from pathlib import Path
import json
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import Ridge
import os
from dotenv import load_dotenv
from langchain_upstage import UpstageEmbeddings

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 7: Text-to-tag alignment matrix")
    parser.add_argument(
        "--tag-vecs", type=str,
        default=str(Path("outputs/tag_vecs.npy")),
        help="Input tag vectors path (default: outputs/tag_vecs.npy)"
    )
    parser.add_argument(
        "--indexes", type=str,
        default=str(Path("outputs/index_maps.json")),
        help="Input index maps JSON path (default: outputs/index_maps.json)"
    )
    parser.add_argument(
        "--model", type=str,
        default="all-MiniLM-L6-v2",
        help="Sentence transformer model (default: all-MiniLM-L6-v2)"
    )
    parser.add_argument(
        "--lambda-reg", type=float,
        default=1e-2,
        help="Regularization lambda (default: 1e-2)"
    )
    parser.add_argument(
        "--tag-text", type=str,
        default=str(Path("outputs/tag_text_vecs.npy")),
        help="Output tag text vectors path (default: outputs/tag_text_vecs.npy)"
    )
    parser.add_argument(
        "--align", type=str,
        default=str(Path("outputs/W_align.npy")),
        help="Output alignment matrix path (default: outputs/W_align.npy)"
    )
    parser.add_argument(
        "--stats", type=str,
        default=str(Path("outputs/text_align_stats.json")),
        help="Output statistics JSON path (default: outputs/text_align_stats.json)"
    )
    return parser.parse_args()

def create_tag_texts(tag_names: list) -> list:
    """
    태그 이름을 문장으로 변환
    
    Args:
        tag_names: 태그 이름 리스트
    
    Returns:
        태그 문장 리스트
    """
    tag_texts = []
    
    for tag in tag_names:
        # 태그 이름을 문장으로 변환
        if tag.replace("-", " ").replace("_", " ").isalpha():
            # 단순 태그는 "This is a [tag] game" 형태로
            tag_text = f"This is a {tag.replace('-', ' ')} game"
        else:
            # 복잡한 태그는 그대로 사용
            tag_text = tag.replace("-", " ").replace("_", " ")
        
        tag_texts.append(tag_text)
    
    return tag_texts

def compute_alignment_matrix(T: np.ndarray, tag_vecs: np.ndarray, lambda_reg: float) -> np.ndarray:
    """
    정렬 행렬 계산: W = (T^T T + λI)^(-1) T^T tag_vecs
    
    Args:
        T: 태그 텍스트 임베딩 (태그 수 × 텍스트 차원)
        tag_vecs: 태그 벡터 (태그 수 × 임베딩 차원)
        lambda_reg: 정규화 파라미터
    
    Returns:
        정렬 행렬 W (텍스트 차원 × 임베딩 차원)
    """
    print("[INFO] 정렬 행렬 계산 중...")
    
    # Ridge 회귀로 해결
    ridge = Ridge(alpha=lambda_reg, fit_intercept=False)
    ridge.fit(T, tag_vecs)
    
    W = ridge.coef_.T  # (텍스트 차원 × 임베딩 차원)
    
    print(f"[INFO] 정렬 행렬 크기: {W.shape}")
    print(f"[INFO] Ridge R² 점수: {ridge.score(T, tag_vecs):.4f}")
    
    return W

def main(tag_vecs_path: str, index_path: str, model_name: str, lambda_reg: float,
         tag_text_path: str, align_path: str, stats_path: str):
    print(f"[INFO] 입력 파일 로드:")
    print(f"   - 태그 벡터: {tag_vecs_path}")
    print(f"   - 인덱스 맵: {index_path}")
    print(f"   - 문장 임베딩 모델: {model_name}")
    print(f"   - 정규화 lambda: {lambda_reg}")
    
    # 데이터 로드
    tag_vecs = np.load(tag_vecs_path)
    
    with open(index_path, 'r', encoding='utf-8') as f:
        index_maps = json.load(f)
    
    tag2idx = index_maps['tag2idx']
    idx2tag = {int(k): v for k, v in index_maps['idx2tag'].items()}
    
    # 태그 이름 정렬
    tag_names = [idx2tag[i] for i in range(len(idx2tag))]
    
    print(f"[INFO] 데이터 크기:")
    print(f"   - 태그 벡터: {tag_vecs.shape}")
    print(f"   - 태그 수: {len(tag_names)}")
    
    # 태그 텍스트 생성
    print("[INFO] 태그 텍스트 생성 중...")
    tag_texts = create_tag_texts(tag_names)

    # 문장 임베딩 모델 로드 및 임베딩 수행
    print(f"[INFO] 문장 임베딩 모델 로드 중: {model_name}")
    
    # 모델 종류에 따라 분기
    if "solar" in model_name:
        print("[INFO] Upstage API 모델을 사용합니다.")
        load_dotenv()
        api_key = os.environ.get("UPSTAGE_API_KEY")
        if not api_key:
            raise ValueError("UPSTAGE_API_KEY가 .env 파일에 설정되어야 합니다.")
        
        model = UpstageEmbeddings(model=model_name, api_key=api_key)
        
        print("[INFO] 태그 텍스트 임베딩 중 (Upstage API)...")
        T = np.array(model.embed_documents(tag_texts))
        
        print("[INFO] 정렬 행렬 테스트용 임베딩...")
        test_embedding = np.array(model.embed_query("action adventure game"))

    else:
        print("[INFO] SentenceTransformer 모델을 사용합니다.")
        model = SentenceTransformer(model_name)
        
        print("[INFO] 태그 텍스트 임베딩 중 (SentenceTransformer)...")
        T = model.encode(tag_texts, show_progress_bar=True)
        
        print("[INFO] 정렬 행렬 테스트용 임베딩...")
        test_embedding = model.encode(["action adventure game"])[0]

    print(f"[INFO] 텍스트 임베딩 크기: {T.shape}")
    
    # 정렬 행렬 계산
    W = compute_alignment_matrix(T, tag_vecs, lambda_reg)
    
    # 출력 폴더 생성
    Path(tag_text_path).parent.mkdir(parents=True, exist_ok=True)
    Path(align_path).parent.mkdir(parents=True, exist_ok=True)
    Path(stats_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 저장
    np.save(tag_text_path, T)
    np.save(align_path, W)
    
    # 통계 정보 저장
    stats = {
        "text_embedding_info": {
            "model": model_name,
            "text_embedding_dim": T.shape[1],
            "num_tags": T.shape[0]
        },
        "alignment_info": {
            "alignment_matrix_shape": W.shape,
            "lambda_reg": lambda_reg
        },
        "sample_tag_texts": {
            tag_names[i]: tag_texts[i] for i in range(min(10, len(tag_names)))
        }
    }
    
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 저장 완료:")
    print(f"   - 태그 텍스트 벡터: {tag_text_path}")
    print(f"   - 정렬 행렬: {align_path}")
    print(f"   - 통계 정보: {stats_path}")
    
    # 샘플 태그 텍스트 확인
    print(f"\n[INFO] 샘플 태그 텍스트 (처음 10개):")
    for i in range(min(10, len(tag_names))):
        print(f"   - {tag_names[i]}: '{tag_texts[i]}'")
    
    # 정렬 행렬 테스트
    print(f"\n[INFO] 정렬 행렬 테스트:")
    test_phrase = "action adventure game"
    # test_embedding is already calculated above
    predicted_tag_vec = test_embedding @ W
    
    # 가장 유사한 태그 찾기
    similarities = []
    for i, tag_vec in enumerate(tag_vecs):
        similarity = np.dot(predicted_tag_vec, tag_vec) / (np.linalg.norm(predicted_tag_vec) * np.linalg.norm(tag_vec))
        similarities.append((i, similarity))
    
    similarities.sort(key=lambda x: x[1], reverse=True)
    print(f"   - 테스트 문구: '{test_phrase}'")
    print(f"   - Top-5 유사 태그:")
    for i, (tag_idx, sim) in enumerate(similarities[:5]):
        tag_name = tag_names[tag_idx]
        print(f"     {i+1}. {tag_name}: {sim:.4f}")


if __name__ == "__main__":
    args = _parse_args()
    main(args.tag_vecs, args.indexes, args.model, args.lambda_reg,
         args.tag_text, args.align, args.stats)