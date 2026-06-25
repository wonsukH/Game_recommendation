# Data-scaling (user-count axis) — run `datascaling_users`

Fixed 120 test users, hold-out recall@20; co-occurrence from X% of 141403 train users.

| users | recall@20 [CI] |
|---|---|
| 35350 (25%) | 0.192 [0.147,0.237] |
| 70701 (50%) | 0.246 [0.196,0.297] |
| 106052 (75%) | 0.254 [0.203,0.307] |
| 141403 (100%) | 0.268 [0.215,0.321] |

- 25%→100% recall Δ = +0.076 [+0.039,+0.117] (SIG)
- monotonic increasing: True

## 해석
- 유저 수↑ → recall 추세로 데이터 가치 판단. SIG 상승 & 미포화면 '더 늘리면 더 좋아짐'.
- (미측정) 유저당 라이브러리 풍부도(캡~10→GetOwnedGames 수백)는 더 큰 레버일 가능성 — 크롤 필요.