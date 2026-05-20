# 🎮 Steam 게임 추천 시스템

Steam 게임 데이터를 활용한 AI 기반 게임 추천 시스템입니다. 크롤링부터 EDA, Feature Engineering을 거쳐 최종적으로 Streamlit 웹 애플리케이션으로 구현되었습니다.

## 📋 프로젝트 개요

이 프로젝트는 다음과 같은 단계로 구성되어 있습니다:

1. **데이터 수집 (Crawling)**: Steam에서 게임 정보, 태그, 리뷰 데이터 수집
2. **탐색적 데이터 분석 (EDA)**: 수집된 데이터의 특성 분석 및 시각화
3. **특성 엔지니어링 (FE)**: 임베딩 기반 게임 추천 시스템 구축
4. **웹 애플리케이션 (st_app)**: Streamlit 기반 사용자 인터페이스

## 🚀 전체 파이프라인 구조

```
Crawling → EDA → FE → st_app
   ↓        ↓     ↓     ↓
Steam    데이터  임베딩  웹앱
데이터   분석    모델   서비스
수집
```

## 📁 프로젝트 구조

```
27th-project-game/
├── Crawling/                    # 데이터 수집
│   ├── steam_review_pipeline.py      # Steam 리뷰 수집
│   ├── steam_tags_crawler.py         # Steam 태그 수집
│   ├── steam_tags_crawler_parallel.py # 병렬 태그 수집
│   ├── user_reviews_crawler_simple2.py # 사용자 리뷰 수집 (steamcommunity HTML)
│   └── user_game_scores_penalty.py   # 게임 점수 계산
├── EDA/                        # 탐색적 데이터 분석
│   ├── game_analysis.py             # 게임 데이터 분석
│   └── eda_plots/                   # 분석 결과 플롯
├── FE/                         # 특성 엔지니어링
│   ├── step1.py                     # 태그 정규화
│   ├── step2.py                     # Game×Tag 행렬 생성
│   ├── step3.py                     # 게임 점수 정규화
│   ├── step4.py                     # 태그 임베딩 학습
│   ├── step5.py                     # 태그 효과 학습
│   ├── step6.py                     # 게임 벡터 합성
│   ├── step7.py                     # 텍스트→태그 정렬
│   ├── step8.py                     # 메타데이터 관리
│   ├── step9.py                     # 품질 점검
│   ├── create_faiss_index.py        # FAISS 인덱스 생성
│   └── run_online_pipeline.py       # 온라인 파이프라인 실행
├── st_app/                      # Streamlit 웹 애플리케이션
│   ├── app.py                       # 메인 애플리케이션
│   ├── data/                        # 모델 데이터
│   └── rag/                         # RAG 시스템
│       ├── retriever.py             # 벡터 검색기
│       └── nodes/                   # RAG 노드들
│           ├── parser_node.py       # JSON 파싱 노드
│           ├── recommendation_nodes.py # 추천 노드들
│           ├── router_node.py       # 라우팅 노드
│           └── response_generator_node.py # 응답 생성 노드
├── outputs/                     # 중간 결과물
├── images/                      # 이미지 파일
└── requirements.txt             # 의존성 패키지
```

## 🔧 설치 및 설정

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정
`.env` 파일을 생성하고 다음 내용을 추가하세요:
```
UPSTAGE_API_KEY=your_upstage_api_key_here
```

## 📊 데이터 수집 (Crawling)

### 실행 순서

1. **Steam 태그 수집**
```bash
cd Crawling
python steam_tags_crawler.py
```
- Steam 게임 페이지에서 태그 정보 수집
- Selenium을 사용한 웹 크롤링
- 연령 제한 페이지 자동 처리

2. **Steam 리뷰 수집**
```bash
python steam_review_pipeline.py
```
- Steam API를 통한 리뷰 데이터 수집
- 게임별 최대 200개 리뷰 수집
- 리뷰 텍스트, 투표 정보, 메타데이터 포함

3. **사용자 게임 점수 계산**
```bash
python user_game_scores_penalty.py
```
- 리뷰 데이터를 기반으로 게임 점수 계산
- 플레이타임 페널티 적용

### 주요 기능
- **병렬 처리**: `steam_tags_crawler_parallel.py`로 대용량 데이터 처리
- **에러 처리**: 네트워크 오류, 연령 제한 등 자동 처리
- **데이터 정제**: 중복 제거, 형식 통일

## 📈 탐색적 데이터 분석 (EDA)

### 실행 방법
```bash
cd EDA
python game_analysis.py
```

### 분석 내용
- **게임 통계**: 리뷰 수, 긍정 비율, 플레이타임 분포
- **태그 분석**: 인기 태그, 태그 조합 패턴
- **시각화**: 
  - 리뷰 길이 분포
  - 추천률과 플레이타임 관계
  - 게임 유사도 히트맵
  - 감정 지도

### 생성 파일
- `eda_plots/`: 분석 결과 이미지들
- `game_similarity_visualizations/`: 게임 유사도 시각화

## ⚙️ 특성 엔지니어링 (FE)

### 실행 순서 (Step 1-9)

```bash
cd FE

# 1. 태그 정규화
python step1.py

# 2. Game×Tag 이진 행렬 생성
python step2.py

# 3. 게임 점수 정규화
python step3.py --gamma 0.5

# 4. 태그 임베딩 학습
python step4.py --dim 128

# 5. 태그 효과 학습
python step5.py --alpha 1.0

# 6. 게임 벡터 합성
python step6.py --kappa 1.0 --alpha 0.5 --eta 0.2

# 7. 텍스트→태그 정렬
python step7.py --lambda-reg 0.01

# 8. 메타데이터 관리
python step8.py --version v1 --backup

# 9. 품질 점검
python step9.py --top-k 10
```

### 각 단계별 설명

#### Step 1: 태그 정규화
- 태그 이름 표준화 (소문자, 하이픈 통일)
- 별칭 매핑 적용
- 출력: `tag_vocab.json`

#### Step 2: Game×Tag 행렬
- 게임-태그 관계를 희소 행렬로 변환
- CSR(Compressed Sparse Row) 형식 사용
- 출력: `X_game_tag_csr.npz`, `index_maps.json`

#### Step 3: 게임 점수 정규화
- Min-Max 정규화 및 Gamma 보정
- 게임별 평균 점수 계산
- 출력: `game_weight.npy`, `game_weight_stats.json`

#### Step 4: 태그 임베딩 학습
- PPMI(Positive Pointwise Mutual Information) 계산
- Truncated SVD로 128차원 임베딩 생성
- 출력: `tag_vecs.npy`, `tag_embedding_stats.json`

#### Step 5: 태그 효과 학습
- Ridge 회귀로 태그별 β 계수 학습
- R² 점수로 모델 성능 평가
- 출력: `tag_beta.npy`, `tag_beta_stats.json`

#### Step 6: 게임 벡터 합성
- 태그 벡터의 가중 평균 계산
- Softmax 정규화 및 β-축 스티어링
- 출력: `game_vecs.npy`, `game_vecs_stats.json`

#### Step 7: 텍스트→태그 정렬
- Sentence Transformer로 태그 텍스트 임베딩
- Ridge 회귀로 정렬 행렬 학습
- 출력: `tag_text_vecs.npy`, `W_align.npy`

#### Step 8: 메타데이터 관리
- 파일 버전 관리 및 파라미터 추적
- 백업 생성
- 출력: 버전별 파일들, `params_v*.json`, `metadata_v*.json`

#### Step 9: 품질 점검
- 태그 이웃 스팟체크
- 게임 유사도 스팟체크
- 허브니스 분석
- 출력: `quality_report.json`

### FAISS 인덱스 생성
```bash
python create_faiss_index.py
```
- 게임 벡터를 FAISS 인덱스로 변환
- 빠른 유사도 검색을 위한 최적화

## 🌐 Streamlit 웹 애플리케이션 (st_app)

### 실행 방법
```bash
cd st_app
streamlit run app.py
```

### 주요 기능

#### 1. RAG (Retrieval-Augmented Generation) 시스템
- **Parser Node**: 사용자 질문을 JSON으로 파싱
- **Router Node**: 모드별 작업 분기 (similar, vibe, hybrid, general)
- **Recommendation Nodes**: 
  - Similar Node: 유사한 게임 추천
  - Vibe Node: 분위기 기반 추천
  - Hybrid Node: 하이브리드 추천
- **Response Generator Node**: 자연스러운 추천사 생성

#### 2. 추천 모드
- **Similar**: 특정 게임과 유사한 게임 추천
- **Vibe**: 분위기나 태그 기반 추천
- **Hybrid**: 게임 유사도 + 분위기 조합
- **General**: 일반적인 대화

#### 3. 재정렬 시스템
- **Tag Match**: 코사인 유사도 기반 점수 (0~1)
- **Novelty**: 유사도 기반 신선도 점수 (0~1)
- **가중치 조정**: 사용자가 직접 설정 가능

### 파일 구조
```
st_app/
├── app.py                    # 메인 Streamlit 앱
├── data/                     # 모델 데이터 (FE 결과물 복사)
└── rag/
    ├── retriever.py          # 벡터 기반 추천기
    └── nodes/
        ├── parser_node.py    # JSON 파싱
        ├── recommendation_nodes.py # 추천 노드들
        ├── router_node.py    # 조건부 라우팅
        ├── response_generator_node.py # 응답 생성
        ├── general_node.py   # 일반 채팅
        └── normalization_node.py # 게임명 정규화
```

## 🎯 사용 예시

### 1. 유사한 게임 찾기
```
"엘든링이랑 비슷한 게임 찾아줘"
```
- 모드: similar
- 대상 게임: Elden Ring
- 유사한 액션 RPG 게임들 추천

### 2. 분위기 기반 추천
```
"다크 판타지 분위기에, 호러는 아니었으면 좋겠어"
```
- 모드: vibe
- 원하는 태그: Dark Fantasy
- 제외 태그: horror
- 분위기 기반 게임 추천

### 3. 하이브리드 추천
```
"발더스 게이트 3 같은데, 좀 더 밝은 분위기 없을까? 한국어도 지원해야 하고"
```
- 모드: hybrid
- 기준 게임: Baldur's Gate 3
- 추가 요구사항: 밝은 분위기, 한국어 지원
- 게임 유사도 + 분위기 조합 추천

## 📊 성능 지표

### 데이터 규모
- **게임 수**: 1,031개
- **태그 수**: 393개
- **임베딩 차원**: 128차원
- **평균 게임당 태그**: ~8.2개

### 품질 지표
- **태그 임베딩**: PPMI + SVD 기반 의미적 유사도
- **게임 임베딩**: 태그 효과 가중 평균
- **회귀 성능**: Ridge R² 점수로 평가
- **허브니스**: 코사인 유사도 분포 분석

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

## 🚨 주의사항

1. **의존성 설치**: `pip install -r requirements.txt` 필수
2. **메모리 요구사항**: 최소 4GB RAM 권장
3. **실행 순서**: Crawling → EDA → FE → st_app 순서대로 실행
4. **API 키**: Upstage API 키가 필요합니다
5. **데이터 경로**: 모든 파일은 지정된 경로에 저장
6. **버전 관리**: Step 8로 정기적인 백업 권장

## 🔄 전체 실행 순서 요약

```bash
# 1. 데이터 수집
cd Crawling
python steam_tags_crawler.py
python steam_review_pipeline.py
python user_game_scores_penalty.py

# 2. 데이터 분석
cd ../EDA
python game_analysis.py

# 3. 특성 엔지니어링
cd ../FE
python step1.py
python step2.py
python step3.py
python step4.py
python step5.py
python step6.py
python step7.py
python step8.py --version v1 --backup
python step9.py
python create_faiss_index.py

# 4. 웹 애플리케이션 실행
cd ../st_app
streamlit run app.py
```

## 📝 향후 개선 사항

- [ ] 더 많은 게임 데이터 크롤링 (판매량, 출시일 포함)
- [ ] Scoring 시스템 개선
- [ ] 데이터베이스 연동
- [ ] 성능 테스트 추가
- [ ] 사용자 피드백 시스템

---

**프로젝트 팀**: YBIGTA 27기 신입기수 프로젝트
**기술 스택**: Python, Streamlit, LangChain, FAISS, Selenium, scikit-learn






