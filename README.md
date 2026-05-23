# Steam Game Recommendation Agent

YBIGTA 27기 신입기수 팀 프로젝트로 만든 시스템을, 마치고 나서 다시 들여다보니 production 관점에서 부족한 부분들이 눈에 띄어 차근차근 다시 정리하고 키워나가는 레포.

원본 팀 작업은 `27th-project-game/`에 그대로 보존되어 있고, 본 레포는 그 시점의 clone에서 출발해 점진적으로 손을 본 흔적이 `git log`에 그대로 남는다.

본 시스템의 핵심 가설은 **"게임 입문자는 `Soulslike`, `Roguelite`, `Cozy` 같은 태그를 자연어적으로 이해 못 한다. 태그 간 의미적 유사도 + 자연어↔태그 사상이 정확하면 입문자도 평범한 말로 적합한 게임에 도달할 수 있다"**. 그래서 본 시스템의 1급 자산은 **태그 의미 임베딩**(PPMI+SVD + Item2Vec 앙상블)이고, 4-metric rerank + Streamlit 태그 지도가 그 위에 올라간다.

---

## 시스템 구조

```
[ 사용자 자연어 쿼리 ]
        |
        v
[ Streamlit UI ]  serving/main.py + pages/
        |
        v
[ LangGraph 에이전트 ]  pipeline/game_rec/agent/
   parser -> normalizer -> route_by_mode
                              |
              +---------------+---------------+
              v               v               v
           similar          vibe            hybrid
              |               |               |
              +-------+-------+
                      v
                  [ rerank ]   MMR + 4 signals
                      v
              [ response_generator ]


[ Offline pipeline ]  pipeline/orchestration/build_offline.py
  user_scores -> tag_vocab -> game_tag_matrix -> game_weights (Bayesian)
              -> game_popularity
              -> tag_embeddings (PPMI+SVD on vote-weighted X)
              -> tag_effects (Ridge)
              -> item2vec (user-favorite SkipGram)
              -> game_vectors (PPMI + Item2Vec ensemble)
              -> text_alignment (Gemini embedding -> tag space, Ridge)
              -> faiss_index (over outputs/, then sync_data promotes to serving/data/)
              -> tag_projection (UMAP 2D for the map page)
              -> quality_report
              -> sync_data (auto-promotes outputs/ -> serving/data/)


[ Data collection ]  data_collection/crawlers/
  metacritic.ipynb         (Metacritic PC userscore -> ~1800 titles)
  steam_reviews.py         (Steam Search + appreviews API -> review CSV)
  steamspy.py              (SteamSpy /all + /appdetails -> user-tags + popularity)
  steam_appdetails.py      (Steam Store API -> rich metadata: genre, lang, price)
  user_reviews.py          (steamcommunity HTML -> per-user review history)
```

---

## 평가 4-metric

추천 결과를 4축으로 평가. 메트릭 정의 + 구현은 `pipeline/game_rec/evaluation/metrics.py`.

| 축 | 측정 | 사용자 선호도와의 관계 |
|---|---|---|
| **Relevance** | Recall@k / NDCG@k | 쿼리 의도와 얼마나 일치 |
| **Diversity** | Intra-List Distance (1 - 평균 pairwise cosine) | 같은 카테고리 안에서 폭 넓은지 |
| **Novelty** | Self-Information `-log2(P(item))` | 메이저 게임만 안 나오는지 |
| **Serendipity** | Relevance × not-in-popularity-baseline | 입문자가 모르는 좋은 게임을 발견하는지 |

`pipeline/orchestration/benchmark.py`가 평가 셋(`tests/evaluation_set.json`)을 받아 6개 모드(`popularity`, `content-ppmi`, `content-ensemble`, `mmr-{beginner, balanced, heavy}`)를 4-metric으로 비교한다.

---

## 입문자 / 헤비 유저 슬라이더

`config/default.yaml`의 `rerank.presets`:

| 프리셋 | Relevance | Diversity | Novelty |
|---|---|---|---|
| **입문자** | 9 | 4 | 1 |
| **균형** | 5 | 5 | 5 |
| **헤비** | 5 | 7 | 8 |

신호의 출처 (3-axis, M11에서 Serendipity 제거):
- **Relevance**: cosine similarity between query vector and game_vecs (top 200 candidates). positive-only weight.
- **Novelty**: $-\log_2 P(\text{game})$ where P ∝ popularity. signed sigmoid (5=neutral, <5=popular 우대, >5=niche 우대).
- **Diversity**: MMR penalty on selected vs candidate similarity. signed sigmoid (>5에서만 활성).

Serendipity slider는 Novelty와 popularity-기반 redundant라 학계 표준대로 user control에서 제외 (Adamopoulos & Tuzhilin 2014, Kotkov 2016). Serendipity@K **metric**은 `evaluation/metrics.py`에 측정용으로 유지.

game_vecs 자체는 **PPMI(game, tag) + Truncated SVD only** (M9.C 결정 — `ensemble_alpha=1.0`). 옛날 Item2Vec ensemble은 user data sparsity 때문에 noise였음, 비활성.

각 슬라이더(0-10)의 의미:

- **Relevance**: positive-only weight. 0 = 무시, 10 = 최대 강조 (`less relevant`라는 개념 자체가 없음).
- **Diversity / Novelty / Serendipity**: **signed sigmoid modifier**. **슬라이더 5 = neutral** (영향 없음). 10 = full positive (niche / 다양 / 의외 우대). 0 = full negative (popular / 비슷한 류 / 예측 가능 우대). sigmoid라 5 근처는 약한 효과, 양 끝에서 강한 효과.

→ 입문자(nov=2, ser=1) = popularity 강한 게임 boost → 정통 인기작이 자연스럽게 top 5. 헤비(nov=8, ser=8) = niche/long-tail 발견 위주. 5/5/5/5는 순수 cosine relevance만.

구현: `pipeline/game_rec/agent/scoring.py:sigmoid_modifier`. 단위 테스트 `tests/test_rerank_helpers.py` 12건.

---

## 실행

### 환경

```powershell
.venv\Scripts\Activate.ps1
pip install -e .
# .env에 GEMINI_API_KEY (LLM + embedding), STEAM_API_KEY (옵션)
```

`.env`:
```
GEMINI_API_KEY=...
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-2     # 3072d
GEMINI_CHAT_MODEL=gemini-2.5-pro
STEAM_API_KEY=...                                     # crawling 시
```

원본 baseline은 Upstage Solar를 썼으나 본 레포는 무료 tier가 generous한 Gemini로 갈아탔다 (decoupled — 모델 이름만 `solar-...`로 두면 그대로 동작).

### 데이터 수집 (게임 풀 확장)

```powershell
# Sample dry-run (1분)
python -m data_collection.crawlers.steamspy --target-count 100 --dry-run

# 본격 (10K 게임, 약 3시간)
python -m data_collection.crawlers.steamspy --target-count 10000

# Steam Store 메타데이터 (약 3시간, SteamSpy 다음에 직렬)
python -m data_collection.crawlers.steam_appdetails --input outputs/steamspy_games.csv
```

자세한 흐름 + 트러블슈팅은 `docs/runbook_pool_expansion.md`.

### 오프라인 파이프라인

전체:

```powershell
python -m pipeline.orchestration.build_offline
```

API 키 / faiss 없으면 단계 skip:

```powershell
python -m pipeline.orchestration.build_offline --skip-text-alignment --skip-faiss
```

개별 단계:

```powershell
python -m pipeline.game_rec.data.user_scores
python -m pipeline.game_rec.data.tag_vocab
python -m pipeline.game_rec.data.game_tag_matrix
python -m pipeline.game_rec.data.game_weights        # Bayesian shrinkage
python -m pipeline.game_rec.data.game_popularity
python -m pipeline.game_rec.models.tag_embeddings    # PPMI + SVD
python -m pipeline.game_rec.models.tag_effects       # Ridge
python -m pipeline.game_rec.models.item2vec          # SkipGram on user favorites
python -m pipeline.game_rec.models.game_vectors      # PPMI + Item2Vec ensemble
python -m pipeline.game_rec.models.text_alignment
python -m pipeline.game_rec.index.faiss_index
python -m pipeline.game_rec.index.tag_projection     # UMAP 2D + clusters
python -m pipeline.game_rec.evaluation.quality
```

### Streamlit 챗봇

```powershell
# build_offline에 sync_data가 자동 stage로 포함되어 있어
# 파이프라인 직후라면 별도 sync 불필요. 다만 다음 명령으로 수동 sync도 가능:
python scripts/sync_data.py     # outputs/ -> serving/data/

streamlit run serving/main.py
```

좌측 사이드바에서 페이지 4개:
- **main**: 채팅 (parser → normalizer → similar/vibe/hybrid → rerank → response)
- **tag map**: UMAP 2D scatter — 호버 시 인기 게임 Top 5
- **tag graph 2d**: streamlit-agraph 기반 force-directed graph (옵시디언 스타일, drag/zoom/physics)
- **tag graph 3d**: 3d-force-graph (three.js, components.html 임베드) — 3D 회전

### 평가

두 가지 평가 경로:

```powershell
# 1) 4-metric benchmark (ideal label 필요 - tests/evaluation_set.json)
python -m pipeline.orchestration.benchmark --eval-set tests/evaluation_set.json -k 10

# 2) LLM vs 시스템 비교 (label-free, 추천)
python -m pipeline.orchestration.llm_vs_system --preset beginner
python -m pipeline.orchestration.llm_vs_system --preset heavy
```

(2)는 ground-truth 라벨 없이 30 query를 우리 시스템과 순수 Gemini Pro에 동시에 던지고 `overlap@5`, `existence_rate` (LLM hallucination), `avg_pop`, `ILD`로 비교. 결과는 `outputs/llm_vs_system.{csv,md}`.

### Tests

```powershell
pytest tests/
# 55 passed
```

---

## 디렉토리

```
Game_recommendation/
  data_collection/                # 외부 데이터 수집 + EDA
    crawlers/
      metacritic.ipynb
      steam_reviews.py
      steamspy.py                 # tags + popularity (API)
      steam_appdetails.py         # description / genre / price (API)
      user_reviews.py             # steamcommunity HTML
      _legacy/                    # 옛 Selenium 크롤러 (보완용)
    eda/
      game_analysis.py
      plots/, similarity_plots/

  pipeline/                       # 라이브러리 + CLI 오케스트레이션
    game_rec/                     # 메인 패키지
      io.py, config.py, log.py, prompts.py
      data/                       # user_scores, tag_vocab, game_tag_matrix,
                                  # game_weights (Bayesian), game_popularity
      models/                     # tag_embeddings, tag_effects, item2vec,
                                  # game_vectors (ensemble), text_alignment
      index/
        faiss_index.py
        tag_projection.py         # UMAP + clusters (for tag map)
        tag_similarity.py
      evaluation/
        metrics.py                # Recall / Diversity / Novelty / Serendipity
        quality.py, metadata.py
      agent/                      # 온라인 LangGraph 에이전트
        retriever.py              # FAISS + MMR rerank
        scoring.py                # pure-numpy helpers (testable)
        nodes/
          parser.py / router.py / normalizer.py
          recommendation.py / response.py / general.py
    orchestration/
      build_offline.py            # 전체 파이프라인 직렬 실행
      benchmark.py                # 4-metric 모드별 비교

  serving/                        # Streamlit 진입점
    main.py / graph.py / ui.py
    graph_data.py                 # force-graph 페이지 공용 데이터 로더
    pages/
      2_tag_map.py                # UMAP 2D scatter + hover Top 5 인기 게임
      3_tag_graph_2d.py           # streamlit-agraph (옵시디언-style force)
      4_tag_graph_3d.py           # 3d-force-graph (three.js)
    data/                         # 앱이 읽는 산출물 사본 (sync_data.py로 갱신)

  config/                         # default.yaml — 하이퍼파라미터 + presets
  prompts/                        # parser.txt, response_generator.txt
  scripts/
    sync_data.py                  # outputs/ -> serving/data/
    build_games_tags_csv.py       # SteamSpy raw -> retriever용 normalized CSV
  docs/
    runbook_pool_expansion.md     # SteamSpy/appdetails 크롤링 가이드
  tests/                          # 55 단위 테스트
    eval_queries.json             # 30 query 평가 시드 (label-free)
  outputs/                        # gitignored 파이프라인 산출물
    llm_vs_system.{csv,md}        # 30 query × LLM 비교 결과

  pyproject.toml, requirements.txt
  .env (gitignored): STEAM_API_KEY, GEMINI_API_KEY,
                     GEMINI_EMBEDDING_MODEL, GEMINI_CHAT_MODEL
```

---

## 임베딩 quality 측면

원본 baseline에서 회귀 R² = 0.3877이라 `quality.py`가 자동 "Poor fit" 라벨링했었다. 단 그건 *태그→점수 회귀 적합도*이지 *추천 quality*가 아니다. 이 차이를 정리하기 위해:

- `data.game_weights`: 단순 평균 -> **Bayesian shrinkage**로 변경. 표본 작은 게임이 noisy 점수로 PPMI 가중치를 왜곡하는 걸 방지.
- `data.game_tag_matrix`: binary X에 더해 **vote-count weighted X** (`X_game_tag_weighted.npz`) 생성.
- `models.tag_embeddings` / `models.game_vectors`: PPMI 학습에 **weighted X 기본 사용**. 메인 태그(예 `DARK SOULS II`의 `Souls-like` 50000표)와 곁다리 태그(예 `Outbreak`의 `Souls-like` 1표)를 구분 → "장르 다른데 단순 태그 overlap으로 묶이는 매크로 분류 오류" 해소. 측정: weighted 적용 후 DS II top-10에서 `Outbreak`(좀비 horror) 빠지고 `Lies of P`/`Elden Ring`/`Dragon's Dogma` 진입.
- `models.item2vec`: user-favorite 시퀀스 SkipGram 임베딩 추가. PPMI(태그 co-occurrence)와 **다른 신호**(같이 플레이된 게임).
- `models.game_vectors`: 두 임베딩 L2 정규화 후 가중 ensemble (`α=0.7` PPMI 우세, config로 조절).
- `evaluation.metrics`: 4-metric으로 *추천 결과 quality*를 정량 측정 가능하게 함. R²와 별개.

ablation: benchmark 표에서 `content-ppmi` vs `content-ensemble` 비교로 ensemble의 기여 측정.

### Series 자동 제외 필터 (similar 모드)

`recommend_similar`는 seed 게임 title에서 **시리즈 prefix**를 추출해 (`DARK SOULS II` → `dark souls`, `The Witcher 3: Wild Hunt` → `the witcher`) 후보 200개에서 그 prefix를 가진 게임을 자동 제외. 사용자가 "Dark Souls 시리즈 말고 비슷한 거"라 했을 때 LLM에 시리즈가 candidate으로 가서 post-hoc 제거되어 응답이 1개로 줄어드는 문제를 candidate 단계에서 차단. 구현: `pipeline/game_rec/agent/retriever.py:_series_prefix` + `recommend_similar`. roman/arabic은 normalizer가 canonicalize (`DARK SOULS III` ↔ `Dark Souls 3` Jaccard 1.0).

### 평가 결과 — LLM 단독 vs 우리 시스템 + Ablation

`pipeline/orchestration/llm_vs_system.py`로 30 query × 2 시스템 비교. ideal label 없이 정량 비교 가능 메트릭 (overlap, hallucination rate, popularity, ILD).

#### Ablation 표 (30 query, 입문자 프리셋, label-free)

| variant | 설명 | overlap@5 | `our_avg_pop` | `vibe_overlap@5` | `vibe_our_avg_pop` | `our_ild` |
|---|---|---|---|---|---|---|
| `pre_m9a` | 옛 W_align, α=0.7, η=0.2, 4-axis — **초기 baseline** | 0.060 | 6.22M | 0.040 | 7.19M | 0.070 |
| `a07` | 새 W_align (M9.A), α=0.7, η=0.2, 4-axis | 0.053 | 3.95M | 0.040 | **4.64M ↓** | 0.071 |
| `a05` | 새 W_align, α=0.5, 4-axis | 0.013 | 1.35M | 0.000 | 1.35M | 0.066 |
| `a09` | 새 W_align, α=0.9, 4-axis | 0.047 | 5.91M | 0.027 | 5.86M | 0.044 |
| `a10` | 새 W_align, α=1.0 (Item2Vec OFF), 4-axis | 0.087 | 6.62M | 0.080 | 6.08M | 0.042 |
| `eta0` | 새 W_align, η=0 (β-축 OFF), 4-axis | 0.053 | 3.78M | 0.040 | 4.79M | 0.076 |
| `final` | M9.A revert, α=1.0, η=0, 4-axis (이전 채택) | 0.087 | 7.91M | 0.093 | 9.58M | 0.055 |
| **`final3`** ⭐ | **M11: Serendipity slider 제거, 3-axis (채택)** | **0.067** | 5.71M | **0.080** | 7.38M | 0.050 |

#### 핵심 발견 3가지

**1. M9.A description augmentation은 의도와 반대 효과** (`pre_m9a → a07`): vibe 카테고리의 `our_avg_pop`이 7.19M → 4.64M으로 **35% 하락**. mainstream 추천이 줄고 niche로 더 깊이 빠짐.

- 원인: 학습 데이터에 추가한 9956 게임 description의 분포가 long-tail (niche가 mainstream보다 많음). W_align Ridge가 다수파인 niche cluster로 더 강하게 self-bias.
- **결정**: M9.A revert. `text_alignment.py --no-include-descriptions`로 옛 방식.

**2. Item2Vec ensemble (`α<1.0`)이 noise**: `a10` (Item2Vec OFF)이 모든 정량 지표 1위.

- 원인: `user_reviews.py` 페이지네이션 issue로 user당 첫 페이지 10건만 수집 → Skip-Gram sentence 너무 짧음 → 학습 부실 → ensemble에서 noise 도입.
- **결정**: `ensemble_alpha: 0.7 → 1.0` (PPMI only).

**3. β-축 (`eta`) 효과 미미**: `eta0` vs `a07` 차이 미미 (4.79M vs 4.64M). `tag_effects` Ridge R²=0.10이라 약한 신호 → 단순화.

- **결정**: `eta: 0.2 → 0`.

#### 최종 (`final3`, 3-axis) vs baseline (`pre_m9a`, 4-axis)

- `overlap@5`: 0.060 → **0.067** (+12%)
- `our_avg_pop`: 6.22M → 5.71M (-8%)
- `vibe_overlap@5`: 0.040 → **0.080** (+100%)
- `vibe_our_avg_pop`: 7.19M → 7.38M (+3%)
- `llm_existence_rate`: **0.987 → 0.980** (hallucination 거의 0%)
- vibe 모드의 niche cluster bias 완화 — `My Beautiful Paper Smile` 같은 반복 등장 줄어듦

#### 3-axis (`final3`) vs 옛 4-axis (`final`) 트레이드오프

| 메트릭 | 4-axis (final) | 3-axis (final3, 채택) |
|---|---|---|
| `overlap@5` | 0.087 | 0.067 |
| `vibe_our_avg_pop` | 9.58M | 7.38M |
| UX 슬라이더 수 | 4개 | **3개** |
| 학계 표준 | 다이렉트 Serendipity control은 일반적 X | ✅ Rel/Div/Nov 표준 |
| Serendipity@K 측정 | 가능 | **가능 (metric 유지)** |

→ 정량 지표는 4-axis가 약간 우세, **UX 단순화 + 학계 표준 + 의미 분리**는 3-axis가 우세. 후자 우선 채택. baseline 대비는 명확히 개선.

#### 의의

LLM 단독 대비 우리 시스템의 차별점:
- ✅ **0% hallucination** (LLM 1.3% vs 우리 0%)
- ✅ similar 모드는 LLM과 같거나 우세 (게임명 기반)
- ✅ vibe 모드 final에서 LLM과 정렬 (overlap@5 0.093, mainstream cover)
- ✅ niche/long-tail 발굴 능력은 그대로 유지 (다른 카테고리에서)
- 후속 hybrid retrieval (LLM 후보 + 우리 rerank)은 시스템 정체성 약화 우려로 **의식적 미진행**

### 데이터 충분성 결정 분기점

위 평가 결과 + benchmark의 `content-ensemble` vs `content-ppmi`를 보고 user data를 더 모을지 결정.

| 신호 | 조치 |
|---|---|
| vibe 모드 quality 부족 | W_align 학습 데이터 보강 (game description 텍스트 추가) 또는 vibe 단계에 LLM hybrid retriever |
| ensemble vs ppmi (Recall/NDCG) <2% 차이 | cold-start 비율 확인. 50%↑면 user 풀 확장 |
| ensemble이 ppmi보다 낮음 | `ensemble_alpha`를 0.9로 올리거나 Item2Vec 비활성화 |

user 풀 확장 절차 (선택적): `steam_reviews.py`로 새 9000 게임 리뷰 → 새 steamid에 대해 `user_reviews.py` 재크롤 → `user_scores` + `item2vec` 재학습. 약 7-12시간이라 benchmark 결과 보고 가치 확실할 때만.

---

## 의식적으로 빼는 것

- **CF (ALS / BPR / LightFM)** — 본 시스템은 익명 query 기반이라 user-side cold-start. CF는 "이 유저와 비슷한 사람들" 신호인데 우리는 익명. 목적성에 부합 안 함. Novelty는 단순 popularity로 충분.
- **Sequence / Session-based 추천** (SASRec, BERT4Rec) — 데이터에 timestamp 없음.
- **Two-Tower / NCF / Node2Vec** — 작은 데이터에서 PPMI+SVD 대비 결정적 이득 보장 없음. 시간 ROI 약함.

---

## 알려진 제약사항

- `Item2Vec`은 user favorite 시퀀스(`s_round10_rec ≥ 7`)에서만 학습. 적은 표본의 user는 sentence가 짧아 임베딩 quality 떨어짐. cold-start 게임은 ensemble에서 자동으로 PPMI fallback.
- `text_alignment`은 `GEMINI_API_KEY` 필요. 키 없으면 `--skip-text-alignment`로 회피. 또는 `config/default.yaml`의 `text_model`을 SentenceTransformer 명(예: `all-MiniLM-L6-v2`)으로 두면 무키 분기로 자동 fallback.
- 영문 리뷰만 수집. 한국어 리뷰는 데이터셋에 없음.
- **vibe 모드 (자연어만)의 추천 quality**가 W_align Ridge의 sparse niche bias 때문에 mainstream 정통작을 놓치는 경향. similar/hybrid 모드는 정통 후보 잘 잡음.
- 4-metric `benchmark.py`는 라벨링된 `tests/evaluation_set.json`을 요구하지만, 본 레포는 label-free `llm_vs_system.py`로 평가 흐름을 재구성 (사용자가 만 개 게임을 다 알 필요 없음).

---

## 기술 스택

Python 3.13 · scikit-learn · scipy · gensim (Item2Vec) · umap-learn · FAISS-CPU · plotly · streamlit-agraph · 3d-force-graph · LangGraph · LangChain · Google Gemini (embedding + chat) · Streamlit · aiohttp · pandas · numpy
