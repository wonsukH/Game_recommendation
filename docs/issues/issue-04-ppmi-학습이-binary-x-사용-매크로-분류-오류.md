# Issue #4: PPMI 학습이 binary X 사용 → 매크로 분류 오류

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md)


## Symptom

DS II 기준 cosine top 10에 **`Outbreak: The Nightmare Chronicles`** (좀비 horror co-op)가 등장. cosine 0.918, rank 8/9955. 정통 후계 `Elden Ring`은 cosine 0.916 (rank 12)로 더 낮음. 사용자 직관: "Outbreak이 Elden Ring보다 다크 소울에 가깝다고?"

## Diagnosis

1. 코드 확인: `pipeline/game_rec/models/tag_embeddings.py:19`의 `--matrix` default가 `outputs/X_game_tag_csr.npz` (binary).
2. `outputs/X_game_tag_weighted.npz` (vote-count weighted)는 만들어져 있지만 학습에서 미사용.
3. binary X는 element가 0 또는 1. `Outbreak`이 "Souls-like" 태그를 1표 받았든 50000표 받았든 둘 다 1로 처리.
4. PPMI 계산 시 메인 태그와 곁다리 태그 구분 X → "Souls-like" 태그가 약하게 voted된 niche 게임이 강하게 voted된 main 게임과 같은 카테고리로 묶임.

## Root Cause

`pipeline/game_rec/models/tag_embeddings.py:19`, `pipeline/game_rec/models/game_vectors.py:22`의 default 경로가 binary X (`X_game_tag_csr.npz`). weighted X는 만들어 두고 사용 안 함.

## Fix

두 파일의 default를 weighted matrix로 변경:

```python
# tag_embeddings.py:19, game_vectors.py:22
parser.add_argument(
    "--matrix", type=str,
    default=str(Path("outputs/X_game_tag_weighted.npz")),
    help="Input CSR matrix path. Default uses vote-count weighted X ..."
)
```

`compute_ppmi_matrix(X, game_weights)` 함수 자체는 변경 0 (sparse matmul `X.T @ X`는 dtype 무관).

## Verification

DS II cosine 측정 (전후):

| 게임 | Before (binary) | After (weighted) | 변화 |
|---|---|---|---|
| DS II ↔ DS III | 0.960 | **0.971** | ↑ |
| DS II ↔ Elden Ring | 0.916 | **0.932** | ↑ (top-10 진입) |
| DS II ↔ Outbreak | 0.918 (rank 8) | **0.846** | ↓ (top-10에서 빠짐) |
| DS II ↔ Lies of P | rank 외 | **0.933 (top-10)** | ✅ |
| DS II ↔ Dragon's Dogma | rank 외 | **0.943 (top-10)** | ✅ |

매크로 카테고리 오류 해소.

## Lesson

- 데이터를 만들어 두고 학습에서 사용하지 않으면 dead asset. M3.1에서 weighted X를 만들었지만 학습 코드 갱신을 잊음.
- vote count weight는 "메인 태그 vs 곁다리 태그" 신호로 매우 강력. binary는 모든 태그를 동등 처리 → 매크로 분류 오류 위험.
- Spot check (cosine top-10)로 정량 진단 가능. 사용자가 잘 알 만한 게임 시드로 점검하는 게 효과적.

---
