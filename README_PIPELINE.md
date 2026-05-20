# 🎮 게임 추천 시스템 파이프라인 (Step 1-9)

## 📋 개요
Steam 게임 데이터를 활용한 다단계 임베딩 기반 게임 추천 시스템을 구축했습니다. 태그 정규화부터 품질 점검까지 총 9단계로 구성되어 있습니다.

---

## 🚀 전체 파이프라인 구조

```
Step 1: 태그 정규화 → Step 2: Game×Tag 행렬 → Step 3: 게임 점수 정규화
    ↓
Step 4: 태그 임베딩 학습 → Step 5: 태그 효과 학습 → Step 6: 게임 벡터 합성
    ↓
Step 7: 텍스트→태그 정렬 → Step 8: 메타데이터 관리 → Step 9: 품질 점검
```

---

## 📁 입력 파일 구조
```
outputs/
├── steam_games_tags.csv          # 게임-태그 데이터
├── user_game_scores.csv          # 게임 점수 데이터
└── user_all_reviews.csv          # 사용자 리뷰 데이터
```

---

## 🔧 각 단계별 상세 설명

### **Step 1: 태그 정규화** (`step1.py`)
**목적**: 태그 이름을 표준화하고 별칭 매핑 생성
- **입력**: `steam_games_tags.csv`
- **출력**: `tag_vocab.json`
- **주요 기능**:
  - 태그 이름 정규화 (소문자, 공백/하이픈 통일)
  - 별칭 매핑 적용
  - 태그 빈도 통계 생성

```bash
python step1.py
```

### **Step 2: Game×Tag 이진 행렬** (`step2.py`)
**목적**: 게임-태그 관계를 희소 행렬로 변환
- **입력**: `steam_games_tags.csv`, `tag_vocab.json`
- **출력**: `X_game_tag_csr.npz`, `index_maps.json`
- **주요 기능**:
  - CSR(Compressed Sparse Row) 형식 행렬 생성
  - 게임 ID ↔ 행 인덱스 매핑
  - 태그 이름 ↔ 열 인덱스 매핑

```bash
python step2.py
```

### **Step 3: 게임 점수 정규화** (`step3.py`)
**목적**: 게임 점수를 가중치로 변환
- **입력**: `user_game_scores.csv`
- **출력**: `game_weight.npy`, `game_weight_stats.json`
- **주요 기능**:
  - Min-Max 정규화
  - Gamma 보정 (기본값: 0.5)
  - 게임별 평균 점수 계산

```bash
python step3.py --gamma 0.5
```

### **Step 4: 태그 임베딩 학습** (`step4.py`)
**목적**: 태그 간 의미적 관계 학습
- **입력**: `X_game_tag_csr.npz`, `game_weight.npy`
- **출력**: `tag_vecs.npy`, `tag_embedding_stats.json`
- **주요 기능**:
  - PPMI(Positive Pointwise Mutual Information) 계산
  - Truncated SVD로 128차원 임베딩 생성
  - 게임 점수 가중치 반영

```bash
python step4.py --dim 128
```

### **Step 5: 태그 효과 학습** (`step5.py`)
**목적**: 각 태그가 게임 점수에 미치는 영향 학습
- **입력**: `X_game_tag_csr.npz`, `user_game_scores.csv`
- **출력**: `tag_beta.npy`, `tag_beta_stats.json`
- **주요 기능**:
  - Ridge 회귀로 태그별 β 계수 학습
  - R² 점수로 모델 성능 평가
  - 태그 효과 순위 분석

```bash
python step5.py --alpha 1.0
```

### **Step 6: 게임 벡터 합성** (`step6.py`)
**목적**: 최종 게임 임베딩 벡터 생성
- **입력**: `tag_vecs.npy`, `tag_beta.npy`, `X_game_tag_csr.npz`
- **출력**: `game_vecs.npy`, `game_vecs_stats.json`
- **주요 기능**:
  - 태그 벡터의 가중 평균 계산
  - Softmax 정규화 (κ 파라미터)
  - 태그 수 보정 (α 파라미터)
  - β-축 스티어링 (η 파라미터)

```bash
python step6.py --kappa 1.0 --alpha 0.5 --eta 0.2
```

### **Step 7: 텍스트→태그 정렬** (`step7.py`)
**목적**: 자연어 입력을 태그 공간으로 매핑
- **입력**: `tag_vecs.npy`, `index_maps.json`
- **출력**: `tag_text_vecs.npy`, `W_align.npy`
- **주요 기능**:
  - Sentence Transformer로 태그 텍스트 임베딩
  - Ridge 회귀로 정렬 행렬 학습
  - 자연어 쿼리 → 태그 벡터 변환

```bash
python step7.py --lambda-reg 0.01
```

### **Step 8: 메타데이터 관리** (`step8.py`)
**목적**: 버전 관리 및 파라미터 추적
- **입력**: 모든 출력 파일들
- **출력**: 버전별 파일들, `params_v*.json`, `metadata_v*.json`
- **주요 기능**:
  - 파일 버전 관리
  - 파라미터 기록
  - 백업 생성
  - 메타데이터 요약

```bash
python step8.py --version v1 --backup
```

### **Step 9: 품질 점검** (`step9.py`)
**목적**: 시스템 성능 및 품질 평가
- **입력**: `tag_vecs.npy`, `game_vecs.npy`, `tag_beta.npy`
- **출력**: `quality_report.json`
- **주요 기능**:
  - 태그 이웃 스팟체크
  - 게임 유사도 스팟체크
  - 허브니스 분석
  - 회귀 적합도 평가

```bash
python step9.py --top-k 10
```

---

## 📊 최종 산출물

### **핵심 임베딩 파일**
- `tag_vecs.npy`: 태그 임베딩 벡터 (393×128)
- `game_vecs.npy`: 게임 임베딩 벡터 (1031×128)
- `tag_beta.npy`: 태그 효과 계수 (393,)

### **정렬 및 매핑 파일**
- `W_align.npy`: 텍스트→태그 정렬 행렬
- `tag_text_vecs.npy`: 태그 텍스트 임베딩
- `index_maps.json`: 인덱스 매핑 정보

### **통계 및 메타데이터**
- `*_stats.json`: 각 단계별 통계 정보
- `params_v*.json`: 파라미터 기록
- `metadata_v*.json`: 메타데이터 요약
- `quality_report.json`: 품질 점검 결과

---

## 🎯 사용 방법

### **전체 파이프라인 실행**
```bash
# 순서대로 실행
python step1.py
python step2.py
python step3.py
python step4.py
python step5.py
python step6.py
python step7.py
python step8.py --version v1 --backup
python step9.py
```

### **게임 추천 사용 예시**
```python
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# 게임 벡터 로드
game_vecs = np.load('outputs/game_vecs.npy')
index_maps = json.load(open('outputs/index_maps.json'))

# 특정 게임과 유사한 게임 찾기
game_idx = 0  # 첫 번째 게임
similarities = cosine_similarity([game_vecs[game_idx]], game_vecs)[0]
top_similar = np.argsort(similarities)[::-1][1:11]  # Top-10

# 결과 출력
for i, similar_idx in enumerate(top_similar):
    game_id = index_maps['row2appid'][str(similar_idx)]
    print(f"{i+1}. 게임 {game_id}: {similarities[similar_idx]:.4f}")
```

### **자연어 쿼리 사용 예시**
```python
from sentence_transformers import SentenceTransformer

# 정렬 행렬 로드
W_align = np.load('outputs/W_align.npy')
model = SentenceTransformer('all-MiniLM-L6-v2')

# 자연어 쿼리
query = "action adventure game"
query_embedding = model.encode([query])[0]
predicted_tag_vec = query_embedding @ W_align

# 유사한 태그 찾기
tag_vecs = np.load('outputs/tag_vecs.npy')
similarities = cosine_similarity([predicted_tag_vec], tag_vecs)[0]
top_tags = np.argsort(similarities)[::-1][:5]
```

---

## 🔧 주요 파라미터

| 단계 | 파라미터 | 기본값 | 설명 |
|------|----------|--------|------|
| Step 3 | `--gamma` | 0.5 | 점수 정규화 감마 값 |
| Step 4 | `--dim` | 128 | 임베딩 차원 |
| Step 5 | `--alpha` | 1.0 | Ridge 정규화 강도 |
| Step 6 | `--kappa` | 1.0 | Softmax 온도 |
| Step 6 | `--alpha` | 0.5 | 태그 수 보정 계수 |
| Step 6 | `--eta` | 0.2 | β-축 스티어링 강도 |
| Step 7 | `--lambda-reg` | 0.01 | 정렬 행렬 정규화 |

---

## 📈 성능 지표

### **데이터 규모**
- **게임 수**: 1,031개
- **태그 수**: 393개
- **임베딩 차원**: 128차원
- **평균 게임당 태그**: ~8.2개

### **품질 지표**
- **태그 임베딩**: PPMI + SVD 기반 의미적 유사도
- **게임 임베딩**: 태그 효과 가중 평균
- **회귀 성능**: Ridge R² 점수로 평가
- **허브니스**: 코사인 유사도 분포 분석

---

## 🚨 주의사항

1. **의존성 설치**: `pip install -r requirements.txt`
2. **메모리 요구사항**: 최소 4GB RAM 권장
3. **실행 순서**: Step 1-9 순서대로 실행 필수
4. **파일 경로**: 모든 파일은 `outputs/` 디렉토리에 저장
5. **버전 관리**: Step 8로 정기적인 백업 권장

---

