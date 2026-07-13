# 6. M9 — Vibe 약점 풀기 시도 + 결과

> **유형**: design-spec · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [INTENT.md](../INTENT.md) · 정본: [README.md](../../README.md) · [ROADMAP.md](../ROADMAP.md)


## 시도한 것

**M9.A: W_align 학습 데이터 augmentation**
- 9956 게임의 description을 Gemini로 임베딩
- target은 그 게임의 top-5 vote 태그의 가중평균 tag_vec (tag space 유지로 정체성 보존)
- 의도: niche cluster bias 약화

## 결과 — 의외의 negative finding

`vibe_our_avg_pop` 7.19M → **4.64M (-35%)**. 의도와 정반대로 niche bias가 **강화**됨.

원인: 추가한 9956 description의 자연어 분포가 long-tail (niche가 mainstream보다 다수). Ridge가 다수파 niche cluster로 더 강하게 self-bias.

→ **revert**. M9.A는 negative finding으로 기록.

## M9.C ablation으로 답을 찾음

`ensemble_alpha` 값을 변경하며 비교:

| α | overlap@5 | vibe_our_avg_pop |
|---|---|---|
| 0.5 | 0.013 | 1.35M |
| 0.7 (옛 default) | 0.053 | 4.64M |
| 0.9 | 0.047 | 5.86M |
| **1.0 (Item2Vec OFF)** | **0.087** | **6.08M** |

**Item2Vec 자체가 noise였음**. 비활성하면 모든 지표 개선.

원인: `user_reviews.py` 페이지네이션 issue — user당 첫 페이지(10건)만 수집되어 Skip-Gram sentence가 짧음 → 학습 부실 → ensemble에서 noise 도입.

## 최종 채택

| 설정 | 옛 | 새 |
|---|---|---|
| W_align 학습 방식 | tag wrapper만 | **그대로 유지 (M9.A revert)** |
| `ensemble_alpha` | 0.7 | **1.0** (Item2Vec OFF) |
| `eta` (β-축) | 0.2 | **0** (β-축 OFF, 효과 미미) |
| 사용자 슬라이더 | 4-axis (Rel/Div/Nov/**Ser**) | **3-axis** (Rel/Div/Nov) — M11 |

결과: vibe 모드의 niche cluster bias 사실상 해소. 시스템 정체성 (태그 의미 기반 추천) 그대로.

## M11 — Serendipity slider 제거 (학계 표준 + UX 단순화)

Serendipity = Relevance × (1 - popularity_percentile). Novelty와 popularity 기반 redundant. 사용자 control 다이얼로는 두 슬라이더가 거의 같은 효과 (200 후보가 이미 cosine top이라 rel 곱이 미미).

학계 표준 (Adamopoulos & Tuzhilin 2014, Kotkov 2016 등): "Serendipity should not be directly optimized; it emerges from relevance + novelty combination". measurement metric으로만 사용하고 user-facing axis로는 두지 않는 게 일반적.

→ Serendipity slider 제거, 3-axis(Rel/Div/Nov)로 단순화. Serendipity@K **metric**은 `evaluation/metrics.py`에 측정용으로 그대로 유지.

정량 트레이드오프: 4-axis 대비 vibe_our_avg_pop 9.58M → 7.38M (입문자에서 popular boost 약간 약해짐). 다만 baseline(pre_m9a) 대비는 여전히 명확히 우세 (vibe_overlap 0.040 → 0.080, +100%). 학계 표준 + UX 깔끔함 우선.
