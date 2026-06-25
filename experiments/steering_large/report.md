# F novelty-steering validation — run `steering_large`

1800 users; 153 have >=1 NEW-genre held-out game (<0.34 of its tags in profile). recall@20, leave-user-out.

| config | new-genre recall [CI] | overall recall [CI] |
|---|---|---|
| cf | 0.0098 [0.0000,0.0261] | 0.2203 [0.2073,0.2341] |
| nov_b1 | 0.0784 [0.0392,0.1242] | 0.1425 [0.1306,0.1544] |
| nov_b2 | 0.1209 [0.0719,0.1732] | 0.0892 [0.0794,0.0986] |
| nov_b3 | 0.1209 [0.0719,0.1765] | 0.0606 [0.0529,0.0686] |

Δ vs plain CF (paired):

- nov_b1: new-genre +0.0686 [+0.0327,+0.1111] SIG; overall -0.0778 [-0.0889,-0.0668] SIG
- nov_b2: new-genre +0.1111 [+0.0654,+0.1634] SIG; overall -0.1311 [-0.1444,-0.1189] SIG
- nov_b3: new-genre +0.1111 [+0.0621,+0.1634] SIG; overall -0.1596 [-0.1732,-0.1465] SIG

- **best config (new-genre recall, CI>0): nov_b2**

## 해석
- best가 있으면: 인접노벨티 스티어링이 유저 본인의 *신장르 분기 행동*을 plain-CF보다 잘 회복(비순환 입증).
- overall recall 트레이드오프 정직 보고: 신장르↑가 전체↓를 동반하면 그 폭을 명시(스티어링은 의도적 탐색 모드).
- 측면 스티어링은 별도(기계적 aspect-match + blinded judge).