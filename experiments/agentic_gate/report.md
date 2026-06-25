# Phase D — Agentic orchestration value (run `agentic_gate`)

60 user-pairs, behavioral hold-out, deterministic (no LLM/judge). 95% bootstrap CI.

## Test 1 — MULTI-ENTITY ('me + friend'), k=20  [the gate]

| system | recall A | recall B (friend) | min(A,B) = serves both |
|---|---|---|---|
| non-agentic (A만) | 0.308 [0.225,0.392] | 0.028 [0.006,0.058] | 0.011 [0.000,0.028] |
| **agentic (A+B 융합)** | 0.119 [0.072,0.172] | 0.119 [0.072,0.172] | **0.031 [0.008,0.058]** |

- **agentic − non, min(A,B)** = +0.019 [+0.000,+0.044]  (ns)
- agentic − non, friend(B) recall = +0.092 [+0.050,+0.139]  (SIG)

## Test 2 — over-constrained completeness (descriptive)  constraints={'coop': True, 'max_price': 10.0, 'released_after': 2018}

- non-agentic returns/k = 0.421 [0.371,0.473]
- agentic returns/k     = 0.977 [0.947,0.998]  (refine relaxes softest constraint to fill K)

## Decision (pre-registered)

**SIMPLIFY → single-pass (agentic 미입증)** — multi-entity min-recall: non=0.011 vs agentic=0.031.

## 해석
- 단일패스는 친구(B)를 구조적으로 무시 → B-recall 낮음. agentic은 두 라이브러리 융합 → 둘 다 served.
- 이건 LLM이 더 똑똑해서가 아니라 *오케스트레이션*(다중주체 융합)이 주는 가치 → 진짜 agentic 차별점.
- (참고) 단발·단일주체 단순 추천이면 agentic은 과함; 가치는 복합/다중주체에서 발생.