# D4 library-richness (profile-size) — run `libraryrichness_20260625_014020`

0 users (>= 11 liked, 0 eligible), FIXED 30% holdout, recall@20; reveal first p profile games to leave-user-out CF.

| profile size p | recall@20 [CI] |
|---|---|
| 1 | 0.0000 [0.0000,0.0000] |
| 2 | 0.0000 [0.0000,0.0000] |
| 3 | 0.0000 [0.0000,0.0000] |
| 5 | 0.0000 [0.0000,0.0000] |
| 8 | 0.0000 [0.0000,0.0000] |

- p=1→8 Δ = +0.0000 [+0.0000,+0.0000] (ns); monotonic=True
- last step (p=5→8) Δ = +0.0000 [+0.0000,+0.0000] (ns (saturating))

## 해석
- recall이 p와 함께 유의·단조 상승 → **라이브러리 풍부도가 큰 레버** → GetOwnedGames(수백 게임) 입력이 프록시(평균 3) 대비 큰 이득. 라이브 통합 정당화.
- last step 유의면 미포화(아직 더 늘릴 여지). ns면 수확체감 시작점.
- 캡(10)보다 실현 평균(3.05)이 진짜 병목 — 풍부한 입력만으로 모델 변경 없이 개인화 향상.