# Issue #15: Serendipity slider redundancy (M11에서 제거)

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md)


## Symptom

사용자가 4-axis rerank scheme (Relevance/Diversity/Novelty/Serendipity)을 검토하다 의문:
> "Serendipity는 Novelty와 너무 비슷한 신호 아니야? 둘 다 popularity 기반인데."

## Diagnosis

`Serendipity = Relevance × (1 - popularity_percentile)`의 식 분해:
- Relevance: Relevance 축에 이미 들어있음
- (1 - popularity_percentile): popularity 기반 — Novelty와 같은 source

→ Serendipity는 본질적으로 **Relevance × Novelty의 곱셈 변형**. 독립 신호 X.

또 학계 reference:
- Adamopoulos & Tuzhilin (2014): "Serendipity should not be directly optimized; it emerges from relevance + unexpectedness"
- Kotkov et al. (2016): "Serendipity = relevance + novelty + unexpectedness의 함수"

→ 학계 일반적 user-facing control은 **3-axis** (Rel/Div/Nov), Serendipity는 측정 metric용.

## Root Cause

원본 baseline이 4-metric 평가 framework (`pipeline/game_rec/evaluation/metrics.py`)을 만들었고, 그 4개를 그대로 user-facing slider로 옮긴 게 4-axis가 된 원인. **measurement metric**과 **user control axis** 구분 안 함.
