import argparse
import ast
import json
import os
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import Ridge

from pipeline.game_rec.config import load_config
from pipeline.game_rec.io import load_index_maps, save_stats


# ─── M9.A helpers: description-augmented W_align training ──────────────────
# W_align는 "자연어 → tag space" projection. 학습 데이터를 짧은 태그 wrapper
# 문장 447개에서 9956개 게임 description까지 늘리되, target은 항상 tag space에
# 머무름 (target = 그 게임의 top-5 vote 태그의 vote-weighted 평균 tag_vec).
# 정체성(태그 기반 추천) 유지하면서 niche cluster bias 약화.


def _normalize_tag_for_lookup(tag: str) -> str:
    """build_games_tags_csv.py / tag_vocab.py와 동일한 정규화 규칙."""
    t = unicodedata.normalize("NFKC", str(tag)).lower().strip()
    t = re.sub(r"[/\s]+", "-", t)
    t = re.sub(r"-+", "-", t)
    return t


def _parse_tags_json(raw) -> dict:
    """tags_json 컬럼이 JSON string 또는 python literal 둘 다 처리."""
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        try:
            v = ast.literal_eval(raw)
            return v if isinstance(v, dict) else {}
        except (ValueError, SyntaxError):
            return {}


def _build_description_targets(
    steamspy_path: Path, appdetails_path: Path, tag_vecs: np.ndarray, tag2idx: dict, top_k: int = 5
) -> tuple[list[str], np.ndarray]:
    """Return (descriptions, Y_game) for W_align augmentation.

    각 게임:
      - input: short_description (자연어)
      - target: top-k vote 태그의 vote-weighted 평균 tag_vec (tag space 안)
    유효 태그(vocab에 있고 vote >0)가 1개 이상인 게임만 포함.
    """
    spy = pd.read_csv(steamspy_path)[["appid", "tags_json"]]
    meta = pd.read_csv(appdetails_path)[["appid", "short_description"]]
    merged = meta.merge(spy, on="appid")
    merged = merged[merged["short_description"].notna() & (merged["short_description"].astype(str).str.strip() != "")]

    descriptions: list[str] = []
    Y_game: list[np.ndarray] = []
    skipped = 0
    for _, row in merged.iterrows():
        tags_dict = _parse_tags_json(row["tags_json"])
        valid = []
        for tag, vote in tags_dict.items():
            try:
                v = int(vote)
            except (TypeError, ValueError):
                continue
            if v <= 0:
                continue
            norm = _normalize_tag_for_lookup(tag)
            if norm in tag2idx:
                valid.append((tag2idx[norm], v))
        if not valid:
            skipped += 1
            continue
        valid.sort(key=lambda x: -x[1])
        top = valid[:top_k]
        weights = np.array([v for _, v in top], dtype=np.float32)
        weights /= weights.sum()
        avg = sum(w * tag_vecs[idx] for (idx, _), w in zip(top, weights))
        Y_game.append(avg.astype(np.float32))
        descriptions.append(str(row["short_description"]))

    print(f"[INFO] description augmentation: kept {len(descriptions)}, skipped {skipped}")
    return descriptions, np.array(Y_game, dtype=np.float32)


def _parse_args() -> argparse.Namespace:
    cfg = load_config()["models"]["text_alignment"]
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
        default=cfg["text_model"],
        help=f"Embedding model — supports SentenceTransformer or Google Gemini (default from config: {cfg['text_model']})"
    )
    parser.add_argument(
        "--lambda-reg", type=float,
        default=cfg["lambda_reg"],
        help=f"Regularization lambda (default from config: {cfg['lambda_reg']})"
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
    parser.add_argument(
        "--include-descriptions",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="(M9.A) Augment W_align training with game descriptions. "
             "Target stays in tag space (vote-weighted mean of top-5 tag_vecs). "
             "Use --no-include-descriptions for original tag-only training.",
    )
    parser.add_argument(
        "--steamspy-path", type=str,
        default=str(Path("outputs/steamspy_games.csv")),
        help="(M9.A) SteamSpy CSV with per-game tag votes",
    )
    parser.add_argument(
        "--appdetails-path", type=str,
        default=str(Path("outputs/steam_appdetails.csv")),
        help="(M9.A) Steam appdetails CSV with game descriptions",
    )
    parser.add_argument(
        "--description-top-k", type=int, default=5,
        help="(M9.A) Top-K vote tags per game for target weighted-mean (default 5)",
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
         tag_text_path: str, align_path: str, stats_path: str,
         include_descriptions: bool = True,
         steamspy_path: str = "outputs/steamspy_games.csv",
         appdetails_path: str = "outputs/steam_appdetails.csv",
         description_top_k: int = 5):
    print(f"[INFO] 입력 파일 로드:")
    print(f"   - 태그 벡터: {tag_vecs_path}")
    print(f"   - 인덱스 맵: {index_path}")
    print(f"   - 문장 임베딩 모델: {model_name}")
    print(f"   - 정규화 lambda: {lambda_reg}")
    
    # 데이터 로드
    tag_vecs = np.load(tag_vecs_path)

    index_maps = load_index_maps(index_path)
    tag2idx = index_maps['tag2idx']
    idx2tag = index_maps['idx2tag']
    
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
    if "gemini" in model_name.lower() or model_name.startswith("models/"):
        print("[INFO] Google Gemini API 모델을 사용합니다.")
        load_dotenv()
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 .env 파일에 설정되어야 합니다.")

        model = GoogleGenerativeAIEmbeddings(model=model_name, google_api_key=api_key)

        print("[INFO] 태그 텍스트 임베딩 중 (Gemini API)...")
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

    print(f"[INFO] 태그 wrapper 임베딩 크기: {T.shape}")

    # ─── M9.A: description augmentation (input 늘리고 target은 tag space 유지) ───
    n_tag_samples = T.shape[0]
    n_game_samples = 0
    if include_descriptions:
        spy_p = Path(steamspy_path)
        meta_p = Path(appdetails_path)
        if not (spy_p.exists() and meta_p.exists()):
            print(f"[WARN] description augmentation skipped: missing {spy_p} or {meta_p}")
        else:
            print(f"[INFO] (M9.A) description augmentation 시작 — top-{description_top_k} vote 태그 가중평균을 target으로")
            descriptions, Y_game = _build_description_targets(
                spy_p, meta_p, tag_vecs, tag2idx, top_k=description_top_k
            )
            if len(descriptions) > 0:
                print(f"[INFO] description 임베딩 중 ({len(descriptions)}개)...")
                # 같은 model로 description 임베딩
                if "gemini" in model_name.lower() or model_name.startswith("models/"):
                    T_game = np.array(model.embed_documents(descriptions))
                else:
                    T_game = model.encode(descriptions, show_progress_bar=True)
                print(f"[INFO] description 임베딩 크기: {T_game.shape}")

                # 결합: input augmented, target은 둘 다 tag space (128d)
                T = np.vstack([T, T_game.astype(T.dtype)])
                Y_combined = np.vstack([tag_vecs, Y_game.astype(tag_vecs.dtype)])
                n_game_samples = len(descriptions)
                print(f"[INFO] 결합 후 학습 데이터: T={T.shape}, Y={Y_combined.shape}")
            else:
                Y_combined = tag_vecs
    else:
        Y_combined = tag_vecs

    # 정렬 행렬 계산 — target은 tag space (단일 태그 또는 가중평균, 둘 다 128d)
    W = compute_alignment_matrix(T, Y_combined, lambda_reg)
    
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
            "num_tags": n_tag_samples,
            "num_game_descriptions": n_game_samples,
            "total_training_samples": T.shape[0],
        },
        "alignment_info": {
            "alignment_matrix_shape": W.shape,
            "lambda_reg": lambda_reg,
            "include_descriptions": include_descriptions,
            "description_top_k": description_top_k if include_descriptions else None,
        },
        "sample_tag_texts": {
            tag_names[i]: tag_texts[i] for i in range(min(10, len(tag_names)))
        }
    }
    
    save_stats(stats, stats_path)
    
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
         args.tag_text, args.align, args.stats,
         include_descriptions=args.include_descriptions,
         steamspy_path=args.steamspy_path,
         appdetails_path=args.appdetails_path,
         description_top_k=args.description_top_k)