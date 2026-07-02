# P4 자율 운행 체크포인트 보고서 — 월요일 정오용 (초안, 지속 갱신 중)

> **유형**: experiment-report · **상태**: active · **갱신**: 2026-07-03 (금 — 초안 v1)

> 읽는 순서: 이 보고서(요약·결정 항목) → `LEADERBOARD.md`(shortlist 상세) → `JOURNAL.md`(전 과정 서사·감사) → 개별 run 디렉토리(수치).

## TL;DR
금요일 하루에 **P4 shortlisting이 사실상 완료**됐습니다: 하니스 구축 → 0.293 정확 재현 → Stage A 진화 5라운드(46평가) → Stage B 랭커 일제전(11구성) → Stage C 소교차+패자부활전 → **private 패널 검증**까지. 최종 shortlist 4개(S1~S4)가 동결됐고, 가장 큰 서프라이즈는 **user-KNN이 프로덕션 condcos 공식을 유의하게 이긴 것**(+0.0242)과 **당신의 p-value seed가 부활전을 거쳐 private 1위(0.2943)**가 된 것.

## 결정해주셔야 할 것 (우선순위순)
1. **랭커 교체 여부**: user-KNN·RP3β가 condcos(프로덕션 공식)를 이김. P5 재배선 시 교체 vs 유지 — 서빙 구조 영향 있음. *권고: 10k 유저 재평가·OOD와 묶어 판단(1.1k에서의 순위가 규모에서 바뀔 수 있음 — EASE도 10k 재평가 플래그).*
2. **Shortlist 최종 선정**(S1~S4 중 1~2개) → P6 OOD 재실험 대상.
3. **유저-크롤 업적 스코프**: Stage A 판정 — **완료율(이미 dense)만 유효, 희귀도(global_pct)는 P4 신호에 불필요**했음. 유저당 ~170콜(96%)인 업적 콜을 allowlist/축소하면 10k 도달 대폭 가속 가능. *단 P7(학습형 선호가중)의 rarity 활용 여지는 남음 — 완전 중단 전 검토.*
4. (가벼움) 학습형 #20 결과 처리 — 아래 참조.

## Shortlist (private 150명 검증 — 상세 LEADERBOARD.md)
S1 pvalue×userKNN **0.2943** / S2 pctl×userKNN 0.2925 / S3 cap_blend×RP3β(발굴·SNIPS 최고) / S4 cap_blend×condcos 0.2667(프로덕션-호환). null 바닥 분리 ✓, dev→private 순위 재현(과적합 없음) ✓.

## 크롤 현황
- games-only 진행: 백로그 28.8k → **(갱신 중)** — CAUGHT UP 시 users+games 복귀(자동 감시).
- 유저 1,669(분석 풀) — 유저 크롤은 완주 후 백그라운드 재개 예정.

## 실행 중 이슈·에러 로그 (전부 저널에 상세)
- rtime: Valve가 3rd-party 키에 미반환 확정 → 무작위 70/30 fallback (프로토콜상 무해).
- 3.5 1차 실패(원인: CLI 기본값≠manifest 설정) → manifest 기준 재실행으로 해소. 교훈 저널화.
- venv shim 오판으로 크롤러 1회 중단(즉시 복구, 손실 0), RUNSTATE 미래-시각 버그 교정.
- 소셜 F5 측정불가(in-cohort 친구 간선 20개) — 10k+·스노볼 후 재개 항목.

## 잔여 위험 (구조적으로 못 본 곳)
in-cohort 편향(최종 판정은 P6 OOD) · 풀 성장 중(절대값 라운드 간 비교 불가, ref로 통제) · long-tail 슬라이스 사실상 미측정(rp3b만 non-zero) · EASE/랭커 순위의 규모 의존성.

## 학습형 #20 · 주말 잔여 작업 로그
- **학습형 blend: 음성(사전 선언대로)** — train-내부 12-simplex 탐색의 최적 가중도 dev에서 pctl 단독 대비 +0.0013 ns. ROADMAP P7의 "지면 음성결과로 고정식 유지" 조항 이행: **학습형 선호가중은 현 규모에서 불채택**, 단순 형태(pctl/pvalue)가 최종. (10k·OOD에서 재시도 여지는 열어둠 — P7의 rarity 활용과 함께.)
- 이후: games 크롤 완주 감시 → users 복귀 / 풀 성장 시 top-4 재확인 / 이 보고서 갱신.
