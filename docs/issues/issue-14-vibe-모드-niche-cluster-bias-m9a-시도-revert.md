# Issue #14: Vibe 모드 niche cluster bias (M9.A 시도 → revert → M9.C로 해소)

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md)


## Symptom

30 query 평가 (label-free `llm_vs_system.py`) 결과 — vibe 카테고리에서 **`My Beautiful Paper Smile`, `Strobophagia`, `Magnus Positive Phototaxis`, `A Detective's Novel`, `Bacteria`, `Puzzle Galaxies`** 가 카테고리 무관 **반복 등장**:

| Query (vibe 카테고리) | 우리 top 5 (실패 케이스) | LLM top 5 (정통) |
|---|---|---|
| q03 "마음 편하게 따뜻한" | Bacteria, Puzzle Galaxies, Cosmic Pioneer ... | Stardew, A Short Hike, Coffee Talk |
| q05 "짧은 로그라이크" | Bacteria, Puzzle Galaxies, The Next Door ... | Vampire Survivors, Hades, Slay the Spire |
| q12 "픽셀 RPG 감성적" | My Beautiful Paper Smile, Sanfu, Strobophagia ... | To the Moon, Stardew, Undertale, OMORI |

같은 niche 게임들이 다른 카테고리 query에 반복 등장.

## Diagnosis

1. 반복 등장 게임들의 popularity 확인: 약 890,000 owners (SteamSpy 가장 작은 owners range bucket).
2. game_vec 공간 안에서 좁고 dense한 cluster 형성 (atmospheric, psychological-horror, walking-simulator, surreal 같은 niche tag 공유).
3. 사용자 자연어 → Gemini embed → `W_align` projection → tag space → 매우 일관되게 이 niche cluster 근처로 falling.
4. 단일 강한 장르 시그널 (survival, rhythm, farming) query에서는 OK — projection이 mainstream tag로 정확히 매핑.
5. 복합/모호 자연어 (어두운+스토리, 픽셀+감성, 짧고 여운) 일 때 niche cluster로 self-bias.

## Root Cause

`pipeline/game_rec/models/text_alignment.py`의 W_align 학습 데이터가 **편향**:
- 학습 입력 = 447개 짧은 태그 wrapper 문장 (`"This is a souls-like game"`)
- 학습 target = 447개 tag_vec (PPMI+SVD)
- PPMI tag_vecs 공간에서 niche tag들이 sparse하고 강한 신호로 over-represent → Ridge가 niche 방향으로 학습 강함
- mainstream 태그(`action`, `indie`)는 PPMI에서 약화 → Ridge에서 약한 매핑
- 결과: 사용자 phrase의 자연스러운 자연어가 mainstream 매핑이 약해서 niche cluster로 falling

## Fix Path — M9.A 시도 → 의도 반대 효과 → revert → M9.C로 해소

### 시도 1: M9.A (description input augmentation)

학습 데이터의 input을 늘려 sparse niche cluster bias를 약화하려 함. **target은 tag space에 유지** (그 게임의 top-5 vote 태그의 vote-weighted 평균 vec) — 정체성 유지.

```python
# pipeline/game_rec/models/text_alignment.py — main()에 약 25줄 추가
# Stage 2: 게임 description Gemini embed → target = top-5 vote 태그 가중평균 tag_vec
T_combined = vstack([T_tag, T_game])      # (10497, 3072)
Y_combined = vstack([Y_tag, Y_game])      # (10497, 128) — 둘 다 tag space
W = Ridge.fit(T_combined, Y_combined)
```

CLI: `--include-descriptions` (default True). 학습 데이터 447 → 10,497, Ridge R² 0.40.

### 시도 1 결과 — **의도 반대**

`llm_vs_system.py` 30 query 평가:

| | `pre_m9a` (M9.A 전) | `a07` (M9.A 후) |
|---|---|---|
| `vibe_our_avg_pop` | 7.19M | **4.64M (-35%)** |

mainstream 추천 늘기를 의도했는데 **오히려 niche로 더 깊이 falling**.

**원인 진단**: 학습 데이터에 추가된 9956 게임 description의 자연어 분포가 **long-tail** (niche 게임이 mainstream보다 더 많음). Ridge가 다수파인 niche cluster로 더 강하게 self-bias. 학습 sample을 단순히 늘리는 게 root cause를 풀지 않고 오히려 강화.

→ **M9.A revert**: `text_alignment.py --no-include-descriptions`로 옛 방식 W_align 복원.

### 시도 2: M9.C ablation (`ensemble_alpha`)

α ∈ {0.5, 0.7, 0.9, 1.0} variant 학습 + 평가:

| variant | overall overlap@5 | vibe_overlap@5 | vibe_our_avg_pop |
|---|---|---|---|
| α=0.5 (Item2Vec 비중 ↑) | 0.013 | 0.000 | 1.35M |
| α=0.7 (기존 default) | 0.053 | 0.040 | 4.64M |
| α=0.9 | 0.047 | 0.027 | 5.86M |
| **α=1.0 (Item2Vec OFF)** | **0.087** | **0.080** | **6.08M** |

**α=1.0이 모든 지표 best**. Item2Vec 자체가 noise였다는 결정적 증거.

원인: `user_reviews.py` 페이지네이션 issue (각 user 첫 페이지 10건만 수집) → Skip-Gram sentence 짧음 → 학습 부실 → ensemble에서 noise.

### 시도 3: M9.D (`eta`)

η=0 (β-축 OFF) vs η=0.2: 차이 미미. R²=0.10인 약한 신호라 예상된 결과. **η=0** 채택 (단순화).

### 최종 (Final) — 채택

`config/default.yaml`:
- `ensemble_alpha: 0.7 → 1.0`
- `eta: 0.2 → 0`
- W_align는 M9.A revert (옛 방식, tag wrapper만)

30 query 재평가:

| 메트릭 | pre_m9a → final | 변화 |
|---|---|---|
| `overlap@5` | 0.060 → **0.087** | **+45%** |
| `our_avg_pop` | 6.22M → **7.91M** | +27% |
| `vibe_overlap@5` | 0.040 → **0.093** | **+133%** |
| `vibe_our_avg_pop` | 7.19M → **9.58M** | **+33%** |
| `llm_existence_rate` | 0.987 (유지) | hallucination 0% |

vibe 모드의 niche cluster bias **사실상 해소**. mainstream 정통작이 자연스럽게 진입.

## Verification

- `outputs/llm_vs_system_final.csv` + `outputs/ablation_summary.md`
- Streamlit에서 같은 vibe 쿼리 ("어두운 분위기 RPG") → niche 반복 등장 게임들 (`My Beautiful Paper Smile` 등) 빠지고 mainstream 정통작 진입

## Lesson

- **학습 sample을 단순히 늘리는 게 root cause를 풀지 않음**. Long-tail 분포라면 다수파(niche) bias가 오히려 강화됨. M9.A는 이를 정량 검증한 negative finding.
- **Ablation으로 가설 검증**. "Item2Vec이 도움 될 거라는 직관" vs "ablation 결과 noise였음" — 정량 측정이 직관을 뒤집음.
- **데이터 부실은 알고리즘 비활성화로 해결되기도**. user_reviews 페이지네이션 issue는 Item2Vec quality에 직결 → 데이터 수집 안 고치면 알고리즘 자체 끄는 게 best.
- **β-축 (tag_effects)** 같은 약한 signal(R²=0.10)은 처음부터 의심. ablation으로 확인 후 제거.
- **시스템 정체성 우선**: M9.A target에 game_vecs 넣자는 첫 제안을 사용자가 잡아냈음. 그게 정체성 약화로 갔으면 더 큰 후폭풍. target=tag space 유지는 옳았으나 학습 분포 문제로 실패. **정체성 유지 + 효과 확인 + revert** 같은 disciplined cycle이 중요.
- Label-free 평가 framework (`llm_vs_system.py`) 가치 — 이 모든 결정을 정량 근거 위에서 가능하게 함. ground truth label 없이도 정량.

---
