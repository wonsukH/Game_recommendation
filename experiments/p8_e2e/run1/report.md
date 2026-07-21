# P8 e2e — run1

## library — PASS
- query: 나한테 맞는 게임 추천해줘
- route: library (expected ['library']) | cands 300 → filtered 300 | 126.2s

## seed — **FAIL**
- query: 다크소울 같은 거
- route: library (expected ['seed']) | cands 300 → filtered 300 | 125.7s
- failing checks: ['ok_route_ok']

## explore — **FAIL**
- query: 안 해본 새로운 장르로 색다른 거
- route: library (expected ['explore']) | cands 300 → filtered 300 | 125.9s
- failing checks: ['ok_route_ok']

## multi — **FAIL**
- query: 나랑 친구 둘 다 좋아할 게임
- route: library (expected ['multi_entity']) | cands 300 → filtered 300 | 125.6s
- failing checks: ['ok_route_ok']

## constraint_coop_kr — PASS
- query: 협동 가능하고 한국어 되는 게임
- route: library (expected ['anonymous', 'library']) | cands 300 → filtered 300 | 125.6s

## constraint_price — PASS
- query: 2만원 이하 협동 게임
- route: library (expected ['anonymous', 'library']) | cands 300 → filtered 300 | 125.6s

## anonymous_no_lib — **FAIL**
- query: 차분하고 분위기 좋은 인디 게임
- route: anonymous (expected ['anonymous', 'general']) | cands 0 → filtered 0 | 188.6s
- failing checks: ['ok_cands_nonempty']

**3/7 PASS**