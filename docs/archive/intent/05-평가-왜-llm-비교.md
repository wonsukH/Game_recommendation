# 5. 평가 — 왜 LLM 비교?

> **유형**: design-spec · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [INTENT.md](../INTENT.md) · 정본: [README.md](../../README.md) · [ROADMAP.md](../ROADMAP.md)


## 원래 계획: ideal label 30개 라벨링

문제: **만 개 게임을 다 알아야 30개 query에 ideal recommendation 5-10개를 정할 수 있음**. 비현실적.

## 새 framework: LLM 단독과 비교

**아이디어**: ground truth label이 없어도, "LLM 단독 추천과 우리 시스템 추천을 비교"하면 정량적으로 차이를 측정 가능.

**최종 채택 metric (외부 어필용)**:
- **Pool Coverage Miss**: LLM 추천이 도메인 풀(9,956) 외부 비율 — 운영 통합 시 dead link 위험
- **True Hallucination**: Steam Storefront API cross-check로 진짜 hallucination 분리 (Pool Miss와 다름 — 풀 외부지만 실존하는 게임이 대부분)
- **Genre Precision**: 시스템 추천이 쿼리의 명시 카테고리 태그를 보유한 비율 (Steam 사용자 vote 기반 객관 측정)

**검토했지만 의도적으로 제외한 metric**:
- **Overlap@5 / ILD**: 두 시스템 목표가 다름 (LLM=풀 외부 mainstream, 시스템=풀 내부 검증 추천)에서 비롯되는 자연 차이라 외부 어필 부적합. 내부 ablation 도구로만 활용.
- **LLM-as-Judge** (Gemini에게 "추천이 적합한가?"): 시도했지만 LLM이 niche indie game을 모를 때 unfair한 결과. 시스템이 추천한 정통 roguelike 5개를 LLM에 직접 물어봐 검증 → 2개 unknown, 1개 부분 인지 → bias 입증 → portfolio에서 제외. **잘못된 metric을 명시적으로 빼는 자기 검증도 평가 framework의 일부**.

**측정 못 하는 것**: 절대 정확도 (둘 다 추천이지 정답 아님). 다만 **상대 차이 + 객관 태그 매칭은 충분히 의미 있음**.

## 30 query 결과 요약

- **우리 시스템 추천은 100% 도메인 풀 내** (운영 통합 가능). LLM 단독은 7.3%가 풀 외부.
- **Genre Precision 90.7%** (시스템 추천이 명시 카테고리 태그를 객관적으로 정확히 매칭). 3 fix (Hybrid 2-stage + parser lock 동적 weight + tag alias 매핑)를 통해 76.7% → 90.7% 누적 개선.
- **niche 발굴은 우리만 가능** (Stardew Valley 같은 유명한 거 말고 indie 발굴) — LLM-as-Judge bias의 원인이기도

**결론**: 두 시스템 **보완 가치**. 시스템의 차별점은 **운영 통합 가능성 + 카테고리 객관 정확도 + niche 발굴**. LLM은 mainstream 친숙도 측면에서 강점. 같은 metric으로 비교 부적합 → 다른 metric으로 각자 평가.

---
