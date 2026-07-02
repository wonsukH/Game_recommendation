# P4 종합 리더보드 — 최종 shortlist (2026-07-03, 자율 운행 1일차)

> **유형**: experiment-report · **상태**: active · **갱신**: 2026-07-03

> Stage A(선호 진화 R0~R4, 46평가) → Stage B(랭커 11구성 일제전) → Stage C(소교차+패자부활전) → **private 패널 1회 확인**(150명, 라운드 결정 미사용 — winner's curse 방어)의 최종 산출.
> 전 평가의 per-user CSV·config = `rounds/`·`stageB/`·`stageC/`·`private_check/`. 서사 = `JOURNAL.md`.

## 🏆 최종 shortlist (private 패널 기준, 사용자 확정 대기)

| # | 구성 (선호 × 랭커) | NDCG@20 | recall@20 | SNIPS | 성격 |
|---|---|---|---|---|---|
| S1 | **pvalue_lognorm_eb × user-KNN25** | **0.2943** | 0.1721 | 0.0878 | private 1위 — **패자부활전 부활자**(내재-외재 불일치→랭커 미스매치 실증). p-value seed의 승리 |
| S2 | **pctl_game × user-KNN25** | 0.2925 | 0.1724 | 0.0916 | S1과 통계 동률 — **가장 단순·해석 용이**(게임별 백분위 하나) |
| S3 | **cap_a03_blend04 × RP3β** | 0.2800 | **0.1756** | **0.0994** | **발굴형 대표**(SNIPS·recall 최고) — Pareto 비지배 |
| S4 | cap_a03_blend04 × condcos | 0.2667 | 0.1658 | 0.0860 | **프로덕션-호환 최선**(랭커 교체 없이 선호만 교체 시) |
| — | random_support × * (null) | 0.126~0.180 | — | — | 바닥 분리 ✓ (지표 건강) |

dev 상위권 = private 상위권 (패널 과적합 없음 확인).

## 핵심 발견 연쇄 (서사는 JOURNAL, 여기는 요약)
1. **support(누가-뭘-플레이)가 그래프 신호의 등뼈** — 가중은 2차 (smoke01).
2. **playtime 등급화 단독은 무익, 완료율(업적)이 유일한 유효 그레이드 신호** (R0, +0.0073 유의).
3. **per-user 질량 캡 = condcos에서의 최대 레버** (+0.0161 유의, 파밍 프로브 예측 적중) — 단 **condcos 전용**(userknn은 코사인 정규화가 이를 내장, Stage C).
4. **weighted-C 귀속**: 그레이드 이득의 ~75%는 그래프 간선 가중 (R3·R4 4사분면).
5. **랭커가 선호보다 큰 레버**: user-KNN이 프로덕션 condcos를 +0.0242 유의로 이김 (Stage B). EASE는 1.1k 유저에서 열세 — **10k 도달 후 재평가 필수**.
6. **Pareto 쌍 반복**: NDCG축(userknn/a03) vs 발굴축(rp3b/a0) — 단일 승자 강제 대신 비지배 쌍 유지.
7. **음성결과 전량 기록**: magnitude(3회)·D시간축·소셜(측정불가 20간선)·resid 과제거·AFK 중복·PPMI/Jaccard/EASE 열세.

## ⚠️ 사용자 결정 필요 (복귀 시)
- **랭커 교체 여부**: userknn/rp3b가 condcos를 이김 — P5 재배선 시 교체 vs 유지(서빙 구조 영향). 10k 재평가와 묶어 판단 권고.
- shortlist 최종 1~2개 선정(S1~S4) — OOD(P6) 재실험 대상.
- 유저-크롤 업적 allowlist: 완료율만 유효했으므로 **희귀도 크롤 없이도 P4 신호는 성립** — 업적 콜 스코프 재논의 여지.

## 잔여 위험 (구조적으로 못 본 곳)
- in-cohort dev/private 모두 같은 편향 코호트 — 최종 판정은 OOD(P6).
- 풀이 크롤과 함께 성장 중(round간 절대값 비교 불가 — ref로 통제).
- long-tail 슬라이스는 전 구성에서 ~0 (20k 풀 k=20의 구조적 어려움 + rp3b만 첫 non-zero).
- 학습형(#20) 미투입(단순 조합이 계속 개선 중이었음) — 주말 잔여 시간에 시도 예정.
