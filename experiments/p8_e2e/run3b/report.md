# P8 e2e — run3b

## constraint_coop_kr — PASS
- query: 협동 가능하고 한국어 되는 게임
- route: library (expected ['anonymous', 'library']) | cands 300 → filtered 83 | 21.8s
- constraints: {'coop': True, 'multiplayer': True, 'korean': True} | relaxed: []

## constraint_price — PASS
- query: 2만원 이하 협동 게임
- route: library (expected ['anonymous', 'library']) | cands 300 → filtered 99 | 67.6s
- constraints: {'coop': True, 'multiplayer': True, 'max_price': 20000} | relaxed: []

## anonymous_no_lib — PASS
- query: 차분하고 분위기 좋은 인디 게임
- route: anonymous (expected ['anonymous', 'general']) | cands 8 → filtered 8 | 163.0s

**3/3 PASS**