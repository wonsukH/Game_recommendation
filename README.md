# Steam Game Recommendation Agent

> 자연어로 게임을 추천하는 멀티 에이전트 시스템 — LangGraph + Gemini + FAISS

```
"몰입감 있는 어드벤처 게임 추천해줘"   →   AI Agent   →   Steam 게임 5개 + 자연어 설명
```

사용자가 게임 태그(`Soulslike`, `Roguelite`)를 몰라도 평범한 한국어 한 줄로 적합한 게임에 도달할 수 있게 만든 시스템. 자연어 ↔ 게임 의미 임베딩 정렬을 1급 자산으로 두고, 자체 평가 framework로 모델 구성을 검증·단순화했다.

---

## 핵심 결과

| 지표 | 값 |
|---|---|
| 추천 대상 Steam 게임 | **9,956** |
| 태그 임베딩 차원 | **447 태그 → 128차원** |
| LLM 단독 vs 시스템 평가 쿼리 | **30** |
| Pool Coverage Miss | **0.0%** (LLM 단독 7.3% — 풀 외부 추천 시 운영 통합 불가) |
| True Hallucination | ~0% (Steam Storefront API cross-check) |
| Genre Precision (객관 측정) | **90.7%** (Steam 사용자 vote 기반 태그 매칭) |
| 단위 테스트 | **55 passing** |

자세한 평가 표 + ablation: [`README_PIPELINE.md`](README_PIPELINE.md) 의 "평가 결과" 섹션.

---

## 1분 안에 데모 실행

```powershell
# 1. clone + venv
git clone https://github.com/wonsukH/YBIGTA-Newbie-project.git
cd YBIGTA-Newbie-project/Game_recommendation
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. dependencies
pip install -r requirements.txt
pip install -e .

# 3. .env 만들기 (Gemini 키 필요, 무료)
#    https://aistudio.google.com/apikey 에서 발급
echo "GEMINI_API_KEY=your_key_here" > .env
echo "GEMINI_EMBEDDING_MODEL=models/gemini-embedding-2" >> .env
echo "GEMINI_CHAT_MODEL=gemini-2.5-pro" >> .env

# 4. 데모 실행
streamlit run serving/main.py
```

브라우저에서 `http://localhost:8501` 자동 열림. 채팅창에 자연어 쿼리 입력:

- `다크 소울 3 같은 게임 추천해줘`
- `혼자 차분하게 할 수 있는 짧은 게임`
- `Stardew Valley처럼 힐링되는데 더 모험적인 거`
- `Roguelite 좋아하는데 너무 어렵지 않은 거`

좌측 사이드바에서 3-axis 슬라이더(Relevance / Diversity / Novelty)로 추천 성향 조절.

> **데이터 산출물 없이 데모 실행**: `outputs/`는 gitignored. 처음 clone 시 임베딩이 없어 추천이 안 된다. `python -m pipeline.orchestration.build_offline`으로 전체 파이프라인 실행 (Gemini 임베딩 호출 약 7분 + faiss index 빌드). 또는 사전 빌드된 산출물 zip을 받았다면 `outputs/`에 풀어두기.

---

## 무엇을 보여주는가

1. **자연어 이해 + 의도 분류** — LangGraph 멀티 에이전트 (Parser → Router → Recommender → Response)
2. **RAG-like 검색** — Gemini 임베딩 + 자연어-태그 공간 정렬 + FAISS 코사인 검색 + 3-axis rerank
3. **데이터 기반 의사결정** — 자체 평가 framework로 가설 검증 → 모델 구성 단순화 (negative finding 채택)
4. **검증 가능한 시스템** — 단위 테스트 55건, label-free 평가 30 query, 모든 의사결정이 `INTENT.md`/`ISSUES.md`에 기록

---

## 시스템 아키텍처

```
사용자 자연어 쿼리
    │
    ▼
┌─────────────────────────────────────────────┐
│  LangGraph StateGraph                       │
│                                             │
│  Parser  →  Router  →  Recommender  →  Response
│    │          │            │              │
│    │          │            │              ▼
│    │          │            │         자연어 답변
│    │          │            ▼
│    │          │       FAISS 코사인
│    │          │       + 3-axis rerank
│    │          │       + 시리즈 자동 제외
│    │          ▼
│    │     {similar | vibe | hybrid | general}
│    ▼
│  Gemini로 의도 분류 + 게임명/태그/제약 추출
└─────────────────────────────────────────────┘
```

### 4가지 모드
| 모드 | 쿼리 예시 | 동작 |
|---|---|---|
| **similar** | "다크 소울 비슷한 게임" | seed 게임의 임베딩과 가까운 후보, 시리즈는 자동 제외 |
| **vibe** | "차분하고 감성적인 게임" | 자연어 → 태그 의미 공간 정렬 → 가까운 영역 검색 |
| **hybrid** | "Stardew Valley 같은데 더 모험적인" | similar + vibe 조합 |
| **general** | "어떤 게임 좋아?" | 대화형 응답 (검색 안 함) |

### 시각화 페이지 (사이드바)
- `tag map` — UMAP 2D scatter, 태그 hover 시 인기 게임 Top 5
- `tag graph 3d` — Three.js 기반 인터랙티브 3D 그래프. dark + bloom glow, 검색창, 클러스터 필터, 노드 호버 시 연결된 태그 강조 + 이웃 5개 표시, 클릭 시 사이드 패널 (top 게임 + 이웃 태그)

---

## 자체 평가 framework

만 개 게임에 ground truth 라벨링은 비현실적. 그래서 LLM(Gemini) 단독과 본 시스템에 같은 30개 자연어 쿼리를 던지고 4개 지표로 비교:

```powershell
python -m pipeline.orchestration.llm_vs_system --preset balanced
# 결과: outputs/llm_vs_system.{csv,md}
```

| 지표 | 의미 | LLM 단독 | 본 시스템 |
|---|---|---|---|
| **Pool Coverage Miss** | 추천 게임이 도메인 풀(9,956) 외부 비율 — 운영 통합 시 dead link | 7.3% | **0.0%** (정의상 보장) |
| **True Hallucination** | Steam에도 없는 게임 추천 비율 (Steam Storefront API cross-check) | ~0% | 0% |
| **Genre Precision** | 쿼리 카테고리 태그 보유한 시스템 추천 비율 (Steam vote 기반 객관 측정) | — | **90.7%** |

평가 시드: `tests/eval_queries.json` (30 query). 측정 코드: `pipeline/orchestration/llm_vs_system.py` + `pipeline/orchestration/intuitive_metrics.py` + `scripts/check_true_hallucination.py`.

검토했지만 의도적으로 제외한 metric: **Overlap@5 / ILD** (두 시스템 목표가 다름 — LLM=풀 외부 mainstream, 시스템=풀 내부 검증 추천 — 자연 차이라 외부 어필 부적합), **LLM-as-Judge** (LLM이 niche indie game 모름 → mainstream bias로 unfair). 자세한 사유는 `ISSUES.md` 및 `portfolio/portfolio_content.md`.

---

## 기술 스택

Python 3.13 · **LangGraph** · LangChain · **Google Gemini** (chat + embedding) · **FAISS-CPU** · scikit-learn · scipy · gensim (Item2Vec) · umap-learn · plotly · **Streamlit** · **Three.js** (3d-force-graph + UnrealBloomPass) · aiohttp · pandas · numpy

---

## 디렉토리

```
Game_recommendation/
├── serving/                 # Streamlit + LangGraph agent (online)
│   ├── main.py             #   채팅 entry
│   ├── pages/              #   tag_map (UMAP) + tag_graph_3d (Three.js)
│   └── data/               #   앱이 읽는 산출물 사본
├── pipeline/                # 라이브러리 + CLI orchestration (offline)
│   ├── game_rec/
│   │   ├── data/           #   user_scores, tag_vocab, weighted X
│   │   ├── models/         #   PPMI+SVD, Item2Vec, game_vectors, W_align
│   │   ├── index/          #   FAISS + UMAP projection
│   │   ├── evaluation/     #   4-metric (Relevance/Diversity/Novelty/Serendipity)
│   │   └── agent/          #   parser / router / recommender / response 노드
│   └── orchestration/      #   build_offline.py, llm_vs_system.py
├── data_collection/         # SteamSpy + Steam Store API 크롤러
├── scripts/                 # sync_data, build_games_tags_csv, summarize_ablation
├── config/default.yaml      # 하이퍼파라미터 + 3-axis presets
├── prompts/                 # parser / response_generator LLM 프롬프트
├── docs/runbook_*.md        # 데이터 풀 확장 가이드
├── tests/                   # 55 단위 테스트 + 30 query 평가 시드
├── outputs/                 # 파이프라인 산출물 (gitignored, 재현 가능)
├── README.md                # 이 파일 (overview + quick start)
├── README_PIPELINE.md       # 임베딩 학습 / 평가 / ablation deep dive
├── INTENT.md                # 개발 의도 + 의사결정 기록
└── ISSUES.md                # 개발 중 발견한 이슈 + 해결 (14건)
```

---

## 환경 변수

`.env` (gitignored, 절대 commit 금지):

```
GEMINI_API_KEY=...                                    # 필수
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-2      # 3072d
GEMINI_CHAT_MODEL=gemini-2.5-pro
STEAM_API_KEY=...                                     # 크롤링 시만
```

키 발급:
- **Gemini**: https://aistudio.google.com/apikey (무료 tier 1500 req/min)
- **Steam Web API**: https://steamcommunity.com/dev/registerkey (크롤링용, 본 데모는 불필요)

키 노출 시 즉시 위 URL에서 새 키로 교체.

---

## 데이터 수집 (선택 — 본 데모 실행에는 불필요)

본 레포는 9,956 게임의 처리된 산출물이 `outputs/`에 들어가야 데모가 동작. 처음 빌드 절차:

```powershell
# 1. SteamSpy 게임 풀 수집 (약 3시간, target 10K)
python -m data_collection.crawlers.steamspy --target-count 10000

# 2. Steam Store 메타데이터 보강 (약 3시간)
python -m data_collection.crawlers.steam_appdetails --input outputs/steamspy_games.csv

# 3. 정규화 CSV
python scripts/build_games_tags_csv.py

# 4. 전체 파이프라인 (임베딩 학습 + FAISS + sync_data 자동)
python -m pipeline.orchestration.build_offline
```

자세한 runbook + 트러블슈팅: [`docs/runbook_pool_expansion.md`](docs/runbook_pool_expansion.md).

---

## 더 깊이 보기

- **임베딩 학습 / 평가 / Ablation 상세**: [`README_PIPELINE.md`](README_PIPELINE.md)
- **개발 의도 + 의사결정 기록**: [`INTENT.md`](INTENT.md)
- **개발 중 발견한 14개 이슈와 해결**: [`ISSUES.md`](ISSUES.md)
- **데이터 풀 확장 절차**: [`docs/runbook_pool_expansion.md`](docs/runbook_pool_expansion.md)

---

## 테스트

```powershell
pytest tests/
# 55 passed
```
