# 데이터 / 모델 파이프라인 상세 — Reproducible Specification

> ⚠️ **[폐기·이력] 이 스펙은 *피벗 이전* 태그-유사도 파이프라인(PPMI+SVD 128d tag_vecs·Item2Vec·W_align·FAISS·MMR rerank·similar/vibe/hybrid/general·serving/main.py)을 기술하며 현재 시스템이 아니다.** 그 스택은 삭제됨. 현재 = 개인화 CF(`cf_recommender.py`) + LangGraph agent(`serving/agent_graph.py`, routes library/seed/multi_entity/explore/anonymous, entry `main_agent.py`) + content/hybrid 스티어링 + 행동 SQLite `steam.db`. 정본은 [`../README.md`](../README.md)·[`ROADMAP.md`](ROADMAP.md). 데이터층 재구축 후(P8) 전면 재작성 예정. (Genre Precision 90.7%·Pool Coverage Miss·9,956게임/447태그·55테스트는 폐기/강등 수치.)

이 문서는 본 시스템을 **밑바닥부터 동일하게 재현할 수 있는 수준**으로 모든 단계를 기술한다. 각 단계의 입력 / 출력 / 알고리즘 / 수식 / 하이퍼파라미터 / 실행 명령 / 트러블슈팅을 다 포함.

목차:
1. [시스템 가설](#0-시스템-가설)
2. [데이터 수집 (Crawling)](#1-데이터-수집-crawling)
3. [데이터 처리 (`pipeline/game_rec/data/`)](#2-데이터-처리)
4. [임베딩 (`pipeline/game_rec/models/`)](#3-임베딩)
5. [인덱스 (`pipeline/game_rec/index/`)](#4-인덱스)
6. [평가 (`pipeline/game_rec/evaluation/`, `pipeline/orchestration/`)](#5-평가)
7. [에이전트 (`pipeline/game_rec/agent/`)](#6-온라인-에이전트)
8. [서빙 UI (`serving/`)](#7-서빙-ui)
9. [전체 하이퍼파라미터](#8-하이퍼파라미터-전체)
10. [실행 명령 모음](#9-실행-명령-모음)
11. [트러블슈팅](#10-트러블슈팅)

---

## 0. 시스템 가설

> "게임 입문자는 `Soulslike`, `Roguelite`, `Cozy` 같은 태그를 자연어적으로 이해 못 한다. **태그 간 의미적 유사도** + **자연어 ↔ 태그 사상**이 정확하면 입문자도 평범한 말로 적합한 게임에 도달할 수 있다."

→ 본 시스템의 1급 자산은 **태그 의미 임베딩** (`tag_vecs.npy`, 128d). 게임 임베딩(`game_vecs.npy`)은 그 위에서 합성. FAISS는 빠른 검색, MMR rerank는 3축(Relevance/Diversity/Novelty) 사용자 선호 반영, Streamlit은 UI.

---

## 1. 데이터 수집 (Crawling)

`data_collection/crawlers/` 안의 모듈들. 두 경로:
- **Legacy** (옛 베이스라인): Metacritic → Steam Reviews → User Reviews. 1031 게임 풀.
- **새 경로**: SteamSpy API + Steam Store appdetails. 10K 게임 풀.

### 1.1. Metacritic PC 타이틀 (`metacritic.ipynb`) — Legacy

- **방법**: Selenium WebDriver로 `metacritic.com/browse/games/...` 페이지 1~75 순회
- **데이터**: 게임 이름, userscore (green ≥ 7.5만 채택)
- **출력**: `outputs/metacritic_pc_userscore_green.csv` — 약 1800 titles
- **rate limit**: 페이지당 1-2초 sleep + browser session reuse

### 1.2. Steam 리뷰 (`steam_reviews.py`) — Legacy

- **입력**: Metacritic CSV
- **단계 1**: 타이틀 → appid 매핑. `https://store.steampowered.com/api/storesearch/?term={title}&l=english&cc=US` 호출
- **단계 2**: 각 appid에 대해 `https://store.steampowered.com/appreviews/{appid}?json=1&filter=recent&language=english&num_per_page=100` 호출. 최대 200개 리뷰/게임
- **데이터 schema**: `appid, steamid, voted_up, playtime_forever, review, timestamp_created, ...`
- **출력**: `outputs/steam_reviews.csv` — 약 348K rows
- **rate limit**: 0.5-2초 jitter, 10 appid마다 checkpoint CSV write

### 1.3. 유저별 전체 리뷰 (`user_reviews.py`) — Legacy

- **입력**: `steam_reviews.csv`의 unique steamid (~40K)
- **방법**: `steamcommunity.com/profiles/{steamid}/recommended/` HTML을 `aiohttp` + `BeautifulSoup`로 비동기 fetch. 각 유저의 리뷰 history (game name, voted_up, playtime_forever) 파싱
- **출력**: `outputs/user_all_reviews.csv` — 약 1.19M rows
- **rate limit**: 동시 connection 5, sleep 0.3-1초, 100명마다 checkpoint
- **현재 한계**: 첫 페이지(10건)만 받음 → 유저당 max 10 리뷰. Item2Vec sentence가 짧아 학습 약함.

### 1.4. SteamSpy — 태그 + 인기도 (`steamspy.py`) — 새 경로 (M1)

SteamSpy는 Steam 비공식 통계 API. user-tag vote count + owners range 무료 제공.

- **2-단계 호출**:
  1. **Pagination**: `https://steamspy.com/api.php?request=all&page={N}` (N=0..9) → 페이지당 1000 게임의 기본 정보
  2. **Per-game detail**: `https://steamspy.com/api.php?request=appdetails&appid={appid}` → 상세 (tags dict, owners range, average/median playtime, ...)
- **데이터 schema** (`steamspy_games.csv`):
  ```
  appid, name, developer, publisher, owners, average_forever, average_2weeks,
  median_forever, median_2weeks, ccu, price, initialprice, discount,
  languages, genre, tags_json
  ```
  - `owners`: 문자열 range. 예 `"100,000,000 .. 200,000,000"`
  - `tags_json`: JSON-encoded dict. 예 `{"Souls-like": 50000, "Difficult": 40000, ...}`. vote count가 value
- **출력**: `outputs/steamspy_games.csv` — 약 10K rows
- **rate limit**: appdetails는 1 req/sec. 10K = 약 3시간

### 1.5. Steam Store 메타데이터 (`steam_appdetails.py`) — 새 경로 (M1)

- **입력**: `steamspy_games.csv`의 appid
- **호출**: `https://store.steampowered.com/api/appdetails?appids={appid}&cc=US&l=english`
- **데이터**: description, short_description, genres, categories, languages, release_date, developers, publishers, price (initial + discount), platforms
- **출력**: `outputs/steam_appdetails.csv`
- **rate limit**: 1.5초/req, 429 발생 시 exponential backoff (60s → 120s → 240s). 50개마다 checkpoint. `--retry-missing` 모드로 누락된 appid만 재시도 가능

### 1.6. SteamSpy → retriever용 normalized CSV (`scripts/build_games_tags_csv.py`)

새 SteamSpy raw (`tags_json` dict 형태) → 옛 normalized schema (`steam_games_tags.csv`) 변환.

알고리즘:
1. `steamspy_games.csv` load → `tags_json` 파싱
2. `index_maps.json`의 `row2appid` 순서로 정렬 (retriever의 `idx_to_appid`와 일관성)
3. 각 태그에 `normalize_tag` 적용 (다음 섹션 참조)
4. 출력: `outputs/steam_games_tags.csv` (`appid, game_title, tags, tag_count`)

`tags` 컬럼은 콤마 구분 normalized 태그 리스트.

---

## 2. 데이터 처리

`pipeline/game_rec/data/`. 모든 모듈은 `python -m pipeline.game_rec.data.<name>`로 호출 가능, default args는 `config/default.yaml`.

### 2.1. `tag_vocab` — 태그 정규화 + 어휘 구축

**입력**: `outputs/steamspy_games.csv` (또는 옛 `steam_games_tags.csv`)

**핵심 함수**: `normalize_tag(tag)` — 다음 변환 순차 적용:
```python
def normalize_tag(t: str) -> str:
    t = unicodedata.normalize("NFKC", str(t))      # 1. NFKC 정규화 (유니코드 호환 분해 + 합성)
    t = t.lower().strip()                          # 2. 소문자 + 양끝 공백 제거
    t = re.sub(r"[/\s]+", "-", t)                  # 3. 슬래시/공백 → 하이픈
    t = re.sub(r"-+", "-", t)                      # 4. 연속 하이픈 collapse
    t = ALIAS_MAP.get(t, t)                        # 5. alias 매핑 (있으면)
    return t
```

예: `"Action / Adventure"` → `"action-adventure"`

**필터링**: `min_votes` (default 5) — 모든 게임에서의 vote 합계가 임계 미만이면 제외. SteamSpy 데이터는 이미 인기 게임 위주라 min_votes 변경 효과는 작음 (5→1000으로 늘려도 447→416 정도).

**출력**: `outputs/tag_vocab.json`
```json
{
  "tags": ["1980s", "1990s", "2.5d", ..., "zombies"],
  "format": "steamspy",
  "n_tags": 447
}
```

### 2.2. `game_tag_matrix` — Game × Tag 희소 행렬 + 인덱스

**입력**: `steamspy_games.csv` + `tag_vocab.json`

**두 종류의 행렬 생성**:
1. **Binary** (`X_game_tag_csr.npz`): 게임 g가 태그 t를 가지면 1, 아니면 0. dtype `int8`.
2. **Weighted** (`X_game_tag_weighted.npz`): element = SteamSpy의 vote count. dtype `float32`. **PPMI 학습에 default로 사용** (M-bonus).

```python
from scipy.sparse import csr_matrix
shape = (n_games, n_tags)
X_bin = csr_matrix((data_bin, (rows_bin, cols_bin)), shape=shape, dtype=np.int8)
X_w   = csr_matrix((data_w,   (rows_w,   cols_w)),   shape=shape, dtype=np.float32)
```

**인덱스 매핑** (`outputs/index_maps.json`):
```json
{
  "appid2row":  {"236430": 1270, ...},   # appid -> row index
  "row2appid":  {"1270": 236430, ...},   # 역
  "tag2idx":    {"souls-like": 42, ...},
  "idx2tag":    {"42": "souls-like", ...},
  "matrix_shape": [9956, 447],
  ...
}
```

### 2.3. `game_weights` — Bayesian Shrinkage 점수 가중치

각 게임 g에 대해 그 게임을 플레이한 user들의 `s_round10_rec` (0-10 점수) 평균을 가중치로. 단순 평균은 표본 작은 게임에서 noisy → **Bayesian shrinkage**로 안정화:

$$
w_g = \frac{n_g \cdot \overline{s_g} + k \cdot \mu_{\text{global}}}{n_g + k}
$$

- $n_g$: 게임 g를 플레이한 user 수
- $\overline{s_g}$: 그 user들의 점수 평균
- $\mu_{\text{global}}$: 모든 (user, game) 점수의 글로벌 평균
- $k$: prior strength (default 10). $k$가 클수록 글로벌 평균으로 강하게 끌어당김

예시: $k=10$, $\mu_{\text{global}}=6.5$
- 게임 A: 1 user, 평균 9.0 → $w_A = (1 \cdot 9 + 10 \cdot 6.5) / 11 = 6.73$ (글로벌 쪽으로 끌림)
- 게임 B: 100 user, 평균 9.0 → $w_B = (100 \cdot 9 + 10 \cdot 6.5) / 110 = 8.77$ (자기 평균 가까움)

`weighting` 옵션: `mean` (옛), `bayesian` (default), `variance` (역분산 가중).

**출력**: `outputs/game_weight.npy` (shape `(n_games,)`, float32, 0~10 범위).

### 2.4. `game_popularity` — 인기도 (Novelty/Serendipity 입력)

**우선순위**:
1. SteamSpy `owners` range 중간값. `"100,000,000 .. 200,000,000"` → `150,000,000`
2. 없으면 `user_all_reviews.csv`의 review count fallback

**출력**: `outputs/game_popularity.npy` (shape `(n_games,)`, float32).

**용도**: rerank의 novelty score는 $-\log_2(\text{pop}(g) / \sum_g \text{pop}(g))$.

### 2.5. `user_scores` — User × Game 점수

**입력**: `outputs/user_all_reviews.csv` (steamid, appid, voted_up, playtime_forever)

**알고리즘**:
1. 각 게임 내 user들의 `playtime_forever` percent-rank 계산
2. `voted_up` (True/False)로 조정:
   - positive vote: `alpha10_pos = 0.5` 만큼 점수 boost
   - negative vote: `alpha10_neg = 0.3` 만큼 차감
   - 또는 `--penalty-mode no-vote`: vote 무시
3. 0-10 스케일로 정규화 → `s_round10_rec`

**출력**: `outputs/user_game_scores.csv` (`steamid, appid, playtime_forever, voted_up, s_round10_rec`).

---

## 3. 임베딩

### 3.1. `tag_embeddings` — PPMI + Truncated SVD

목표: 태그 간 의미적 유사도가 cosine으로 측정 가능한 dense 임베딩.

**(a) Weighted X 적용**:

$$
X_{\text{weighted}} = \text{diag}(\sqrt{w}) \cdot X
$$

- $X$: weighted matrix (`X_game_tag_weighted.npz`, shape $n_g \times n_t$, 값 = vote count)
- $w$: Bayesian shrinkage된 게임 가중치 (`game_weight.npy`)
- $\sqrt{w}$를 곱하는 이유: 점수 높은 게임의 태그 co-occurrence가 더 강한 신호

**(b) Co-occurrence Matrix**:

$$
C = X_{\text{weighted}}^T \cdot X_{\text{weighted}}
$$

shape $n_t \times n_t$. element $C_{ij}$ = 태그 $i$와 $j$가 같은 게임에 동시 등장한 weighted count 합.

**(c) PPMI (Positive Pointwise Mutual Information)**:

$$
\text{PMI}(i, j) = \log \frac{P(i, j)}{P(i) P(j)} = \log \frac{C_{ij} / N}{(R_i / N)(R_j / N)}
$$

- $N = \sum_{ij} C_{ij}$ (총 co-occurrence sum)
- $R_i = \sum_j C_{ij}$ (태그 $i$의 marginal sum)
- $R_j = \sum_i C_{ij}$ (태그 $j$의 marginal sum)

$$
\text{PPMI}(i, j) = \max(0, \text{PMI}(i, j))
$$

PMI < 0인 element는 0으로 (negative association은 sparse signal로 부적합).

**(d) Truncated SVD**:

$$
\text{PPMI} \approx U \Sigma V^T, \quad \text{tag\_vecs} = U \Sigma_{:d}^{1/2}
$$

`sklearn.decomposition.TruncatedSVD(n_components=128, random_state=42)`. `fit_transform`이 $U \Sigma_{:d}$ 반환.

**출력**: `outputs/tag_vecs.npy` (shape $447 \times 128$, float32). `outputs/tag_embedding_stats.json` (explained_variance_ratio, singular values).

분산 보존: 128차원에서 약 88.8% (weighted X, 10K풀 기준).

### 3.2. `tag_effects` — Ridge Regression (태그 → 점수)

태그가 게임 점수에 미치는 약한 prior. β-축 스티어링에서만 사용.

$$
\hat{s}_g = \sum_t X_{gt} \cdot \beta_t
$$

Ridge (L2-regularized OLS):
$$
\beta = (X^T X + \alpha I)^{-1} X^T s
$$

`sklearn.linear_model.Ridge(alpha=1.0, fit_intercept=True)`. 입력은 binary X (weighted X 아님 — score regression이라 표시 1/0이면 됨).

**출력**: `outputs/tag_beta.npy` (shape $(n_t,)$). 일반적으로 $R^2 \approx 0.10$ (10K풀에서). 약한 신호.

### 3.3. `item2vec` — User-Favorite Skip-Gram

목표: "같이 좋아한 게임끼리 가깝게". CF의 anonymous 익명 신호.

**Sentence 구성**: 각 user의 `s_round10_rec ≥ 7`인 게임 set을 하나의 "sentence"로 (순서 무관).

```python
from gensim.models import Word2Vec
model = Word2Vec(
    sentences=user_favorite_lists,   # [[appid1, appid2, ...], ...]
    vector_size=128,
    window=10,
    min_count=2,
    sg=1,                            # skip-gram (CBOW 0보다 sparse data에 좋음)
    epochs=5,
    workers=4,
)
```

**Skip-Gram 목적함수** (간단한 형태):
$$
\max \sum_{(g_i, g_j) \in \text{context pairs}} \log \sigma(v_{g_j}^T \cdot u_{g_i})
$$

- $u_g$: target embedding, $v_g$: context embedding
- $\sigma$: sigmoid

학습 후 `model.wv[appid]`로 게임 임베딩 조회.

**출력**: `outputs/game_vecs_user_signal.npy` (shape $n_g \times 128$). 학습 vocab에 없는 게임은 zero vector (cold-start).

### 3.4. `game_vectors` — PPMI + Item2Vec Ensemble

**Step 1: PPMI game vector** (게임의 태그 임베딩 가중평균)

각 게임 $g$에 대해:
$$
v_g^{\text{ppmi}} = \frac{\sum_t X_{gt}^{\alpha} \cdot \beta_t^{\eta} \cdot \text{tag\_vec}_t}{\sum_t X_{gt}^{\alpha} \cdot \beta_t^{\eta}}
$$

- $\alpha$ (count compression, default 0.5): $X_{gt}^{\alpha}$로 vote count의 sharp 차이 완화
- $\eta$ (β-axis steering, **default 0.0** — M9.D 결정으로 비활성, `tag_effects` R²=0.10인 약한 신호로 효과 미미): tag_beta를 $\beta^{\eta}$만큼 가중. $\eta=0$이면 β 무시
- $\kappa$ (default 1.0): 추가 weight 조정

코드:
```python
# X normalized weights per game row
weights = np.power(X_g, alpha) * np.power(np.abs(tag_beta), eta)
v_ppmi = (weights @ tag_vecs) / max(weights.sum(), 1e-12)
```

**Step 2: Item2Vec 보강**

$$
v_g^{\text{ensemble}} = \alpha_{\text{ens}} \cdot \widehat{v_g^{\text{ppmi}}} + (1 - \alpha_{\text{ens}}) \cdot \widehat{v_g^{\text{item2vec}}}
$$

- $\widehat{v}$ = L2-normalized $v$
- $\alpha_{\text{ens}}$ = `ensemble_alpha` (**default 1.0** — M9.C ablation 결정으로 Item2Vec 비활성. `user_reviews.py` 페이지네이션 issue로 sentence 짧아 Item2Vec 학습 noise였음. α=1.0 (PPMI only)이 모든 정량 지표 best였음)
- Item2Vec vec가 zero (cold-start)면 per-row fallback: $v_g = \widehat{v_g^{\text{ppmi}}}$
- 결합 후 다시 L2 정규화

**출력**:
- `outputs/game_vecs.npy` (ensemble, 9956 × 128)
- `outputs/game_vecs_ppmi.npy` (PPMI만, ablation용)

### 3.5. `text_alignment` — Gemini Embedding → Tag Space

자연어 phrase를 PPMI tag space로 사영. Ridge regression.

**(a) 태그 텍스트 생성**: 각 태그 이름을 자연어 sentence로:
- Simple tag: `"souls-like"` → `"This is a souls-like game"`
- Complex tag: 그대로 (예: `"design-&-illustration"` → `"design & illustration"`)

**(b) Gemini embedding** (`models/gemini-embedding-2`, 3072d):
$$
T \in \mathbb{R}^{n_t \times 3072}, \quad T_t = \text{embed}(\text{tag\_text}_t)
$$

**(c) Ridge Regression**:

Target은 tag_vecs (PPMI+SVD 128d):
$$
\min_W \| T W - \text{tag\_vecs} \|_F^2 + \lambda \|W\|_F^2
$$

해석해:
$$
W = (T^T T + \lambda I)^{-1} T^T \cdot \text{tag\_vecs}
$$

- $\lambda$ = `lambda_reg` (default 0.01)
- `sklearn.linear_model.Ridge(alpha=lambda_reg, fit_intercept=False).fit(T, tag_vecs)`
- $W$.shape = `(3072, 128)`

**Runtime 사용**: 사용자 phrase $p$ → Gemini embed $e_p \in \mathbb{R}^{3072}$ → $e_p^T W \in \mathbb{R}^{128}$ = predicted tag-space vector

**출력**: `outputs/W_align.npy` (3072 × 128), `outputs/tag_text_vecs.npy` (447 × 3072, optional inspection).

---

## 4. 인덱스

### 4.1. `faiss_index` — IndexFlatL2

```python
import faiss
index = faiss.IndexFlatL2(128)
index.add(game_vecs.astype(np.float32))    # 9956 × 128
faiss.write_index(index, "outputs/faiss_index.faiss")
```

- `IndexFlatL2`: 정확한 L2 거리 brute-force. 9956 게임이라 충분히 빠름 (검색 < 1ms).
- **중요**: `game_vecs.npy`가 L2-normalized이므로 L2 거리 ≡ $\sqrt{2 - 2\cos(\theta)}$. cosine과 동치.
- **default 경로**: `outputs/`. M-bonus에서 `serving/data/` → `outputs/`로 바꾼 이유: build_offline의 stage 순서에서 옛 vector로 build되던 mismatch 버그 해소.
- **비ASCII 경로 처리**: Windows에서 faiss의 narrow ANSI API가 한글 경로를 못 다루는 문제. `_safe_write_index` / `_safe_read_index`로 tempdir 우회.

### 4.2. `tag_projection` — UMAP 2D + KMeans

태그 의미 지도 시각화용.

```python
import umap, sklearn.cluster
reducer = umap.UMAP(n_components=2, random_state=42, n_neighbors=15, min_dist=0.1)
tag_2d = reducer.fit_transform(tag_vecs)             # 447 × 2

kmeans = sklearn.cluster.KMeans(n_clusters=12, random_state=42, n_init=10)
tag_clusters = kmeans.fit_predict(tag_vecs)          # 447 (cluster id)
```

**k-NN 이웃**: tag_vecs cosine similarity 기준 top-5:
```python
from sklearn.metrics.pairwise import cosine_similarity
sim = cosine_similarity(tag_vecs)
neighbors = {tag: sorted([(tag_j, sim[i,j]) for j, tag_j in enumerate(tags) if j != i],
                         key=lambda x: -x[1])[:5]
             for i, tag in enumerate(tags)}
```

**출력**:
- `outputs/tag_2d.npy` (447 × 2)
- `outputs/tag_clusters.npy` (447,)
- `outputs/tag_neighbors.json` (tag → [(neighbor, sim), ...])

`umap-learn` 없으면 PCA fallback.

---

## 5. 평가

### 5.1. 4-Metric (라벨 필요) — `pipeline/game_rec/evaluation/metrics.py`

**Recall@K**:
$$
\text{Recall@K} = \frac{|\text{relevant}_q \cap \text{pred}_q^{(K)}|}{|\text{relevant}_q|}
$$

**Precision@K**:
$$
\text{Precision@K} = \frac{|\text{relevant}_q \cap \text{pred}_q^{(K)}|}{K}
$$

**NDCG@K**:
$$
\text{DCG@K} = \sum_{i=1}^{K} \frac{2^{\text{rel}_i} - 1}{\log_2(i + 1)}, \quad \text{NDCG@K} = \frac{\text{DCG@K}}{\text{IDCG@K}}
$$

**Intra-List Diversity (ILD)** — top-K 게임 사이의 평균 distance:
$$
\text{ILD} = \frac{2}{K(K-1)} \sum_{i<j} (1 - \cos(\hat{v}_{g_i}, \hat{v}_{g_j}))
$$

**Novelty** — top-K의 평균 self-information:
$$
\text{Novelty} = \frac{1}{K} \sum_{i=1}^{K} -\log_2 \left( \frac{\text{pop}(g_i)}{\sum_g \text{pop}(g)} \right)
$$

**Serendipity** — relevant AND non-popular:
$$
\text{Serendipity} = \frac{1}{K} \sum_{i=1}^{K} \mathbb{1}[g_i \in \text{relevant}] \cdot (1 - \text{pct\_pop}(g_i))
$$

여기서 $\text{pct\_pop}$은 popularity의 percentile (0~1).

### 5.2. Benchmark (`pipeline/orchestration/benchmark.py`)

```bash
python -m pipeline.orchestration.benchmark --eval-set tests/evaluation_set.json -k 10
```

6 모드 × 6 메트릭 표:
- `popularity`: 순수 인기도 정렬 baseline
- `content-ppmi`: PPMI only game vecs (`game_vecs_ppmi.npy`)
- `content-ensemble`: ensemble vecs (`game_vecs.npy`)
- `mmr-beginner`, `mmr-balanced`, `mmr-heavy`: rerank applied

출력: stdout markdown + `outputs/benchmark.csv`.

평가 셋 (`tests/evaluation_set.json`):
```json
[
  {"query": "처음 RPG 어두운 분위기", "relevant_appids": [105600, 1145360, ...]},
  ...
]
```

### 5.3. LLM vs 시스템 비교 (label-free) — `pipeline/orchestration/llm_vs_system.py`

ground-truth 라벨 없이 우리 시스템과 순수 Gemini Pro 추천을 비교.

```bash
python -m pipeline.orchestration.llm_vs_system --preset beginner
```

흐름:
1. 30 query (`tests/eval_queries.json`) 반복
2. 각 query마다:
   - **우리 시스템**: parser → normalizer → similar/vibe/hybrid → rerank → top 5 appids
   - **순수 LLM**: Gemini Pro에 "Recommend 5 Steam games for: {query}" prompt → 응답 파싱
   - LLM 응답의 게임 이름을 `find_best_match` (Jaccard 0.5 threshold)로 우리 데이터 appid에 매핑
3. **내부 ablation용 메트릭** (label-free, 측정 가능):
   - `overlap@5` = $\frac{|A \cap B|}{5}$
   - `llm_existence_rate` = $\frac{|\{a \in \text{LLM} : a \neq -1\}|}{5}$ (1.0 - 이 값 = Pool Coverage Miss)
   - `our_avg_pop`, `llm_avg_pop`
   - `our_ild`, `llm_ild`
4. **외부 어필 metric** (`pipeline/orchestration/intuitive_metrics.py`):
   - **Genre Precision**: 시스템 추천이 쿼리 카테고리 태그 보유 비율 (Steam vote 기반 객관)
   - **True Hallucination**: `scripts/check_true_hallucination.py` — Pool Miss 게임을 Steam Storefront API로 cross-check
5. **출력**: `outputs/llm_vs_system.csv` + `.md`, `outputs/intuitive_metrics.md`

**최신 결과 (balanced 프리셋, Hybrid 2-stage + parser lock 동적 weight + tag alias 매핑 적용 후)**:

| 메트릭 | LLM 단독 | 시스템 |
|---|---|---|
| Pool Coverage Miss | 7.3% | **0.0%** |
| True Hallucination | ~0% (Alan Wake 2 1건만 Steam API miss) | 0% |
| Genre Precision | — | **90.7%** (76.7% → 90.7%, 3 fix 누적) |
| 내부 — overlap@5 | baseline | 0.020 |
| 내부 — our_avg_pop | 5.24M | 1.24M |
| 내부 — our_ild | 0.088 | 0.069 |

> LLM-as-Judge metric은 시도했지만 LLM이 niche indie game을 모를 때 unfair (시스템 추천 정통 roguelike 5개를 LLM에 직접 물어 검증 → 2/5 unknown). 별도 portfolio 어필 지표에서 의도적 제외 (`ISSUES.md` #16 참조).

---

## 6. 온라인 에이전트

`pipeline/game_rec/agent/`. LangGraph `StateGraph`.

### 6.1. 토폴로지

```
START → parser_node → normalizer_node → route_by_mode
                                              ↓
                            similar_node / vibe_node / hybrid_node / general_node
                                              ↓
                                          rerank_node
                                              ↓
                                  response_generator_node
                                              ↓
                                            END
```

### 6.2. `parser_node` — 자연어 → 구조화 JSON

LangChain `PromptTemplate | llm` chain. Few-shot prompt가 사용자 query를 분석:

```json
{
  "mode": "similar | vibe | hybrid | general",
  "games": ["DARK SOULS II", ...],
  "phrases": ["dark fantasy RPG", ...],
  "target_tags": [{"name": "souls-like", "weight": 1.0}, ...],
  "avoid_tags": ["horror", ...],
  "constraints": {"language": "korean", "price_max": 30000, ...}
}
```

prompt 전문: `prompts/parser.txt`. JSON 파싱 실패 시 `{"mode": "general"}`로 fallback.

### 6.3. `normalizer_node` — 게임명 정규화

LLM이 추출한 게임명을 데이터셋의 canonical title에 매핑.

**알고리즘**: Jaccard bigram similarity + canonical form preprocessing.

```python
_ROMAN_TO_ARABIC = [
    (r"\bviii\b", "8"), (r"\bvii\b", "7"), (r"\bvi\b", "6"),
    (r"\biv\b", "4"), (r"\biii\b", "3"), (r"\bii\b", "2"),
    (r"\bix\b", "9"), (r"\bx\b", "10"),
]

def _canonical_form(s):
    s = s.lower().strip()
    for pat, rep in _ROMAN_TO_ARABIC:
        s = re.sub(pat, rep, s)
    s = re.sub(r"[:\-™®©]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def jaccard_similarity(s1, s2):
    s1 = _canonical_form(s1)
    s2 = _canonical_form(s2)
    b1 = {s1[i:i+2] for i in range(len(s1) - 1)}
    b2 = {s2[i:i+2] for i in range(len(s2) - 1)}
    return len(b1 & b2) / len(b1 | b2)
```

`find_best_match(query, choices, threshold=0.3)`: 모든 choices와 Jaccard 계산해 최고점 반환. threshold 이하면 원본 query 그대로 반환.

**Roman 변환 핵심**: III를 II보다 먼저 substitute (길이 desc 순). 안 그러면 III가 "II + I"로 부분 매칭되어 잘못된 변환.

### 6.4. `recommend_similar` — 게임명 기반 추천

```python
def recommend_similar(parsed_json, top_k=200):
    seed_titles = parsed_json['games']
    seed_appids, seed_vecs, canonical = set(), [], []
    for title in seed_titles:
        row = games_df[games_df['game_title'].str.lower() == title.lower()]
        if not row.empty:
            appid = row.index[0]
            seed_appids.add(appid)
            seed_vecs.append(game_vecs[appid_to_idx[appid]])
            canonical.append(row.iloc[0]['game_title'])

    query_vector = np.mean(seed_vecs, axis=0).reshape(1, -1)
    query_vector /= np.linalg.norm(query_vector)

    # Series prefix filter (M-bonus)
    prefixes = {_series_prefix(t) for t in canonical if len(_series_prefix(t)) >= 4}
    excluded = set(seed_appids)
    if prefixes:
        title_lower = games_df['game_title'].astype(str).str.lower()
        mask = pd.Series(False, index=games_df.index)
        for p in prefixes:
            mask |= title_lower.str.contains(p, na=False, regex=False)
        excluded |= set(games_df.index[mask].tolist())

    # FAISS search with headroom for exclusions
    distances, indices = faiss_index.search(query_vector, top_k + len(excluded))
    candidates = [idx_to_appid[i] for i in indices[0] if idx_to_appid[i] not in excluded]
    return {"candidates": candidates[:top_k], "query_vector": query_vector}
```

**`_series_prefix("DARK SOULS II")` → `"dark souls"`**.

### 6.5. `recommend_vibe` — 자연어 phrase 기반

```python
def expand_query_tags(parsed_json, top_k=5):
    query_vectors = []
    # 1. Gemini embed phrases → W_align projection → tag space
    if W_align is not None and parsed_json.get('phrases'):
        text_embs = self.embeddings.embed_documents(parsed_json['phrases'])
        for emb in text_embs:
            projected = np.dot(np.array(emb, dtype=np.float32), W_align)   # 3072 → 128
            query_vectors.append(projected)

    # 2. Existing target_tags의 tag_vec도 추가
    for tag_info in parsed_json.get('target_tags', []):
        if tag_info['name'] in tag_to_idx:
            query_vectors.append(tag_vecs[tag_to_idx[tag_info['name']]])

    # 3. Mean + cosine top-K nearest tags
    final_qv = np.mean(query_vectors, axis=0).reshape(1, -1)
    sims = cosine_similarity(final_qv, tag_vecs)
    sorted_idx = np.argsort(sims[0])[::-1]

    # Top-K tags as expanded target_tags
    for idx in sorted_idx[:top_k]:
        parsed_json['target_tags'].append({"name": idx_to_tag[idx], "weight": float(sims[0][idx])})
    return parsed_json

def _create_query_vector(parsed_json):
    final = np.zeros(tag_vecs.shape[1], dtype=np.float32)
    for tag_info in parsed_json.get('target_tags', []):
        if tag_info['name'] in tag_to_idx:
            w = tag_info.get('weight', 1.0)
            if not np.isfinite(w): continue
            v = tag_vecs[tag_to_idx[tag_info['name']]]
            if not np.all(np.isfinite(v)): continue
            final += v * w
    for tag in parsed_json.get('avoid_tags', []):
        if tag in tag_to_idx:
            final -= tag_vecs[tag_to_idx[tag]]
    if not np.all(np.isfinite(final)):
        return np.zeros_like(final)
    return final

# recommend_vibe core
expanded = expand_query_tags(parsed_json)
query_vector = _create_query_vector(expanded).reshape(1, -1)
query_vector /= max(np.linalg.norm(query_vector), 1e-12)
_, indices = faiss_index.search(query_vector, top_k + 1)
candidates = [idx_to_appid[i] for i in indices[0]]
```

### 6.6. `recommend_hybrid` — 게임 + 자연어 결합

```python
game_title = parsed_json['games'][0]
base_game_vec = game_vecs[appid_to_idx[appid_of(game_title)]]

expanded = expand_query_tags(parsed_json)
vibe_vec = _create_query_vector(expanded)

weights = parsed_json.get('weights', {"similar_weight": 0.5, "vibe_weight": 0.5})
query_vector = (weights['similar_weight'] * base_game_vec
                + weights['vibe_weight'] * vibe_vec).reshape(1, -1)
query_vector /= np.linalg.norm(query_vector)
```

### 6.7. `rerank_candidates` — Signed Sigmoid + MMR

**(a) Per-signal raw scores**

```python
rel_raw = V @ qv                                  # cosine to query, shape (n_cand,)
rel = minmax(rel_raw)                             # [0, 1]

probs = np.maximum(pop / pop.sum(), 1e-12)
nov_raw = -np.log2(probs)
nov = minmax(nov_raw)                             # [0, 1]
```

(Note: M11에서 Serendipity slider 제거. Serendipity@K **metric**은 `evaluation/metrics.py`에 유지하지만 rerank의 user control axis에서는 제외.)

**(b) Signed centering + sigmoid modifier**

```python
def sigmoid_modifier(slider, k=3.0):
    s = (slider - 5.0) / 5.0
    return 2.0 / (1.0 + math.exp(-k * s)) - 1.0
```

- $\text{sigmoid\_modifier}(5) = 0$
- $\text{sigmoid\_modifier}(10) \approx +0.91$
- $\text{sigmoid\_modifier}(0) \approx -0.91$

```python
nov_centered = 2 * nov - 1                        # [-1, +1]; niche=+1, popular=-1

nov_mod = sigmoid_modifier(w_nov)                 # signed
div_mod = sigmoid_modifier(w_div)
```

**(c) Base score** (3-axis: rel = positive-only weight, nov = signed):

$$
\text{base}_i = \frac{w_{\text{rel}}}{10} \cdot \text{rel}_i + 0.5 \cdot \text{nov\_mod} \cdot \text{nov\_centered}_i
$$

**(d) MMR selection** (greedy):

```python
sim_penalty = max(div_mod, 0.0) * 0.5

selected, remaining = [], list(range(n_cand))
for _ in range(top_n):
    if not selected or sim_penalty <= 0:
        pick = max(remaining, key=lambda i: base[i])
    else:
        sel_V = V[selected]
        sim_to_sel = (V[remaining] @ sel_V.T).max(axis=1)
        mmr_score = (1 - sim_penalty) * base[remaining] - sim_penalty * sim_to_sel
        pick = remaining[np.argmax(mmr_score)]
    selected.append(pick)
    remaining.remove(pick)
```

**출력**: DataFrame with columns `[game_title, tags, relevance_score, novelty_score, base_score, tag_match_score, final_score]`, top-N rows.

### 6.8. `response_generator_node` — 자연어 응답

LangChain `LLMChain`. Prompt template (`prompts/response_generator.txt`):

```
**Core Rules:**
1. You MUST mention EVERY SINGLE game in the list below. Do not skip any
   game. If 5 games are provided, your response must contain exactly 5
   bullet points — one per game.
2. You MUST NOT mention any game not in the list. ...
3. Output one bullet point per game, in the same order they appear ...
```

Context: `\n`.join(f"- Game: {row['game_title']}\n  - Matched Score: {row['tag_match_score']:.2f}").

LLM: `ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.2)`.

---

## 7. 서빙 UI

`serving/`. Streamlit multipage app.

### 7.1. `main.py`

```python
@st.cache_resource
def init_recommender():
    return VectorBasedRecommender(
        data_path=os.path.join(os.path.dirname(__file__), 'data'),
        embedding_model=os.environ.get("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-2"),
    )

@st.cache_resource
def init_llm():
    return ChatGoogleGenerativeAI(
        model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"),
        google_api_key=GEMINI_API_KEY,
        temperature=0.2,
    )

@st.cache_resource
def init_graph(_recommender, _llm):
    return build_graph(_recommender, _llm)
```

`graph.py`의 `build_graph`가 LangGraph topology 구성.

### 7.2. `pages/`

- `2_tag_map.py`: plotly UMAP scatter. Hover → 태그 + 인기 게임 Top 5
- `3_tag_graph_2d.py`: streamlit-agraph (vis.js / react-d3-graph) force-directed
- `4_tag_graph_3d.py`: vasturiano `3d-force-graph` (three.js)을 `streamlit.components.html`로 임베드

공통 데이터 로더: `serving/graph_data.py` — nodes (tag), edges (k-NN), color (cluster), size (game count log), hover (Top 5 인기 게임).

---

## 8. 하이퍼파라미터 전체

`config/default.yaml`:

```yaml
data:
  tag_vocab:
    min_votes: 5
  game_weights:
    weighting: bayesian            # mean | bayesian | variance
    prior_strength: 10
    gamma: 0.5
    score_col: s_round10_rec

models:
  tag_embeddings:
    embedding_dim: 128
    random_state: 42
  tag_effects:
    ridge_alpha: 1.0
    score_col: s_round10_rec
  game_vectors:
    kappa: 1.0
    alpha: 0.5                     # count compression
    eta: 0.0                       # β-axis steering (M9.D: 0.2→0, 효과 미미)
    ensemble_alpha: 1.0            # PPMI vs Item2Vec (M9.C: 0.7→1.0, Item2Vec OFF)
  text_alignment:
    lambda_reg: 0.01
    text_model: models/gemini-embedding-2
  item2vec:
    vector_size: 128
    window: 10
    min_count: 2
    epochs: 5
    sg: 1
    score_threshold: 7

retriever:
  top_k_default: 200
  expand_top_k: 5

rerank:
  # M11: 3-axis (Serendipity 제거 - Novelty와 popularity-기반 redundant)
  presets:
    beginner:    {relevance: 9, diversity: 4, novelty: 1}
    balanced:    {relevance: 5, diversity: 5, novelty: 5}
    heavy:       {relevance: 5, diversity: 7, novelty: 8}
  mmr_lambda: 0.5
```

`.env`:
```
GEMINI_API_KEY=...
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-2
GEMINI_CHAT_MODEL=gemini-2.5-pro
STEAM_API_KEY=...
```

---

## 9. 실행 명령 모음

### 환경 셋업

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r pinned.txt           # 또는 pip install -e .
```

### 크롤링

```powershell
# Legacy (1031 풀)
python -m data_collection.crawlers.metacritic         # Selenium notebook
python -m data_collection.crawlers.steam_reviews
python -m data_collection.crawlers.user_reviews

# 새 경로 (10K 풀)
python -m data_collection.crawlers.steamspy --target-count 10000
python -m data_collection.crawlers.steam_appdetails --input outputs/steamspy_games.csv
python scripts/build_games_tags_csv.py                # SteamSpy → normalized CSV
```

### 학습 파이프라인

```powershell
python -m pipeline.orchestration.build_offline       # 전체. 끝에 sync_data 자동
# 또는 개별:
python -m pipeline.game_rec.data.user_scores
python -m pipeline.game_rec.data.tag_vocab
python -m pipeline.game_rec.data.game_tag_matrix
python -m pipeline.game_rec.data.game_weights
python -m pipeline.game_rec.data.game_popularity
python -m pipeline.game_rec.models.tag_embeddings
python -m pipeline.game_rec.models.tag_effects
python -m pipeline.game_rec.models.item2vec
python -m pipeline.game_rec.models.game_vectors
python -m pipeline.game_rec.models.text_alignment
python -m pipeline.game_rec.index.faiss_index
python -m pipeline.game_rec.index.tag_projection
python -m pipeline.game_rec.evaluation.quality
python scripts/sync_data.py
```

### 서빙

```powershell
streamlit run serving/main.py
```

### 평가

```powershell
# 라벨 필요
python -m pipeline.orchestration.benchmark --eval-set tests/evaluation_set.json -k 10

# 라벨 불필요
python -m pipeline.orchestration.llm_vs_system --preset beginner
python -m pipeline.orchestration.llm_vs_system --preset heavy --output-csv outputs/llm_vs_system_heavy.csv
```

### 테스트

```powershell
pytest tests/                       # 55건
```

---

## 10. 트러블슈팅

### 10.1. venv 의존성 충돌

`langchain-upstage 0.7.x`는 `tokenizers<0.21` 요구, `sentence-transformers 5.x`는 `tokenizers>=0.21` 요구. 새 venv에서 strict resolver가 거부.

**해결**: `pinned.txt`에서 `sentence-transformers>=4.0,<5` 사용 (4.x는 `tokenizers<0.21` 호환).

### 10.2. 비-ASCII 경로 + FAISS

Windows에서 한글 폴더명에 faiss `write_index` 실패 (narrow ANSI API). `_safe_write_index` / `_safe_read_index`가 tempdir 우회.

### 10.3. faiss_index가 옛 vector로 빌드

`faiss_index.py`의 default 경로가 `serving/data/`였을 때 build_offline 안에서 stage 순서가 outputs/에 write → serving/data/에서 read하던 mismatch. **해결**: default를 `outputs/`로 변경 + build_offline 마지막에 sync_data 자동 stage.

### 10.4. Gemini embedding 404

`text-embedding-004`가 langchain-google-genai 2.x의 v1beta API에서 deprecated. `gemini-embedding-2` 사용 (3072d).

### 10.5. Streamlit cache_resource 갱신 안 됨

`@st.cache_resource`는 인자 hash만 함, 파일 내용 변경 hash 안 함. 파이프라인 재학습 후엔 **streamlit Ctrl+C → 다시 실행** 필수.

### 10.6. tabulate 누락

`pandas.DataFrame.to_markdown` 호출 시 `Missing optional dependency 'tabulate'`. `pip install tabulate`.

---

## 부록 A. 알려진 한계

- Item2Vec은 user-favorite 시퀀스에서 학습. user_reviews.py가 첫 페이지(10건)만 받아 sentence 짧음. cold-start 게임은 PPMI fallback.
- 영문 리뷰만 수집. 한국어 텍스트 X.
- vibe 모드는 W_align Ridge의 sparse niche bias로 mainstream 정통작을 놓치는 경향. similar/hybrid는 OK.
- timestamp 없음 → sequence-based 모델 불가.

## 부록 B. 디렉토리 트리

(README.md의 디렉토리 섹션 참조)
