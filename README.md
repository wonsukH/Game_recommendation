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
              -> tag_embeddings (PPMI+SVD)
              -> tag_effects (Ridge)
              -> item2vec (user-favorite SkipGram)
              -> game_vectors (PPMI + Item2Vec ensemble)
              -> text_alignment (Solar -> tag space)
              -> faiss_index
              -> tag_projection (UMAP 2D for the map page)
              -> quality_report


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

| 프리셋 | Relevance | Diversity | Novelty | Serendipity |
|---|---|---|---|---|
| **입문자** | 9 | 4 | 2 | 1 |
| **균형** | 5 | 5 | 5 | 5 |
| **헤비** | 5 | 7 | 8 | 8 |

입문자는 인기/검증된 게임 위주 (Novelty 낮음). 헤비 유저는 long-tail 발견 위주 (Novelty/Serendipity 높음). 사이드바에 4축 슬라이더 + 3개 프리셋 버튼.

---

## 실행

### 환경

```powershell
.venv\Scripts\Activate.ps1
pip install -e .
# .env 또는 환경변수에 UPSTAGE_API_KEY (LLM), STEAM_API_KEY (옵션)
```

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
python scripts/sync_data.py     # outputs/ -> serving/data/ 동기화
streamlit run serving/main.py
```

좌측 사이드바에서 페이지 메뉴 → "태그 의미 지도"로 전환 가능.

### Benchmark (평가 셋 만든 후)

```powershell
python -m pipeline.orchestration.benchmark --eval-set tests/evaluation_set.json -k 10
```

### Tests

```powershell
pytest tests/
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
    pages/
      2_tag_map.py                # 태그 의미 지도 (multipage)
    data/                         # 앱이 읽는 산출물 사본 (sync_data.py로 갱신)

  config/                         # default.yaml — 하이퍼파라미터 + presets
  prompts/                        # parser.txt, response_generator.txt
  scripts/
    sync_data.py                  # outputs/ -> serving/data/
  docs/
    runbook_pool_expansion.md     # SteamSpy/appdetails 크롤링 가이드
  tests/                          # 40+ 단위 테스트
  outputs/                        # gitignored 파이프라인 산출물

  pyproject.toml, requirements.txt
  .env (gitignored): STEAM_API_KEY, UPSTAGE_API_KEY
```

---

## 임베딩 quality 측면

원본 baseline에서 회귀 R² = 0.3877이라 `quality.py`가 자동 "Poor fit" 라벨링했었다. 단 그건 *태그→점수 회귀 적합도*이지 *추천 quality*가 아니다. 이 차이를 정리하기 위해:

- `data.game_weights`: 단순 평균 -> **Bayesian shrinkage**로 변경. 표본 작은 게임이 noisy 점수로 PPMI 가중치를 왜곡하는 걸 방지.
- `models.item2vec`: user-favorite 시퀀스 SkipGram 임베딩 추가. PPMI(태그 co-occurrence)와 **다른 신호**(같이 플레이된 게임).
- `models.game_vectors`: 두 임베딩 L2 정규화 후 가중 ensemble (`α=0.7` PPMI 우세, config로 조절).
- `evaluation.metrics`: 4-metric으로 *추천 결과 quality*를 정량 측정 가능하게 함. R²와 별개.

ablation: benchmark 표에서 `content-ppmi` vs `content-ensemble` 비교로 ensemble의 기여 측정.

### 데이터 충분성 결정 분기점

benchmark 결과를 보고 user data를 더 모을지 결정한다:

| `content-ensemble` vs `content-ppmi` | 조치 |
|---|---|
| Recall/NDCG가 >5% 우세 | 현 user data 충분. 그대로 진행. |
| 거의 동일 (<2% 차이) | `outputs/game_vecs_user_signal_stats.json`의 cold-start 비율 확인. 50%↑면 user 풀 확장 (M9) |
| ensemble이 더 낮음 | `ensemble_alpha`를 0.9로 올리거나 Item2Vec 자체 비활성화 |

user 풀 확장 절차 (M9, 선택적): `steam_reviews.py`로 새 9000 게임의 리뷰 수집 → 새 steamid에 대해 `user_reviews.py` 재크롤 → `user_scores` + `item2vec` 재학습. 약 7-12시간 작업이라 benchmark 결과 보고 가치 확실할 때만 진행.

---

## 의식적으로 빼는 것

- **CF (ALS / BPR / LightFM)** — 본 시스템은 익명 query 기반이라 user-side cold-start. CF는 "이 유저와 비슷한 사람들" 신호인데 우리는 익명. 목적성에 부합 안 함. Novelty는 단순 popularity로 충분.
- **Sequence / Session-based 추천** (SASRec, BERT4Rec) — 데이터에 timestamp 없음.
- **Two-Tower / NCF / Node2Vec** — 작은 데이터에서 PPMI+SVD 대비 결정적 이득 보장 없음. 시간 ROI 약함.

---

## 알려진 제약사항

- `Item2Vec`은 user favorite 시퀀스(`s_round10_rec ≥ 7`)에서만 학습. 적은 표본의 user는 sentence가 짧아 임베딩 quality 떨어짐. cold-start 게임은 ensemble에서 자동으로 PPMI fallback.
- `text_alignment`은 `UPSTAGE_API_KEY` 필요 (Solar 임베딩). 키 없으면 `--skip-text-alignment`로 회피.
- 영문 리뷰만 수집. 한국어 리뷰는 데이터셋에 없음.
- 입문자 평가 셋 (`tests/evaluation_set.json`)은 본인이 라벨링해야 함.

---

## 기술 스택

Python 3.10+ · scikit-learn · scipy · gensim (Item2Vec) · umap-learn · FAISS-CPU · plotly · LangGraph · LangChain · Upstage Solar · Streamlit · aiohttp · pandas · numpy
