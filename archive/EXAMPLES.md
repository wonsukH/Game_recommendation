# 온라인 서빙 파이프라인 사용 예시

이 문서는 온라인 서빙 파이프라인의 다양한 사용 시나리오를 보여줍니다.

## 🚀 빠른 시작

### 1. 기본 실행 (Similar 모드)
```bash
python run_online_pipeline.py
```

### 2. Vibe 모드 실행
```bash
python run_online_pipeline.py --input user_intent_vibe.json
```

### 3. Hybrid 모드 실행
```bash
python run_online_pipeline.py --input user_intent_hybrid.json
```

## 📝 사용자 의도 파일 예시

### Similar 모드 - 액션 게임 추천
```json
{
  "mode": "similar",
  "games": [730, 570, 252490],
  "phrases": ["액션 게임", "멀티플레이어"],
  "target_tags": ["action", "multiplayer", "competitive"],
  "avoid_tags": ["casual", "puzzle"],
  "constraints": {
    "price_max": 60.0,
    "platform": "windows"
  }
}
```

### Vibe 모드 - 호러 게임 추천
```json
{
  "mode": "vibe",
  "games": [],
  "phrases": [
    "긴장감 넘치는 스릴러",
    "어두운 분위기의 호러",
    "정신적 긴장을 유발하는 게임"
  ],
  "target_tags": ["horror", "thriller", "atmospheric"],
  "avoid_tags": ["casual", "family-friendly"],
  "constraints": {
    "price_max": 40.0,
    "singleplayer": true
  }
}
```

### Hybrid 모드 - 전략 게임 추천
```json
{
  "mode": "hybrid",
  "games": [730, 570],
  "phrases": [
    "전략적 사고가 필요한 게임",
    "팀워크가 중요한 멀티플레이어"
  ],
  "target_tags": ["strategy", "tactical", "multiplayer"],
  "avoid_tags": ["casual", "puzzle"],
  "constraints": {
    "price_max": 50.0,
    "multiplayer": true
  },
  "weights": {
    "similar": 0.4,
    "vibe": 0.6
  }
}
```

## ⚙️ 고급 설정 예시

### 1. 상세한 설명과 함께 실행
```bash
python run_online_pipeline.py --explanation-style detailed
```

### 2. 더 많은 후보 검색
```bash
python run_online_pipeline.py --top-n 1000
```

### 3. 더 많은 최종 추천
```bash
python run_online_pipeline.py --k 20
```

### 4. 다양성 강조
```bash
python run_online_pipeline.py --lambda 0.3
```

### 5. 모든 설정 조합
```bash
python run_online_pipeline.py \
  --input user_intent_hybrid.json \
  --explanation-style detailed \
  --top-n 1000 \
  --k 15 \
  --lambda 0.4
```

## 🎯 시나리오별 사용법

### 시나리오 1: "CS:GO와 비슷한 게임 추천해줘"
```json
{
  "mode": "similar",
  "games": [730],
  "phrases": [],
  "target_tags": ["fps", "multiplayer", "competitive"],
  "avoid_tags": ["casual"],
  "constraints": {
    "price_max": 30.0,
    "multiplayer": true
  }
}
```

### 시나리오 2: "긴장감 넘치는 스릴러 게임 추천해줘"
```json
{
  "mode": "vibe",
  "games": [],
  "phrases": [
    "긴장감 넘치는 스릴러",
    "정신적 긴장을 유발하는 게임",
    "공포와 스릴이 공존하는 경험"
  ],
  "target_tags": ["thriller", "atmospheric", "psychological"],
  "avoid_tags": ["casual", "family-friendly"],
  "constraints": {
    "price_max": 40.0,
    "singleplayer": true
  }
}
```

### 시나리오 3: "Dota 2와 비슷하면서도 전략적인 게임 추천해줘"
```json
{
  "mode": "hybrid",
  "games": [570],
  "phrases": [
    "전략적 사고가 필요한 게임",
    "팀워크가 중요한 멀티플레이어",
    "전술적 판단력을 요구하는 경험"
  ],
  "target_tags": ["strategy", "tactical", "multiplayer", "competitive"],
  "avoid_tags": ["casual", "puzzle"],
  "constraints": {
    "price_max": 50.0,
    "multiplayer": true,
    "platform": "windows"
  },
  "weights": {
    "similar": 0.4,
    "vibe": 0.6
  }
}
```

## 🔧 단계별 실행 예시

### Step 10만 실행 (의도 파싱 테스트)
```bash
python step10.py --input user_intent.json
```

### Step 10-12 실행 (검색까지)
```bash
python step10.py --input user_intent.json
python step11.py
python step12.py --top-n 200
```

### Step 13-15 실행 (스코어링부터)
```bash
python step13.py
python step14.py --k 15 --lambda 0.4
python step15.py --explanation-style detailed
```

## 📊 결과 해석 예시

### 최종 결과 파일 구조
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
- **tag_match: 0.85** → 요청한 태그와 85% 매칭
- **novelty: 0.72** → 상당히 신선하고 독특한 게임
- **recency: 0.68** → 비교적 최신 게임
- **popularity: 0.91** → 매우 인기 있는 게임
- **final: 0.79** → 종합적으로 높은 점수

## 🐛 문제 해결 예시

### 1. 메모리 부족 오류
```bash
# 후보 수를 줄여서 실행
python run_online_pipeline.py --top-n 100
```

### 2. 느린 실행 속도
```bash
# HNSW 인덱스 사용 (기본값)
python step12.py --index-type hnsw --top-n 500
```

### 3. 정확도 향상
```bash
# 정확한 검색 사용
python step12.py --index-type exact --top-n 1000
```

## 📈 성능 튜닝 팁

### 빠른 응답을 위한 설정
```bash
python run_online_pipeline.py \
  --top-n 200 \
  --k 5 \
  --lambda 0.7
```

### 정확한 추천을 위한 설정
```bash
python run_online_pipeline.py \
  --top-n 1000 \
  --k 20 \
  --lambda 0.3
```

### 다양성 강조를 위한 설정
```bash
python run_online_pipeline.py \
  --lambda 0.2 \
  --k 15
```

## 🔗 관련 문서

- `README_ONLINE_SERVING.md`: 상세한 파이프라인 설명
- `user_intent.json`: Similar 모드 테스트용
- `user_intent_vibe.json`: Vibe 모드 테스트용
- `user_intent_hybrid.json`: Hybrid 모드 테스트용
- `run_online_pipeline.py`: 전체 파이프라인 실행 스크립트
