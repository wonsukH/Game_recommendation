# (b) LIVE library-richness — real GetOwnedGames — run `libraryrichness_live_20260625_031928`

> **유형**: experiment-report · **상태**: active · **run**: `libraryrichness_live_20260625_031928` · **갱신**: 2026-06-25

129 REAL public profiles (liked = in-pool playtime >= 120min; median profile-pool 78 games), FIXED 30% holdout, recall@20, production CF.

| profile size p | recall@20 [CI] |
|---|---|
| 1 | 0.0352 [0.0275,0.0433] |
| 3 | 0.0555 [0.0460,0.0648] |
| 5 | 0.0639 [0.0532,0.0749] |
| 10 | 0.0822 [0.0697,0.0957] |
| 20 | 0.1086 [0.0946,0.1238] |
| 30 | 0.1233 [0.1075,0.1389] |

- **crawl-realistic p=3 -> p=30**: recall 0.0555 -> 0.1233, Δ = +0.0678 [+0.0543,+0.0824] (SIG)
- last step (p=20->30) Δ = +0.0146 [+0.0073,+0.0222] (SIG — not saturated)
- monotonic increasing: True

## 해석
- 실제 라이브러리(중앙값 수백 게임)에서 프로파일 크기↑ → recall↑가 **크롤 캡(~3)을 한참 넘어 지속**되면, 오프라인 D4의 외삽이 실데이터로 **확정**된다 → GetOwnedGames 입력이 개인화의 가장 큰 레버.
- crawl-realistic(p=3) 대비 rich(p=hi) 격차 = GetOwnedGames 도입이 실제로 사주는 이득.