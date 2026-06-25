# Ranker benchmark — CF vs classical recsys — run `rankerbench_main`

200 hold-out users, recall@20/ndcg@20, item universe 6487 (support>=3), leave-user-out. base = cf.

| method | recall@20 [CI] | ndcg@20 [CI] | Δrecall vs CF |
|---|---|---|---|
| pop | 0.0783 [0.0467,0.1125] | 0.0339 [0.0196,0.0510] | -0.1250 [-0.1775,-0.0733] SIG |
| cf | 0.2033 [0.1542,0.2517] | 0.1039 [0.0759,0.1335] | —(base) |
| ease | 0.2000 [0.1533,0.2492] | 0.0982 [0.0733,0.1245] | -0.0033 [-0.0325,+0.0283] ns |
| als | 0.1742 [0.1283,0.2200] | 0.0756 [0.0534,0.1003] | -0.0292 [-0.0792,+0.0184] ns |

- **winner (recall): cf**

## 해석
- EASE/ALS가 CF를 유의하게 이기면 → 그게 에이전트 밑 랭커로 채택할 후보(품질 향상). CF가 비등/우위면 단순 CF 유지 정당.
- 어느 쪽이든 '두 타워보다 낫다'는 직접 주장은 아님(EASE는 통제연구에서 다수 neural을 이기는 강baseline이므로, EASE 대비 위치가 곧 전통 recsys 대비 위치의 보수적 하한).
- 랭커는 교체 가능한 도구 — agentic 레이어(NL·다중주체·제약·스티어링·설명)는 불변.