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
