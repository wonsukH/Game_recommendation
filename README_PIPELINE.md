# 오프라인 파이프라인 상세

`pipelines/build_offline.py`가 차례로 호출하는 9개 모듈의 입출력 / 핵심 알고리즘 / 파라미터 정리. 각 단계의 디폴트는 `config/default.yaml`에서 오고 CLI 인자로 override 가능.

전체 실행:

```powershell
python -m pipelines.build_offline
```

---

## 데이터 흐름

```
crawlers/  ->  outputs/  ->  game_rec.data  ->  game_rec.models  ->  game_rec.index  ->  app/data/
                              + .index            + .evaluation
```

입력 CSV는 `outputs/`에 있다고 가정 (`steam_games_tags.csv`, `user_game_scores.csv`, `user_all_reviews.csv`).

---

## 각 단계

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
