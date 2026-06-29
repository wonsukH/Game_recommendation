# D1 cold-start fallback eval — run `coldstart_20260625_013732`

> **유형**: experiment-report · **상태**: active · **run**: `coldstart_20260625_013732` · **갱신**: 2026-06-25

150 hold-out test users, recall@20, leave-user-out CF from 141373 train users.

- **coverage**: pool 9956, CF-reachable 8604, CF-cold 1352 (13.6%) → content fallback makes 100% recommendable.
- recall@20: CF 0.250 [0.188,0.313] | hybrid 0.253 [0.191,0.318]
- Δ(hybrid−CF) = +0.0033 [+0.0000,+0.0100] (ns)
- **underfill rate** (CF returns < 20): 4.0% of users; fully-cold profile (CF returns 0): 0 users
- held-out liked games that are CF-cold (recovery ceiling): 0.3%
- recall on underfill users: CF 0.417 → hybrid 0.500

## 해석
- 콜드폴백의 1차 가치 = **커버리지(100%)와 콜드/얇은 프로파일 robustness**(CF가 0 주는 유저에 결과 제공).
- 일반 유저는 CF가 top-k를 채우므로 warm recall 불변(설계상). 전체 recall 리프트는 콜드 holdout 비중에 의해 상한.
- niche≠good(P2e) 교훈 반영: 콜드 후보는 user-score 품질게이트 통과분만. 스티어링(F)의 base 인프라.