# F novelty-steering validation — run `steering_20260625_014419`

400 users; 22 have >=1 NEW-genre held-out game (<0.34 of its tags in profile). recall@20, leave-user-out.

| config | new-genre recall [CI] | overall recall [CI] |
|---|---|---|
| cf | 0.0000 [0.0000,0.0000] | 0.2025 [0.1746,0.2321] |
| nov_b1 | 0.0909 [0.0000,0.2273] | 0.1163 [0.0929,0.1392] |
| nov_b2 | 0.1364 [0.0000,0.2727] | 0.0671 [0.0500,0.0850] |
| nov_b3 | 0.1818 [0.0455,0.3636] | 0.0475 [0.0338,0.0621] |

Δ vs plain CF (paired):

- nov_b1: new-genre +0.0909 [+0.0000,+0.2273] ns; overall -0.0862 [-0.1121,-0.0633] SIG
- nov_b2: new-genre +0.1364 [+0.0000,+0.2727] ns; overall -0.1354 [-0.1638,-0.1087] SIG
- nov_b3: new-genre +0.1818 [+0.0455,+0.3636] SIG; overall -0.1550 [-0.1833,-0.1275] SIG

- **best config (new-genre recall, CI>0): nov_b3**

## 해석
- best가 있으면: 인접노벨티 스티어링이 유저 본인의 *신장르 분기 행동*을 plain-CF보다 잘 회복(비순환 입증).
- overall recall 트레이드오프 정직 보고: 신장르↑가 전체↓를 동반하면 그 폭을 명시(스티어링은 의도적 탐색 모드).
- 측면 스티어링은 별도(기계적 aspect-match + blinded judge).