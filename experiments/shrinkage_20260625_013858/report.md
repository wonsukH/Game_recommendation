# D3 support-shrinkage sweep — run `shrinkage_20260625_013858`

> **유형**: experiment-report · **상태**: active · **run**: `shrinkage_20260625_013858` · **갱신**: 2026-06-25

150 hold-out users, recall@20, leave-user-out. sim ·= C/(C+λ). λ=0 is the current baseline.

| λ | recall@20 [CI] | Δ vs λ=0 [CI] |
|---|---|---|
| 0 | 0.2500 [0.1878,0.3133] | +0.0000 [+0.0000,+0.0000] ns |
| 1 | 0.2500 [0.1878,0.3144] | +0.0000 [-0.0200,+0.0200] ns |
| 3 | 0.2433 [0.1811,0.3067] | -0.0067 [-0.0268,+0.0133] ns |
| 5 | 0.2433 [0.1811,0.3067] | -0.0067 [-0.0268,+0.0133] ns |
| 10 | 0.2500 [0.1856,0.3145] | +0.0000 [-0.0267,+0.0267] ns |

- best λ=0 (0.2500); **adopt=False** (pre-registered: only if Δ>0 with CI excluding 0).

## 해석
- 채택이면 저-support 쌍 down-weight가 sparse 공출현에서 신호↑.
- 미채택이면 정직히 드롭: min_cooc≥3 floor + conditional-cosine이 이미 충분(추가 shrinkage 무익).