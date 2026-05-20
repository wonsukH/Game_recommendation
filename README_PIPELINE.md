# 데이터 / 모델 파이프라인 상세

크롤링 → 메인 파이프라인 → 평가 → 서빙까지의 흐름. 각 단계의 디폴트는 `config/default.yaml`. CLI 인자로 override 가능.

메인 파이프라인 전체 실행:

```powershell
python -m pipeline.orchestration.build_offline
```

---

## 0. 전체 데이터 흐름

```
[ Metacritic 페이지 ]
        |  data_collection/crawlers/metacritic.ipynb
        v
metacritic_pc_userscore_green.csv   (1800 titles)
        |  steam_reviews.py
        v
steam_reviews.csv                   (~348K reviews)
        |
        +-- user_reviews.py (steamcommunity HTML) -> user_all_reviews.csv (~1.19M user reviews)
        |
        +-- steamspy.py -> steamspy_games.csv (tags + popularity for 10K games)
        |
        +-- steam_appdetails.py -> steam_appdetails.csv (description / genre / price)


[ data_collection/eda/game_analysis.py ]
        v
game_info_with_names.csv  +  game_similarity_matrix.csv  +  EDA plots


[ pipeline/orchestration/build_offline.py ]
        v
  data.user_scores         user_all_reviews -> user_game_scores.csv
  data.tag_vocab           steam_games_tags.csv -> tag_vocab.json
  data.game_tag_matrix     -> X_game_tag_csr.npz + index_maps.json
  data.game_weights        Bayesian shrinkage -> game_weight.npy
  data.game_popularity     SteamSpy owners + reviews -> game_popularity.npy
  models.tag_embeddings    PPMI + SVD -> tag_vecs.npy
  models.tag_effects       Ridge -> tag_beta.npy
  models.item2vec          SkipGram on user favorites -> game_vecs_user_signal.npy
  models.game_vectors      PPMI + Item2Vec ensemble -> game_vecs.npy
  models.text_alignment    Solar embed + Ridge -> W_align.npy
  index.faiss_index        IndexFlatL2 -> faiss_index.faiss
  index.tag_projection     UMAP 2D + KMeans -> tag_2d.npy + tag_clusters.npy
  evaluation.quality       -> quality_report.json


[ scripts/sync_data.py ]
        v
serving/data/  (앱이 읽는 사본)
```

---

## 1. 크롤링 단계 (`data_collection/crawlers/`)

### 1-1. Metacritic 타이틀 수집 (`metacritic.ipynb`)

- Selenium으로 Metacritic PC userscore 페이지 1~75 순회 → 1800 게임 타이틀
- 출력: `outputs/metacritic_pc_userscore_green.csv`

### 1-2. Steam 리뷰 수집 (`steam_reviews.py`)

- 입력: 위 타이틀 CSV
- Steam Search API로 appid 매핑 → appreviews API에서 영문 리뷰 최대 200개/게임
- 출력: `outputs/steam_reviews.csv` (~348K rows)
- rate limit: 0.5-2초 jitter, 10개마다 checkpoint

### 1-3. 유저별 전체 리뷰 (`user_reviews.py`)

- 입력: `steam_reviews.csv`의 unique steamid
- steamcommunity.com 유저 profile HTML을 aiohttp + BeautifulSoup으로 비동기 fetch
- 출력: `outputs/user_all_reviews.csv` (~1.19M rows: steamid, appid, voted_up, playtime_forever)
- 체크포인트: 100명마다

### 1-4. SteamSpy — tags + popularity (`steamspy.py`) **[새로 추가, M1]**

- 입력: 없음 (popularity 상위부터 페이지네이션)
- `/all&page=N`로 10K appid 받고, `/appdetails`로 각 게임의 user-tag dict + vote 수
- 출력: `outputs/steamspy_games.csv` (appid, name, owners, tags_json, ...)
- rate limit: 1 req/sec (`/appdetails`), 10K = 약 3시간

### 1-5. Steam Store 메타데이터 (`steam_appdetails.py`) **[새로 추가, M1]**

- 입력: `steamspy_games.csv`의 appid
- Steam Store appdetails API → description, genres, languages, release_date, developers, price
- 출력: `outputs/steam_appdetails.csv`
- 50개마다 checkpoint, rate 1 req/sec

상세한 운영 가이드: `docs/runbook_pool_expansion.md`.

### Legacy: Selenium 태그 크롤러

`_legacy/steam_tags.py`, `_legacy/steam_tags_parallel.py`는 SteamSpy 도입 전 사용된 HTML 스크래핑 방식. SteamSpy가 누락한 게임 보완용으로 보존.

---

## 2. EDA 단계 (`data_collection/eda/game_analysis.py`)

- 입력: `steam_reviews.csv`, `user_game_matrix.csv` (옵션)
- 게임별 통계 집계 → `game_info_with_names.csv`
- 공통 플레이어 기반 게임 간 유사도 → `game_similarity_matrix.csv`
- 시각화 → `eda/plots/`, `eda/similarity_plots/`

---

## 3. 메인 파이프라인 모듈

### `data.user_scores`

- **입력**: `outputs/user_all_reviews.csv`
- **출력**: `outputs/user_game_scores.csv`
- 게임 안 percent-rank + recommendation vote 가중 → `s_round10_rec` (0~10)
- 환경변수: `UGS_ALPHA10_POS`, `UGS_ALPHA10_NEG`, `UGS_PENALTY_MODE`

### `data.tag_vocab`

- 태그 이름 정규화 + 별칭 매핑 → `tag_vocab.json`

### `data.game_tag_matrix`

- Game × Tag 이진 행렬 + appid↔row / tag↔idx 매핑 → `X_game_tag_csr.npz`, `index_maps.json`

### `data.game_weights` **[M3.3 갱신: Bayesian shrinkage]**

- 게임별 평균 점수 → 글로벌 평균 방향으로 shrink
- `w_g = (n_g · mean_g + k · global_mean) / (n_g + k)` (k = prior_strength, 기본 10)
- 옵션: `mean` (원래 방식) / `bayesian` (기본) / `variance` (역분산 가중)
- 출력: `game_weight.npy`

### `data.game_popularity` **[M3.2 신규]**

- 입력: `steamspy_games.csv`(우선) + `user_all_reviews.csv`(fallback)
- SteamSpy `owners` range 중간값 또는 review count
- 출력: `game_popularity.npy` (4-metric Novelty/Serendipity 입력)

### `models.tag_embeddings`

- PPMI + Truncated SVD → `tag_vecs.npy` (393×128)
- `kappa=1.0`, `embedding_dim=128`, `random_state=42`

### `models.tag_effects`

- Ridge로 태그별 β → `tag_beta.npy`
- 베이스라인 R² 0.3877. β는 step6에서 게임벡터 합성에 20% 가중(eta=0.2)

### `models.item2vec` **[M3.4 신규]**

- 각 유저의 favorite 게임 set (`s_round10_rec ≥ 7`)을 sentence로 → SkipGram
- 입력: `user_game_scores.csv`, `index_maps.json`
- 출력: `game_vecs_user_signal.npy` (게임 수 × 128)
- vocab에 없는 게임(cold-start)은 zero vector

### `models.game_vectors` **[M3.5 갱신: PPMI + Item2Vec ensemble]**

- 1차: PPMI 임베딩의 β-가중 평균 + β-축 스티어링 (기존 로직)
- 2차: Item2Vec과 가중 결합
    - `game_vec = α · normalize(ppmi_vec) + (1-α) · normalize(user_signal_vec)`, 그 후 다시 L2
    - cold-start (Item2Vec 0 벡터)는 자동으로 PPMI fallback
- 출력: `game_vecs.npy` (ensemble) + `game_vecs_ppmi.npy` (ablation용)

### `models.text_alignment`

- 태그 텍스트를 Solar 임베딩 후 Ridge로 `tag_vecs` 공간에 매핑
- 출력: `W_align.npy` (Solar 4096차원 → 128차원 사상 행렬)
- `UPSTAGE_API_KEY` 필요

### `index.faiss_index`

- IndexFlatL2(128차원) → `faiss_index.faiss`

### `index.tag_projection` **[M6.1 신규]**

- UMAP 2D + KMeans clusters → `tag_2d.npy`, `tag_clusters.npy`, `tag_neighbors.json`
- 태그 의미 지도 페이지 입력
- `umap-learn` 없으면 PCA fallback

### `evaluation.quality`

- 태그 이웃 spot check, 게임 유사도 spot check, 허브니스, 회귀 적합도
- 출력: `quality_report.json`

---

## 4. 평가 + 비교 (`pipeline/orchestration/benchmark.py`)

- 입력: `tests/evaluation_set.json` (자연어 쿼리 + 정답 게임 셋)
- 6개 모드 × 6개 메트릭 표 출력
    - 모드: `popularity`, `content-ppmi`, `content-ensemble`, `mmr-{beginner, balanced, heavy}`
    - 메트릭: Recall@k, Precision@k, NDCG@k, Diversity, Novelty, Serendipity
- 출력: stdout Markdown 표 + `outputs/benchmark.csv`

평가 셋 구조:

```json
[
  {
    "query": "처음 RPG 해보고 싶은데 어두운 분위기",
    "relevant_appids": [105600, 1145360, 1245620]
  },
  ...
]
```

라벨링은 본인이 수동 (M7).

---

## 5. 파라미터 요약

| 파라미터 | 위치 | 기본값 |
|---|---|---|
| `gamma` | `data.game_weights` | 0.5 |
| `weighting` | `data.game_weights` | bayesian |
| `prior_strength` | `data.game_weights` | 10 |
| `embedding_dim` | `models.tag_embeddings` | 128 |
| `ridge_alpha` | `models.tag_effects` | 1.0 |
| `vector_size` (Item2Vec) | `models.item2vec` | 128 |
| `window` (Item2Vec) | `models.item2vec` | 10 |
| `score_threshold` (Item2Vec) | `models.item2vec` | 7 |
| `kappa` | `models.game_vectors` | 1.0 |
| `alpha` (tag count comp.) | `models.game_vectors` | 0.5 |
| `eta` (β-axis steering) | `models.game_vectors` | 0.2 |
| `ensemble_alpha` (PPMI weight) | `models.game_vectors` | 0.7 |
| `lambda_reg` | `models.text_alignment` | 0.01 |
| `text_model` | `models.text_alignment` | solar-embedding-1-large |
| `mmr_lambda` | `rerank` | 0.5 |
| presets {relevance, diversity, novelty, serendipity} | `rerank.presets` | 입문/균형/헤비 |

CLI 인자 (`--gamma`, `--kappa` 등)는 항상 config보다 우선.

---

## 6. 알려진 제약사항

- `tag_effects`의 R²는 기본 ~0.39로 *태그→점수 회귀 적합도*에서는 낮음. 단 메인 신호는 PPMI+SVD가 만들고 β는 보조 (eta=0.2)라서 게임벡터에 미치는 영향 제한적. 이제 4-metric으로 *추천 quality*를 직접 측정 가능.
- Item2Vec은 user-favorite 시퀀스 학습이라 적은 user 표본 게임은 학습 부족. cold-start는 PPMI로 자동 fallback.
- Steam 데이터: 영문 리뷰만 수집. timestamp 없음 (sequence-based 모델 어려움).
- 라이브 추천에서 메모리: 약 4 GB 권장.
