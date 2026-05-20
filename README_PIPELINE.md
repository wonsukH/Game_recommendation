# 데이터 / 모델 파이프라인 상세

크롤링 -> EDA -> 메인 파이프라인 -> 앱 데이터 동기화까지의 흐름을 정리. 각 단계의 디폴트는 `config/default.yaml`에서 오고 CLI 인자로 override 가능.

메인 파이프라인 전체 실행:

```powershell
python -m pipelines.build_offline
```

---

## 0. 전체 데이터 흐름

```
[Metacritic 페이지]
        |  crawlers/metacritic.ipynb
        v
metacritic_pc_userscore_green.csv  (1800 game titles)
        |  crawlers/steam_reviews.py (Steam search API -> appreviews API)
        v
steam_reviews.csv                  (~348K rows: appid + steamid + voted_up
                                    + playtime_forever + review text)
        |
        +----+ crawlers/user_reviews.py (steamcommunity HTML)
        |    |
        |    v
        |  user_all_reviews.csv     (~1.19M rows: per-user review history)
        |
        +----+ eda/game_analysis.py (aggregate per-game stats)
        |    |
        |    v
        |  game_info_with_names.csv (~1082 rows: per-game review/playtime stats)
        |  + game_similarity_matrix.csv (공통 플레이어 기반 유사도)
        |  + EDA 플롯들 (eda/plots, eda/similarity_plots)
        |
        +----+ crawlers/steam_tags_parallel.py
             |   (Selenium으로 Steam 상점 페이지에서 게임당 태그 수집)
             v
        steam_games_tags.csv       (1031 rows: appid -> 콤마 구분 태그)


outputs/ 입력 3종:
  user_all_reviews.csv             (-> 메인 파이프라인의 user_scores 첫 단계 입력)
  steam_games_tags.csv             (-> tag_vocab, game_tag_matrix 입력)
  user_game_scores.csv             (-> 메인 파이프라인이 user_scores로 직접 생성)

           v
        game_rec.data.*     -> tag_vocab.json, X_game_tag_csr.npz, game_weight.npy
        game_rec.models.*   -> tag_vecs.npy, tag_beta.npy, game_vecs.npy, W_align.npy
        game_rec.index.*    -> faiss_index.faiss
        game_rec.evaluation -> quality_report.json, metadata_v*.json
           v
        scripts/sync_data.py -> app/data/   (Streamlit 앱이 읽는 사본)
```

---

## 1. 크롤링 단계 (`crawlers/`)

순서대로 실행해야 한다. 각 단계의 출력이 다음 단계의 입력.

### 1-1. Metacritic 타이틀 수집 (`crawlers/metacritic.ipynb`)

- **무엇을**: Metacritic의 PC userscore 페이지 1~75를 Selenium으로 순회
- **출력**: `outputs/metacritic_pc_userscore_green.csv` (1800개 게임 타이틀 단순 리스트)
- **외부 의존**: Selenium + ChromeDriver
- **노트북**: ad-hoc 디스커버리 용도. cwd가 `crawlers/`라고 가정하고 `../outputs/`에 저장

### 1-2. Steam 리뷰 수집 (`crawlers/steam_reviews.py`)

- **입력**: `outputs/metacritic_pc_userscore_green.csv`
- **알고리즘**:
  1. 각 타이틀을 Steam storesearch API로 검색 -> appid 매핑 (정확 일치 우선)
  2. 각 appid의 appreviews API에서 영문 리뷰 최대 200개 수집 (cursor 페이지네이션)
- **출력**: `outputs/steam_reviews.csv` (~348K rows). 컬럼: appid, recommendationid, author_steamid, review, voted_up, votes_up, votes_funny, weighted_vote_score, comment_count, steam_purchase, received_for_free, written_during_early_access, game_title
- **rate limiting**: 0.5~2초 jitter, 10개마다 중간 저장
- **외부 의존**: `requests`

### 1-3. 유저별 전체 리뷰 수집 (`crawlers/user_reviews.py`)

- **입력**: `outputs/steam_reviews.csv` (unique steamid 추출용)
- **알고리즘**: 각 steamid에 대해 `steamcommunity.com/profiles/{steamid}/reviews/` HTML을 aiohttp로 비동기 fetch -> BeautifulSoup으로 review_box 파싱 (voted_up, playtime, 다른 appid들)
- **출력**: `outputs/user_all_reviews.csv` (~1.19M rows: steamid, appid, voted_up, playtime_forever)
- **체크포인트**: 100명마다 중간 저장 (`*_checkpoint.csv`)
- **외부 의존**: `aiohttp`, `beautifulsoup4`. TCPConnector limit=10

### 1-4. Steam 태그 수집 (`crawlers/steam_tags.py` 또는 `steam_tags_parallel.py`)

- **입력**: `outputs/game_info_with_names.csv` (EDA 단계 출력의 appid 컬럼)
- **알고리즘**: Selenium headless Chrome으로 `store.steampowered.com/app/{appid}/` 방문. 연령 제한 페이지 자동 통과 (생년 2000년 선택). `.app_tag` 요소를 모두 추출 + "+ 더보기" 버튼 클릭
- **출력**: `outputs/steam_games_tags.csv` (1031 rows: appid, game_title, tags 콤마 구분, tag_count)
- **병렬판**: `steam_tags_parallel.py`는 5개 드라이버 동시 (ThreadPoolExecutor)
- **외부 의존**: Selenium + ChromeDriver

---

## 2. EDA 단계 (`eda/game_analysis.py`)

- **입력**: `outputs/steam_reviews.csv`, `outputs/user_game_matrix.csv`
- **무엇을**:
  - 게임별 리뷰 수 / 긍정 비율 / 플레이타임 통계 집계 -> `outputs/game_info_with_names.csv`
  - 유저별 게임 취향 분포 분석
  - 게임 간 공통 플레이어 기반 유사도 행렬 -> `outputs/game_similarity_matrix.csv`
  - 시각화 4종 (`eda/similarity_plots/`): 유사도 히트맵 / 클러스터링 / 네트워크 / 감성지도
- **부가 출력**: `eda/plots/` 안에 리뷰 길이 / 추천률-플레이타임 / 리뷰-추천 산점도
- **한글 폰트**: Windows의 맑은 고딕을 자동 감지. 못 찾으면 DejaVu Sans fallback (한글 깨짐 경고 출력)
- **메인 파이프라인과의 연결**: 이 단계의 `game_info_with_names.csv`가 1-4 태그 크롤링의 입력. 즉 EDA -> 태그 크롤링 -> 메인 파이프라인 순서.

---

## 3. 메인 파이프라인 진입

여기서부터는 `pipelines/build_offline.py`가 차례로 호출하는 모듈들. 입력 3개 CSV가 `outputs/`에 있다고 가정:

- `outputs/user_all_reviews.csv`  (크롤링 1-3에서 생성)
- `outputs/steam_games_tags.csv`  (크롤링 1-4에서 생성)
- 그 외 `game_info_with_names.csv` 등 EDA/크롤링 산출물

`game_rec.data.user_scores`가 `user_all_reviews.csv`를 받아 `user_game_scores.csv`를 만든 뒤, 나머지 8개 모듈이 그것과 `steam_games_tags.csv`를 입력으로 임베딩 / 인덱스 / 평가 결과를 차례로 만든다.

---

## 4. 메인 파이프라인 모듈

### `game_rec.data.user_scores`

- **목적**: 유저-게임 리뷰 행을 게임당 분위수 + 추천/비추천 가중 점수로 변환
- **입력**: `outputs/user_all_reviews.csv`
- **출력**: `outputs/user_game_scores.csv` (컬럼 추가: `ptile`, `s_round10`, `vote_factor`, `s_round10_rec`)
- **알고리즘**:
  - 각 게임 안에서 playtime percent-rank `ptile = (rank-1)/(n-1)`
  - `s_round10 = round(ptile * 10)` (0~10 정수)
  - vote 가중치: 추천이면 `x(1 + α_pos)`, 비추천이면 `linear` 모드에서 `x(1 - α_neg * s/10)`
  - 최종 `s_round10_rec = clip(s_round10 * vote_factor, 0, 10)`
- **파라미터**: 환경변수 `UGS_ALPHA10_POS` (기본 0.3), `UGS_ALPHA10_NEG` (기본 0.5), `UGS_PENALTY_MODE` (기본 `linear`)

### `game_rec.data.tag_vocab`

- **목적**: 태그 이름 정규화 + 별칭 매핑
- **입력**: `outputs/steam_games_tags.csv`
- **출력**: `outputs/tag_vocab.json`
- **핵심**: `lower()` -> NFKC -> 다중 공백 -> `/`와 공백을 `-`로 -> `alias_map` 적용

### `game_rec.data.game_tag_matrix`

- **목적**: Game x Tag 이진 행렬 + 인덱스 매핑
- **입력**: `outputs/steam_games_tags.csv`, `outputs/tag_vocab.json`
- **출력**: `outputs/X_game_tag_csr.npz` (1031 x 393, int8), `outputs/index_maps.json` (`appid2row` / `row2appid` / `tag2idx` / `idx2tag`)

### `game_rec.data.game_weights`

- **목적**: 게임별 평균 점수를 [0, 1] 가중치로 변환
- **입력**: `outputs/user_game_scores.csv`
- **출력**: `outputs/game_weight.npy`, `outputs/game_weight_stats.json`
- **파라미터**: `data.game_weights.gamma` (기본 0.5), `score_col` (기본 `s_round10_rec`)
- **변환**: MinMax 정규화 후 `power(x, gamma)`

### `game_rec.models.tag_embeddings`

- **목적**: PPMI + SVD로 태그 의미 임베딩 학습
- **입력**: `X_game_tag_csr.npz`, `game_weight.npy`
- **출력**: `outputs/tag_vecs.npy` (393 x 128), `outputs/tag_embedding_stats.json`
- **파라미터**: `models.tag_embeddings.embedding_dim` (기본 128), `random_state` (기본 42)
- **알고리즘**: `diag(sqrt(s)) @ X` 가중 행렬 -> 공존 행렬 -> PPMI -> TruncatedSVD

### `game_rec.models.tag_effects`

- **목적**: 각 태그가 게임 점수에 미치는 효과 β 학습
- **입력**: `X_game_tag_csr.npz`, `outputs/user_game_scores.csv`
- **출력**: `outputs/tag_beta.npy` (393,), `outputs/tag_beta_stats.json`
- **파라미터**: `models.tag_effects.ridge_alpha` (기본 1.0)
- **알고리즘**: `StandardScaler(with_mean=False)` -> Ridge 회귀. 베이스라인 R² 0.3877

### `game_rec.models.game_vectors`

- **목적**: 태그 벡터를 가중 합성해 게임 임베딩 생성
- **입력**: `X_game_tag_csr.npz`, `tag_vecs.npy`, `tag_beta.npy`
- **출력**: `outputs/game_vecs.npy` (1031 x 128, 단위벡터), `outputs/game_vecs_stats.json`
- **파라미터**: `models.game_vectors.{kappa, alpha, eta}` (기본 1.0 / 0.5 / 0.2)
- **알고리즘**: per-game `softmax(β/max(β) / kappa)` 가중평균, 태그 수 보정 `/ count^alpha`, β-축 스티어링 `+ eta * <v, d_β> * d_β`, 그 후 L2 정규화

### `game_rec.models.text_alignment`

- **목적**: 자연어 -> 태그 공간 사상 행렬 학습
- **입력**: `tag_vecs.npy`, `outputs/index_maps.json`
- **출력**: `outputs/tag_text_vecs.npy` (393 x 4096), `outputs/W_align.npy` (4096 x 128), `outputs/text_align_stats.json`
- **파라미터**: `models.text_alignment.text_model` (기본 `solar-embedding-1-large`), `lambda_reg` (기본 0.01)
- **알고리즘**: 태그 텍스트를 임베딩 모델로 인코딩한 후 Ridge로 `tag_vecs`에 회귀

### `game_rec.index.faiss_index`

- **목적**: 게임 벡터로 FAISS IndexFlatL2 인덱스 구축
- **입력**: `app/data/game_vecs.npy`
- **출력**: `app/data/faiss_index.faiss`

### `game_rec.evaluation.metadata`

- **목적**: 산출물 버전 스냅샷 (MD5 해시 + 크기 + 통계 합본)
- **출력**: `outputs/{tag_vecs, game_vecs, tag_beta, game_weight, X_game_tag_csr, tag_text_vecs, W_align}_v{N}.{npy,npz}`, `outputs/params_v{N}.json`, `outputs/metadata_v{N}.json`
- **CLI**: `python -m game_rec.evaluation.metadata --version v2 --backup`

### `game_rec.evaluation.quality`

- **목적**: 임베딩 품질 점검 리포트
- **입력**: `tag_vecs.npy`, `game_vecs.npy`, `tag_beta.npy`, `tag_beta_stats.json`
- **출력**: `outputs/quality_report.json`
- **내용**:
  - 태그 이웃 스팟체크 (cozy / roguelike / soulslike / horror / open-world)
  - 게임 유사도 스팟체크 (처음 20개 게임 Top-10)
  - 허브니스 분석 (mean / std / max / entropy)
  - 회귀 적합도 자동 라벨링 (R² < 0.5 -> Poor fit)

---

## 보조 도구

### `game_rec.index.tag_similarity`

PPMI+SVD 기반 임베딩과는 별도로, 유저-태그 점수 매트릭스에 코사인 유사도를 적용한 협업필터링 스타일 태그 유사도. 보조 신호 / sanity check 용도.

```powershell
python -m game_rec.index.tag_similarity
```

출력: `outputs/tag_similarity_cosine.csv` (393 x 393)

---

## 파라미터 요약

| 파라미터 | 위치 | 기본값 |
|---|---|---|
| `gamma` | `data.game_weights` | 0.5 |
| `embedding_dim` | `models.tag_embeddings` | 128 |
| `ridge_alpha` | `models.tag_effects` | 1.0 |
| `kappa` | `models.game_vectors` | 1.0 |
| `alpha` | `models.game_vectors` | 0.5 |
| `eta` | `models.game_vectors` | 0.2 |
| `lambda_reg` | `models.text_alignment` | 0.01 |
| `text_model` | `models.text_alignment` | `solar-embedding-1-large` |
| `top_k_default` | `retriever` | 200 |
| `expand_top_k` | `retriever` | 5 |

CLI 인자 (`--gamma`, `--kappa` 등)는 항상 config보다 우선.

---

## 알려진 제약사항

- Step 5의 R²는 베이스라인 시점 기준 0.3877이라 `quality.py`가 자동으로 "Poor fit" 라벨링한다. 태그 효과는 보조 신호이고 주 임베딩은 PPMI+SVD가 만들지만, 이 가정 자체의 타당성은 Agent 평가 인프라 도입 후 ablation으로 검증 예정.
- 메모리: 약 4 GB RAM 권장. PPMI 계산이 가장 무거움.
- 외부 의존: `text_alignment`에 `UPSTAGE_API_KEY` 필요. `faiss-cpu` 미설치 환경에서는 `--skip-faiss`로 회피 가능.
