# 온라인 서빙 파이프라인 (Online Serving Pipeline)

이 문서는 게임 추천 시스템의 온라인 서빙 파이프라인(Step 10-15)에 대한 설명입니다.

## 📋 파이프라인 개요

온라인 서빙 파이프라인은 사용자의 실시간 요청을 처리하여 개인화된 게임 추천을 제공하는 시스템입니다.

### 파이프라인 단계
1. **Step 10**: LLM 의도 파싱 (Intent Parsing)
2. **Step 11**: 쿼리 벡터 생성 (Query Vector Generation)
3. **Step 12**: 후보 검색 (Candidate Search with ANN)
4. **Step 13**: 필터 & 스코어링 (Filter & Scoring)
5. **Step 14**: 다양성 선택 (Diversity Selection with MMR)
6. **Step 15**: LLM 설명 생성 (Explanation Generation)

## 📁 필수 파일 구조

### 기본 입력 파일들
```
outputs/
├── tag_vocab.json              # 태그 사전 (Step 1에서 생성)
├── index_maps.json             # 인덱스 매핑 (Step 1에서 생성)
├── game_vecs.npy               # 게임 벡터 (Step 2에서 생성)
├── tag_vecs.npy                # 태그 벡터 (Step 2에서 생성)
├── W_align.npy                 # 정렬 행렬 (Step 3에서 생성)
├── X_game_tag_csr.npz          # 게임-태그 행렬 (Step 1에서 생성)
└── game_weight.npy             # 게임 가중치 (Step 1에서 생성)
```

### 사용자 입력 파일
```
user_intent.json                # 사용자 의도 (사용자가 제공)
```

## 🚀 단계별 실행 가이드

### Step 10: LLM 의도 파싱
**목적**: 사용자의 자연어 의도를 구조화된 데이터로 변환

**필수 파일**:
- `user_intent.json` (사용자 입력)
- `outputs/tag_vocab.json`
- `outputs/index_maps.json`

**실행 명령**:
```bash
python step10.py
```

**출력 파일**:
- `outputs/parsed_intent.json`

**사용자 의도 파일 예시**:
```json
{
  "mode": "similar",
  "games": [730, 570, 252490],
  "phrases": ["액션 게임", "멀티플레이어"],
  "target_tags": ["action", "multiplayer"],
  "avoid_tags": ["casual", "puzzle"],
  "constraints": {
    "price_max": 60.0,
    "platform": "windows"
  }
}
```

---

### Step 11: 쿼리 벡터 생성
**목적**: 사용자 의도를 벡터 공간으로 변환

**필수 파일**:
- `outputs/parsed_intent.json` (Step 10 출력)
- `outputs/game_vecs.npy`
- `outputs/tag_vecs.npy`
- `outputs/W_align.npy` (vibe/hybrid 모드용)

**실행 명령**:
```bash
python step11.py
```

**출력 파일**:
- `outputs/query_vector.npy`

---

### Step 12: 후보 검색 (ANN)
**목적**: FAISS를 사용한 빠른 유사도 검색

**필수 파일**:
- `outputs/query_vector.npy` (Step 11 출력)
- `outputs/game_vecs.npy`
- `outputs/index_maps.json`

**실행 명령**:
```bash
python step12.py
```

**출력 파일**:
- `outputs/candidates.json`

---

### Step 13: 필터 & 스코어링
**목적**: 후보 게임들을 다양한 기준으로 점수화

**필수 파일**:
- `outputs/candidates.json` (Step 12 출력)
- `outputs/parsed_intent.json` (Step 10 출력)
- `outputs/X_game_tag_csr.npz`
- `outputs/game_weight.npy`

**실행 명령**:
```bash
python step13.py
```

**출력 파일**:
- `outputs/scored_candidates.json`

---

### Step 14: 다양성 선택 (MMR)
**목적**: MMR 알고리즘으로 다양성 있는 추천 선택

**필수 파일**:
- `outputs/scored_candidates.json` (Step 13 출력)
- `outputs/game_vecs.npy`

**실행 명령**:
```bash
python step14.py
```

**출력 파일**:
- `outputs/diverse_recommendations.json`

---

### Step 15: LLM 설명 생성
**목적**: 추천 게임에 대한 설명 생성

**필수 파일**:
- `outputs/diverse_recommendations.json` (Step 14 출력)
- `outputs/parsed_intent.json` (Step 10 출력)

**실행 명령**:
```bash
python step15.py
```

**출력 파일**:
- `outputs/final_recommendations.json`

## 🔄 전체 파이프라인 실행

### 1. Similar 모드 테스트
```bash
# user_intent.json 사용
python step10.py
python step11.py
python step12.py
python step13.py
python step14.py
python step15.py
```

### 2. Vibe 모드 테스트
```bash
# user_intent_vibe.json 사용
python step10.py --input user_intent_vibe.json
python step11.py
python step12.py
python step13.py
python step14.py
python step15.py
```

### 3. Hybrid 모드 테스트
```bash
# user_intent_hybrid.json 사용
python step10.py --input user_intent_hybrid.json
python step11.py
python step12.py
python step13.py
python step14.py
python step15.py
```

## 📊 모드별 특징

### Similar 모드
- **입력**: 시드 게임 ID 리스트
- **처리**: 시드 게임 벡터의 평균
- **적합한 경우**: "이 게임과 비슷한 게임 추천해줘"

### Vibe 모드
- **입력**: 자연어 표현
- **처리**: 자연어 → 태그 벡터 변환
- **적합한 경우**: "긴장감 넘치는 스릴러 게임 추천해줘"

### Hybrid 모드
- **입력**: 시드 게임 + 자연어 표현
- **처리**: Similar + Vibe 가중합
- **적합한 경우**: "이 게임과 비슷하면서도 전략적인 게임 추천해줘"

## ⚙️ 주요 파라미터

### Step 12 (ANN 검색)
- `--top-n`: 검색할 후보 수 (기본값: 500)
- `--index-type`: 인덱스 타입 (hnsw/ivf/exact)
- `--m`: HNSW M 파라미터 (기본값: 32)

### Step 13 (스코어링)
- `--alpha`: 태그 매칭 가중치 (기본값: 0.4)
- `--beta`: 신선도 가중치 (기본값: 0.2)
- `--gamma`: 최신성 가중치 (기본값: 0.2)
- `--delta`: 인기도 가중치 (기본값: 0.2)

### Step 14 (다양성)
- `--k`: 선택할 추천 수 (기본값: 10)
- `--lambda`: MMR 람다 파라미터 (기본값: 0.5)

### Step 15 (설명)
- `--explanation-style`: 설명 스타일 (concise/detailed/casual)

## 🐛 문제 해결

### 일반적인 오류들

1. **파일이 없다는 오류**
   - Step 1-9가 완료되었는지 확인
   - `outputs/` 폴더에 필요한 파일들이 있는지 확인

2. **메모리 부족 오류**
   - Step 12의 `--top-n` 값을 줄여보세요
   - Step 12의 `--index-type`을 "exact"로 변경해보세요

3. **의도 파싱 오류**
   - `user_intent.json` 파일 형식 확인
   - 필수 필드가 누락되지 않았는지 확인

### 성능 최적화

1. **빠른 검색을 위해**:
   - Step 12: `--index-type hnsw` 사용
   - Step 12: `--top-n` 값을 적절히 조정

2. **정확한 검색을 위해**:
   - Step 12: `--index-type exact` 사용
   - Step 12: `--top-n` 값을 늘려보세요

## 📈 결과 해석

### 최종 출력 파일 구조
```json
{
  "recommendation_info": {
    "total_recommendations": 10,
    "user_mode": "similar",
    "explanation_style": "concise"
  },
  "recommendations": [
    {
      "game_id": "730",
      "scores": {
        "tag_match": 0.85,
        "novelty": 0.72,
        "recency": 0.68,
        "popularity": 0.91,
        "final": 0.79
      },
      "explanation": {
        "text": "게임 730는 요청하신 게임과 매우 유사한 특성을 가지고 있습니다.",
        "style": "concise"
      }
    }
  ]
}
```

### 점수 해석
- **tag_match**: 요청한 태그와의 매칭도 (0-1)
- **novelty**: 게임의 신선도/독특성 (0-1)
- **recency**: 게임의 최신성 (0-1)
- **popularity**: 게임의 인기도 (0-1)
- **final**: 최종 종합 점수 (0-1)

## 🔗 관련 파일들

- `user_intent.json`: Similar 모드 테스트용
- `user_intent_vibe.json`: Vibe 모드 테스트용
- `user_intent_hybrid.json`: Hybrid 모드 테스트용
- `README.md`: 전체 프로젝트 개요
- `requirements.txt`: 필요한 패키지 목록
