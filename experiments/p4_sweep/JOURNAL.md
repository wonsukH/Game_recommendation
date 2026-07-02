# P4 탐색 저널 (append-only) — 자율 운행 2026-07-03 금 → 07-06 월 정오 KST

> **유형**: reasoning-log · **상태**: active · **갱신**: 2026-07-03

> 목적: 진화 탐색의 "유전 기억" + 사용자 부재 중 모든 판단의 감사(audit) 근거.
> 기록 명세(사용자 요구): 후보별 = 식·특징·생성가설·전 관문 점수·사망 지점/사유 / 라운드별 = 순위+CI·왜 이겼/졌나·다음 후보 선정 기준·**안 판 방향+이유**·전환/재량 판단 근거. 재량 랭커 재확인도 사유·결과 기록.
> 규칙: 질문 금지·정지 금지·Gemini 지출 금지·파괴적 작업 금지. 갈림길 = 플랜 결정 + 보수적 기본값.

---

## [2026-07-03 18:55] T0 — 자율 운행 개시
- 플랜 승인(사용자, ExitPlanMode) 직후. 인프라: 절전 차단(powercfg AC sleep/hibernate/disk=0) ✅ · 하트비트 크론(매시 :23, 세션 한정 — Claude 앱 자체가 죽으면 하트비트도 소멸: 내부에서 복구 불가한 잔여 위험으로 기록) ✅ · RUNSTATE/JOURNAL 생성 ✅.
- 크롤: games-only 가동 중(백로그 ~20.7k, ETA ~07-04). 완주(CAUGHT UP) 감지 시 daily_crawl.bat(users+games)로 전환 예정 — 매 틱 워치독이 확인.
- 다음: Step 0 영속화(DELIBERATION_LOG·memory·커밋) → rtime 진단.

## [2026-07-03 19:10] T1 — 기간 연장 + rtime 진단 종결
- **사용자 지시: 자율운행을 "멈출 때까지, 최대 7일(~07-10)"로 연장.** 하트비트 크론 재생성(65d87cfd, 7일 자동만료와 일치). 월 정오 보고 = 체크포인트.
- **rtime 진단 (Task 3 종결)**: GetOwnedGames를 ①현행 파라미터 ②extended(include_extended_appinfo) ③skip_unvetted 3종으로 프로브 → **전부 rtime_last_played 부재(0/328)**. 결론: 파싱 버그가 아니라 **Valve가 서드파티 키에 필드 자체를 미반환**(그래서 크롤분 전부 NULL). 판단: 플랜 contingency 발동 — ⓐ 적합도 시간축 → **무작위 70/30 fallback**(기존 관례와 동일, 0.293 재현 프로토콜과도 일치해 오히려 비교 일관성↑) ⓑ recency 내재신호 = playtime_2weeks + recently 테이블 ⓒ **owned 백필 스킵**(rtime 없이는 목적 상실, Δ미니샘플은 미사용 확정[사용자] → 1.7k콜 절약, games 크롤에 양보). 부수 확인: extended 파라미터가 has_dlc/has_market/has_workshop 필드를 줌 — 지금은 미사용, 기록만.
- 다음: Step 0 영속화 → Step 1-2 코딩(behavioral_extract + registry).

## [2026-07-03 19:55] T2 — Step 0 완료 + Step 1-2 완료
- **Step 0**: DELIBERATION_LOG에 플랜 결정 서사 append, memory 3건(p4-autonomous-run·discuss-before-finalize 신규 + MEMORY.md 인덱스), 커밋 `361fdc0` push.
- **워치독**: 크롤러 생존(2proc), 백로그 20,691→19,744, typed 19,925/40,615(49%).
- **Step 1 `behavioral_extract.py`**: 1,669명·693,276 상호작용(공개·완료 유저만)·played 371,551·업적행 283,791. **풀 19,734**(type='game'∧미출시제외; untyped 20,673 잠정 제외 — 크롤 후 재추출로 확장). **발견: owned에는 DLC가 거의 안 옴**(typed 중 non-game 208뿐 — GetOwnedGames가 DLC를 별도 앱으로 안 줌) → DLC-오염 걱정은 과대평가였음, 필터는 유지(사운드트랙/데모 208개 제거).
- **Step 2 `behavioral_scores.py`**: Round-0 씨앗 10종 등록(anchor 2 + rank 3 + magnitude 1 + parametric[p-value seed] 1 + achievement 3). 전부 스모크 통과, 후보당 0.1~4s(예상보다 빠름 — 라운드 비용 하향 조정 가능). 분포 sanity OK(pctl류 mean 0.5, binary 184k행).
- 다음 틱: Step 3 `preference_sweep.py`(깔때기+지표+리더보드) → 3.5 검증(0.293).

## [2026-07-03 06:37 — 시각 정정] 하트비트 틱: 타임스탬프 버그 교정
- 위 T0~T2의 "18:55/19:10/19:55" 표기는 **오기**(실제 새벽 ~06:1x~06:3x — 시스템 시계 확인 없이 추정 기입한 실수). 이후 모든 타임스탬프는 `date` 실측으로 기입.
- **교정 이유(중요)**: RUNSTATE의 미래-시각 heartbeat는 staleness 판정을 ~13h 무력화 → 진짜 사망을 가림. last_tick_ts를 실측(06:37:30)으로 수정. 하트비트 틱 자체는 "주 루프 생존(wakeup 06:39 예약)" 확인 후 종료 — 설계대로 cheap exit.

## [2026-07-03 06:48] T3 — Step 3 하니스 구축 + 스모크에서 조기 발견 2건
- **워치독**: 크롤러 생존, 백로그 19,629, CAUGHT UP 아직.
- **`preference_sweep.py` 구축**: 패널 동결(train 1,133/dev 200/private 150, 자격 rel-item≥12) · 중립 타깃 rel=max(pt-pctl, completion-pctl) per-game · 공통 70/30 split · GradedCF(가중 condcos, **C 비물질화 — 프로필-합집합 컬럼만 청크 계산**, per-edge count floor 정확 유지) · RP3β · graded NDCG/recall/SNIPS/long-tail + bootstrap CI · 보수적 prefilter.
- **버그 2건 수정**: ① RP3β 전이곱 차원(walk = Pu.T@(PiT.T@v)로 정정) ② prefilter가 binary 앵커를 분산-붕괴로 오인 컷 → anchor/binary family 면제.
- **조기 발견 A (설계 반영)**: random_s(가중치만 랜덤·support 실제)가 pctl_game과 근접(NDCG 0.165 vs 0.181) → **support(누가-뭘-플레이)가 그래프 신호의 지배 성분, 가중은 2차 이득**. random_s는 "가중치-널 프로브"로 재해석하고, **진짜 널 `random_support`**(support 파괴) 추가 → 0.122로 명확 분리 = 지표 건강 확인. 함의: 그레이드 변형 간 델타가 작을 수 있음 — CI 병기·paired 비교가 더 중요해짐; binary 앵커와의 비교가 "그레이드 정당화"의 핵심 시험이 됨.
- **조기 발견 B**: RP3β를 binary로 만들면 후보-무차별(candidate-blind) → **후보의 가중 X로 워크 구성**하도록 수정 — 이제 이중 관문이 진짜 두 관점(0.256 vs 널 0.079 분리 확인).
- Step 3.5(0.293 재현) 백그라운드 실행 중(p4_step35_repro). 완료 시 Round 0(dev 200명, 전 후보 11종) 착수.
