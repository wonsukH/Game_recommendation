# D4 library-richness (profile-size) — run `libraryrichness_20260625_014052`

> **유형**: experiment-report · **상태**: active · **run**: `libraryrichness_20260625_014052` · **갱신**: 2026-06-25

300 users (>= 6 liked, 18197 eligible), FIXED 30% holdout, recall@20; reveal first p profile games to leave-user-out CF.

| profile size p | recall@20 [CI] |
|---|---|
| 1 | 0.0894 [0.0667,0.1128] |
| 2 | 0.1294 [0.1011,0.1572] |
| 3 | 0.1650 [0.1355,0.1956] |
| 4 | 0.1844 [0.1533,0.2150] |

- p=1→4 Δ = +0.0950 [+0.0700,+0.1200] (SIG); monotonic=True
- last step (p=3→4) Δ = +0.0194 [+0.0022,+0.0367] (SIG (not saturated))

## 해석
- recall이 p와 함께 유의·단조 상승 → **라이브러리 풍부도가 큰 레버** → GetOwnedGames(수백 게임) 입력이 프록시(평균 3) 대비 큰 이득. 라이브 통합 정당화.
- last step 유의면 미포화(아직 더 늘릴 여지). ns면 수확체감 시작점.
- 캡(10)보다 실현 평균(3.05)이 진짜 병목 — 풍부한 입력만으로 모델 변경 없이 개인화 향상.