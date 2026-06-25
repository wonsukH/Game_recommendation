# Phase D — Agentic orchestration value (run `agentic_fusion_sweep`)

60 user-pairs, behavioral hold-out, deterministic (no LLM/judge). 95% bootstrap CI.

## Test 1 — MULTI-ENTITY ('me + friend'), k=20 — fusion sweep  [the gate]

| system | recall A | recall B (friend) | min(A,B)=둘다 | Δmin vs non |
|---|---|---|---|---|
| non-agentic (A만) | 0.308 [0.225,0.392] | 0.028 [0.006,0.058] | 0.011 [0.000,0.028] | — |
| agentic:min | 0.119 [0.072,0.172] | 0.119 [0.072,0.172] | 0.031 [0.008,0.058] | +0.019 [+0.000,+0.044] ns |
| agentic:geomean | 0.161 [0.103,0.222] | 0.192 [0.128,0.256] | 0.047 [0.017,0.083] | +0.036 [+0.008,+0.069] SIG |
| agentic:balanced | 0.186 [0.125,0.253] | 0.253 [0.183,0.328] | 0.083 [0.042,0.133] | +0.072 [+0.033,+0.119] SIG |
| agentic:interleave ★best | 0.231 [0.156,0.306] | 0.281 [0.208,0.353] | 0.108 [0.061,0.158] | +0.097 [+0.053,+0.147] SIG |

- best fusion = **interleave**; agentic − non min(A,B) = +0.097 [+0.053,+0.147] (SIG)
- best fusion friend(B) recall Δ = +0.253 [+0.178,+0.331] (SIG)

## Test 2 — over-constrained completeness (descriptive)  constraints={'coop': True, 'max_price': 10.0, 'released_after': 2018}

- non-agentic returns/k = 0.421 [0.371,0.473]
- agentic returns/k     = 0.977 [0.947,0.998]  (refine relaxes softest constraint to fill K)

## Decision (pre-registered)

**KEEP agentic (fusion=interleave)** — multi-entity min-recall: non=0.011 vs agentic(interleave)=0.108.

## 해석
- 단일패스는 친구(B)를 구조적으로 무시 → B-recall 낮음. agentic은 두 라이브러리 융합 → 둘 다 served.
- 이건 LLM이 더 똑똑해서가 아니라 *오케스트레이션*(다중주체 융합)이 주는 가치 → 진짜 agentic 차별점.
- (참고) 단발·단일주체 단순 추천이면 agentic은 과함; 가치는 복합/다중주체에서 발생.