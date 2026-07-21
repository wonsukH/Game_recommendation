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

## [2026-07-03 06:52] T4 — Step 3.5 1차 실패 → 원인 규명 → 재실행
- **1차 실행 전원 0.000(ORACLE 포함)** = 재현 실패가 아니라 **자격 유저 0명**: CLI 기본 `min_liked=15`인데 리뷰 크롤 캡(~10/유저) 때문에 이 조건 충족 유저가 데이터상 0. 그런데 원 런은 78명을 썼음 → **원 런 manifest 확인: `min_liked=8`로 override 돼 있었음**(manifest에 설정·지문이 남는 RunLogger 관례 덕에 5분 만에 규명 — 관례의 가치 실증).
- **CSV 지문 대조: sha256 `ceb22b042cc21dae`·77,750,401B 완전 일치** — 복사해온 파일이 원본과 동일 확정.
- 재실행: `--min-liked 8 --seed 42`(p4_step35_repro2, 백그라운드). 기대 CF recall@20 ≈ 0.293(±CI). 교훈 기록: **재현은 CLI 기본값이 아니라 manifest의 실측 설정으로** — 앞으로 모든 재현·재실행은 manifest 우선.

## [2026-07-03 07:02] T5 — Step 3.5 통과 ✅ + Round 0 지형도 + Round 1 설계
- **3.5 정확 재현**: CF recall@20 = **0.293 [0.218,0.370]**(원 런과 동일치), ORACLE 1.000, POP 0.034 → 데탑 환경·CF 기계·지표 전부 원본 동치 증명. Task 5 완료.
- **Round 0 리더보드(dev 200, NDCG_cf)**: blend .2432 > mult .2393 > afk_gate .2372 > pctl_game .2359 > binary .2350 > pvalue .2296 > logratio .2276 > dblq .2253 > pctl_user .2210 > random_s .2091 > random_support .1585.
- **왜 이겼나(paired CI)**: ① **업적 top3 싹쓸이** — blend vs pctl_game **+0.0073 [+0.0036,+0.0110] 유의**, vs 이진앵커 +0.0082 유의(경계). ② **pctl_game vs 이진 +0.0009 ns → playtime 등급화 자체는 무익** — 그레이드의 가치는 전적으로 완료율 신호에서 옴(support-dominance 발견과 정합: 등뼈=support, pt등급≈0, 업적등급=진짜 Δ). ③ **RP3β 1위는 pvalue_eb(.2855, CF 6위)** — 선호×랭커 상호작용 실증 = 이중 관문 설계 적중. ④ 진짜 널 .1585로 바닥 분리(지표 건강 ✓). ⑤ long-tail: 78/200 유저만 lt-홀드아웃 보유·힛 0 — 지표 정상, 슬라이스가 어려운 것(20k 풀 k=20). 크롤 확장 후 재조명.
- **함의(유저-크롤 allowlist 입력)**: 완료율 리프트 유의 → 업적 콜은 신호 값어치 있음. 어떤 게임에서 값어치 있는지는 라운드 누적 후 판단.
- **Round 1 설계(가설주도, 14 spec)**: H1 완료율 강화 — blend lam 0.4/0.8 스윕, mult gamma 0.2, comp_afk_combo(1위×3위 결합), **resid2way_completion**(완료성향·난이도 주효과 제거 — C가족 ⭐) / H2 pvalue×walk 규명 — k_shrink 5/50 / H3 탐험쿼터 — bm25_sat(포화 magnitude, "magnitude 죽음이 포화 부재 탓?" 반명제), per_user_cap(#28 파밍 실증근거) / 기준선 4종 동봉.
- **안 판 방향+이유**: unlocktime D가족(extract에 unlocktime 미포함 — 확장 필요, R2 후보) · 소셜 friends/groups(별도 로더 필요, R2+) · graph-knob 분리(binary-C vs graded-C — 하니스 플래그 필요, R2) · EASE 조기 투입(Stage B에서 일제전이 원칙 — 단 pvalue×walk 상호작용이 커지면 재량 재확인 발동 고려).

## [2026-07-03 07:12] T6 — Round 1 결과: 탐험 쿼터의 승리 + Round 2 발사
- **리더보드(top)**: **per_user_cap .2521** > blend_lam04 .2450 > blend06 .2432 > mult_g02 .2430 > combo .2414 … bm25 둘은 pctl 이하, 널 .1585.
- **paired 판정**: ① **cap vs pctl +0.0161 [+0.0070,+0.0252] 유의** — 완료율 리프트의 2배. **새 지배 가설: 계정 편중(파밍/whale) 통제 = 최대 레버**(#28 프로브 실증근거가 예측 적중; 탐험 쿼터 3개 중 1개가 1위 = 매몰방지 장치의 즉각적 가치 실증). ② cap vs blend04 +0.0070 ns → **직교 레버 추정(계정축 vs 행신뢰축) → R2 최우선 = cap×blend 결합**. ③ blend lam 0.4≈0.6 플랫. ④ combo(blend×AFK) ns — 완료율이 AFK 정보 흡수(게이트 중복 무익, 음성결과). ⑤ **resid2way −0.0112 유의 악화** — 완료성향 주효과에 진짜 취향 포함, 과제거(음성결과·해당 형태 폐기). ⑥ pvalue: CF 무반응(k 스윕 무차별)·RP3β 최상위 유지(.2837/.2857) — walk-전용 프로필 확정, Stage B에서 재조명. ⑦ bm25 포화 magnitude도 실패 — "magnitude 무익" 반명제 시험까지 완료(탐험 쿼터의 정직한 음성결과).
- **Round 2(13 spec) 발사**: cap×blend(lam 0.2/0.4 × alpha 0/0.3/0.5) 그리드 소형 + blend lam 0.2/0.3 마무리 + 탐험(cap_dblq·cap_logratio — magnitude가 캡 하에 부활하는지) + refs.
- **안 판 방향+이유**: unlocktime·소셜·graph-knob 분리 — R3 이후(extract/하니스 확장 필요); EASE 재량 투입 보류(Stage B 임박).

## [2026-07-03 07:20] T7 — Round 2: 신기록 + Pareto 분기 발견
- **리더보드**: **cap_a03_blend04 .2621**(신기록) > cap_a03_pctl .2584 > cap_a0_blend04 .2571 > … > cap_logratio .2389 > pctl_ref .2359. 궤적 R0 .2432→R1 .2521→R2 .2621(라운드당 ~+0.010, plateau 아님 → A 계속).
- **paired**: ① 신기록 vs R1승자 **+0.0100 유의**. ② alpha 0.3>0.5 **+0.0101 유의**(캡 강화 이득), 0.3 vs 0 +0.0049 ns. ③ blend 한계기여 at a03: +0.0036 ns — cap이 완료율 이득 일부 흡수(둘 다 파밍 행 타격 = 겹침; 직교는 부분만). ④ **SNIPS에선 a0 > a03 +0.0099 유의 — Pareto 분기**: NDCG 최적(a03)≠인기보정 최적(a0, 완전균등질량=발굴형). **cap_a03_blend04(주축형)·cap_a0_blend04(발굴형) 둘 다 비지배 shortlist 유지**(플랜 Pareto 원칙 첫 실전 발동). ⑤ cap_dblq .2524 경쟁력(rank-double이 캡 하에 부활) / cap_logratio — **magnitude 3연속 사망 확정**(순수·포화·캡 하 전패 — 이 축 freeze).
- **freeze(ablation)**: magnitude 축 동결. combo(AFK×blend)·resid2way 형태 폐기 유지.
- **다음(R3)**: ⓐ extract 확장 — user_achievement에서 per-(u,g) first/last unlocktime → **D가족(recency·span·still-progressing)** 첫 투입 ⓑ **graph-knob 귀속 분리** — binary-C+graded-w_p 하니스 플래그(cap 이득이 그래프측인지 w_p측인지) ⓒ alpha 미세(0.2/0.35/0.4) 소형 ⓓ blend lam은 0.4 고정(플랫 확인됨).

## [2026-07-03 07:32] T8 — Round 3: 귀속 확정 + D가족 음성 + plateau 1연속
- **풀 성장 주의**: 크롤이 type을 채우며 풀 19,734→20,249 → 절대값 비교는 라운드 내 ref로만(설계대로). best 절대값 .2621→.2585는 풀 확대 효과지 퇴행 아님.
- **paired 판정**: ① **weighted-C vs binary-C +0.0392 유의(대차)** — cap 이득의 귀속처 = **그래프 간선 가중**(w_p 아님). 플랜의 두-knob gotcha 결정적 해소, weighted-C 확정. binary-C는 pctl_ref보다도 나쁨 — 간선 가중 제거가 cap 재분배 효과를 통째로 죽임. ② **D가족 음성**: recency +0.0009 ns·span −0.0009 ns — unlocktime 시간축은 이 그레인에서 무익(데이터는 dense했으나 신호가 rel과 겹침 추정). D축 freeze. ③ alpha 0.2≈0.3 플랫(robust). ④ **discovery(a0): NDCG −0.0011 ns + SNIPS +0.0128 유의** — R2(+0.0099)와 일관: **a0 = NDCG 무손실 인기보정 = 비지배 최강 후보로 부상**. shortlist 주력을 a0/a03 쌍으로.
- **plateau 카운트 1**(R3 유의 개선 0). 규칙상 R4 한 번 더 → 노이즈면 Stage B.
- **R4 계획(마지막 탐험 라운드)**: ⓐ 소셜 F5 — extract에 friends 조인(per-(u,g) n_friends_played) → social_boost 후보 ⓑ w_p-flat 귀속(weighted-C+균일 w_p — 반대쪽 knob 마무리) ⓒ (재량 재확인 후보) pvalue×walk은 Stage B에서 EASE·워크 계열과 함께 정식 비교.
- **안 판 방향+이유**: 학습형(#20 isotonic/GBM) — plateau 확정 후 Stage B 결과를 보고 투입 여부 판단(단순 조합이 아직 개선 중이었어서 보류했음; B 후 재평가). 의도 tier ablation — 팩-블록 전처리 필요, 우선순위 뒤.

## [2026-07-03 07:20] T9 — R4: 소셜 즉사(데이터 부재) + 귀속 4사분면 완성 → **Stage A 종료(plateau 2연속)**
- **소셜 F5 음성(데이터 부재)**: in-cohort 친구 간선 20/69,797(유저 16명) — 셔플 시드 리뷰작성자끼리 친구일 확률≈0. **social_boost 시도 자체가 불가** → F5는 10k+·스노볼 발동 후 재개 항목으로 이관(음성 아닌 '측정불가' 기록).
- **귀속 4사분면(paired 전 대략 분해)**: 구식등가(binC+flat) .2136 → +graded-wp만 .2193(+0.006) → +weighted-C만 .2473(+0.034) → 둘 다 .2585(+0.045). **간선 가중 ≈ 이득의 75%, w_p ≈ 25%** — R3 발견과 정합, 두-knob 완전 해소.
- **plateau 2연속 확정**(R3·R4 유의 개선 0) → 규칙대로 **Stage A 닫고 Stage B 전환**.
- **Stage A 최종 요약(5라운드·46평가)**: 승자 쌍 = **cap_a03_blend04**(NDCG 주축) + **cap_a0_blend04**(SNIPS 발굴형, NDCG 동률) — per-game pctl × 완료율 blend(lam .4) × per-user 질량캡. 살아남은 원리: per-game 정규화(통일 원리)·완료율(유일 유효 업적신호)·계정 질량캡(최대 레버)·그래프 간선 가중(귀속처). 죽은 축(전부 기록): magnitude(3연속)·pt등급화 단독·AFK게이트 중복·resid 과제거·D시간축·소셜(측정불가)·pvalue(CF에선; walk 전용 프로필로 Stage B 재조명).
- **Stage B 설계**: 랭커 8종 × top 선호 2종 고정. 구현 필요: plain-cosine/Jaccard/PPMI(condcos 변형), P3α(rp3b β=0), **EASE(Woodbury: 필요 컬럼만 P[:,cols]=(1/λ)(I−Xᵀ M⁻¹ X), M=λI+XXᵀ 1.1k dense)**, user-KNN. 패자부활전 후보 선별 기준: 내재-외재 불일치(pvalue 계열 최우선).

## [2026-07-03 07:28] T10 — Stage B 일제전: **판 뒤집힘 — user-KNN이 프로덕션 공식을 이김**
- **리더보드(cap_a03_blend04 기준)**: **userknn25 .2827 ≈ userknn100 .2823** > rp3b .2748 > **condcos(프로덕션) .2585** > condasym .2300 > p3a .2240 > EASE(λ50/200/800) .2124~.2224 > jaccard .2060 > ppmi .0372(고장 수준).
- **paired**: **userknn vs condcos +0.0242 유의** — 프로덕션 item-item 공식이 user-based CF에 유의하게 패배. userknn ≈ rp3b(+0.0078 ns). **SNIPS는 rp3b가 userknn에 +0.0108 유의** → **비지배 랭커 쌍 {userknn(NDCG), rp3b(SNIPS·발굴)}**, condcos는 양축 모두 밀림.
- **해석**: 1.1k 유저·조밀 라이브러리(수백/유저) 체제에선 유저-유사도가 아이템 co-occurrence보다 신호 활용이 좋음(아이템 쌍은 support floor로 잘리는 반면 유저 코사인은 전체 라이브러리를 씀). EASE 약세는 유저 수 부족(릿지 과정규화; λ↓가 최선인 게 그 증거) — **유저 10k 도달 후 재평가 필수 항목**으로 기록. PPMI는 이 밀도에서 표류(positive-clip이 저support만 남김).
- **함의(사용자 결정 항목으로 승격)**: "CF 수식 불변" 전제가 랭커 차원에서 흔들림 — P5 재배선 시 **랭커 교체(userknn or rp3b) vs condcos 유지**는 서빙 구조 영향이 있어 **사용자 확정 필요**. 단 유저 규모가 커지면(10k) 순위가 다시 바뀔 수 있음(EASE 포함) — OOD·규모 재평가와 묶어 결정 권고.
- **Stage C+부활전 발사**: {pvalue_eb(내재-외재 불일치 시그니처), pctl_game, anchor_binary} × {userknn25, rp3b, condcos} — pvalue가 walk/knn 계열에서 cap-blend를 위협하는지, cap 이득이 userknn에서도 유지되는지(선호×랭커 상호작용 소교차).

## [2026-07-03 07:35] T11 — Stage C+부활전+private: **shortlist 확정, Stage B/C 종료**
- **Stage C 반전 2건**: ① **pctl×userknn .2888 — cap 없는 순수 백분위가 최강**: cap 이득은 condcos 전용(유저 코사인의 norm 정규화가 whale-캡을 내장 → 중복). 선호×랭커 상호작용의 정체 규명. ② **부활전 성공**: pvalue×rp3b .2848·×userknn .2840 — "내재-외재 불일치=랭커 미스매치" 가설 실증(사용자 false-negative 지적의 승리). dev 상위 4구성 paired 전부 ns → dev 해상도 소진 → private 발동.
- **Private 패널(150명, [F1])**: 순위 재현 — 과적합 없음. **1위 pvalue×userknn .2943**, 2위 pctl×userknn .2925(동률), 발굴 대표 cap_a03_blend04×rp3b(SNIPS .0994·recall .1756), 프로덕션-호환 최선 cap_a03_blend04×condcos .2667. null 바닥 ✓.
- **Shortlist S1~S4 확정 → LEADERBOARD.md 신설**(종합 리더보드+발견 연쇄 7개+사용자 결정 항목+잔여 위험). Task 7 완료.
- **사용자 결정 항목으로 승격**: 랭커 교체(userknn/rp3b vs condcos 유지) — P5 서빙 구조 영향, 10k 재평가와 묶어 판단 권고. 업적 allowlist: **완료율만 유효, 희귀도 크롤 없이도 P4 성립** — 유저크롤 업적 스코프 재논의 여지(비용 96% 절감 가능성).
- 다음: 보고서 모드 전환 + 잔여 시간 = 학습형(#20) 시도·크롤 CAUGHT UP 감시·풀 성장 시 재확인.

## [2026-07-03 08:05] T12 — 학습형 #20 음성 + 보고서 초안 + 저속 모드 정착
- **학습형 blend 음성(사전 선언 이행)**: identity-trap 회피 설계(rel 회귀 금지, 다운스트림 NDCG 블랙박스 탐색·train-내부 12-simplex 튜닝·dev 1회)에서 최적 가중 (0.5,0,0.5)가 internal .2629 → dev에선 pctl 단독 대비 **+0.0013 ns**. P7 조항("지면 음성결과") 이행 — **단순 형태(pctl/pvalue)가 최종, 학습형 불채택**(10k·OOD 재시도 여지만 기록).
- REPORT_MONDAY.md 초안 v1 작성(TL;DR·결정 4항목·크롤·이슈로그·잔여위험). 남은 주말 = 저속 모니터링: CAUGHT UP→users 전환, 풀 성장 시 top-4 재확인, 보고서 갱신.

## [2026-07-03 12:15] T13 — 25k 풀 재확인: shortlist 강건성 통과
- typed 25,394 트리거 → 재추출(풀 19,734→**25,148**, +27%) → top-3 선호 × 3 랭커 재확인(dev): **순위 완전 유지** — pvalue×knn .2898 > pctl×knn .2862 > cap_blend×knn .2825 > … condcos 하위 > null .11~.16 바닥. recall 절대값은 풀 확대로 하락(과제 난이도 상승, 예상대로) — 순위·간격 구조 불변 = **shortlist가 풀 성장에 강건**.
- 저속 모니터링 계속(백로그 14,140 — CAUGHT UP 내일 새벽 예상).

## [2026-07-03 12:28] T14 — 크롤러 사망(원인 미상) → 사용자 신고로 조기 복구
- 사용자 "루프 죽었어" 신고 → 진단: **루프(세션·크론·wakeup)는 생존**(12:13 tick·12:23 하트비트 정상), **죽은 건 크롤러**(마지막 로그 12:06, 프로세스 0 — 12:06~12:13 사이 사망, 원인 미상: 크래시 추정, WAL 클린 종료 흔적). 워치독이 12:46 틱에 잡았겠지만 신고 덕에 ~19분 빠른 복구.
- 재시작 완료(shim 32604→worker 29308), 진행 재개 확인(unvisited 13,959→13,955 감소·budget 증가). 손실 0(재개형).
- 유의: 사망 시각이 pool_recheck_25k 백그라운드 실행(12:13~14)과 근접 — 재추출/재확인은 read-only 연결이라 인과 가능성 낮으나 기록해둠. 재발 시 상관 조사.

## [2026-07-03 12:58] T15 — 사용자 교정 2건: "결론 내지 마, 계속 실험해" → 능동 탐색 재개
- **교정 ①**(사용자): "모든 실험 끝" = 과장 — MF 가족(ALS/BPR/Poisson)·SLIM 미실행이었음을 인정. "DL 오래 걸림" 전제도 이 규모(1.7k)에선 성립 안 함(분 단위) — 시간이 아니라 내 스테이징 판단이 실험을 막고 있었음. → MFRanker 구현(ALS=기존 Hu2008 재사용, BPR=벡터화 SGD, Poisson=NMF-KL), mf_family 런 발사.
- **교정 ②**(사용자): "실험 열려 있는데 마음대로 결론·종료 금지. 크롤은 안 봐도 잘 돈다. 할 수 있는 걸 계속 해라." → **모드 전환: 감시 → 능동 탐색**. shortlist는 '동결'이 아니라 '현재 리더'로 격하. 열린 전선 큐: MF(실행 중) → 평가축 미구현분(wishlist 2차 fitness·masked-engagement — 플랜에 있는데 하니스 미배선!) → R5 승자조합(pvalue×cap·pvalue-blend·userknn×cap·k강건성) → judge 가드레일(Sonnet blinded, 첫 실행) → 의도 tier ablation(팩블록 병합 전처리)·informed-negative BPR. 크롤 확인은 하트비트 틱만.

## [2026-07-03 13:20] T16 — MF 가족 측정 완료 (추론→측정 대체)
- **결과(dev, 25k 풀)**: **ALS64 0.2656~0.2678**(MF 최강, seed 인자 버그 1회 수정) > NMF-KL(Poisson) 0.219 ≈ EASE 0.21~0.22 > **BPR64 0.183~0.186**(최하). 전부 **userknn(0.2825~0.2898)에 열세**.
- **판정**: "무거운 학습형이 이 규모에서 이기나" — 이제 추론이 아니라 측정으로 **아니오**. 최종 랭커 서열: userknn > rp3b ≈ ALS ≈ condcos > NMF/EASE > BPR > jaccard > ppmi. MF는 10k 유저 재평가 목록에 ALS만 잔류(나머지 기대값 낮음).
- wishlist 2차 축(wishlist_axis.py 신규) 실행 중 — 리더 4구성+null의 "표명된 욕망 발굴력" 첫 측정.

## [2026-07-03 13:25] T17 — wishlist 축 첫 측정 + R5 조합 전멸
- **wishlist 축(168 dev 유저, 최근 미보유 위시 타깃)**: 리더 4구성 0.027~0.029 vs null(인기구조 보존) 0.021 — **행동 모델이 인기 대비 +35%**, 단 리더 간 변별 없음(CI 중첩) = 이 표본에선 저해상도 보조축. 정직 기록: 발굴 과제의 난이도 실증(주축 대비 10배 낮은 recall). K=50·표본 확대는 후속 옵션.
- **R5 승자 조합 전멸**: pvalue+완료율 blend .2901 ≈ 순수 pvalue .2898(무이득) · cap×pvalue .2817(cap은 userknn 위에서 재차 무익/해로움) → **S1(순수 pvalue×userknn)이 모든 강화 시도를 버팀**. 선호-조합 전선 소진 판정(단발 아님 — R4 이후 조합 5종 연속 ns). 남은 전선: masked-engagement 배선 · judge 가드레일(Sonnet 첫 실행) · k-강건성 · 의도 tier ablation · informed-negative BPR(기대값 낮음, 싼 시험).

## [2026-07-03 13:40] T18 — k-강건성 통과 + **judge 가드레일 첫 실행: 지표-judge 분기 발견**
- **k-강건성**: k=10/50에서도 userknn>rp3b·pvalue≈pctl 순위 유지 ✓.
- **judge(Sonnet blinded, 12케이스, grounded 카드, S1 vs S4)**: **적합도 S4 7 : S1 4 (tie 1), 발굴 S4 6 : S1 5** — **NDCG 우승자(S1)가 judge에서 패배**. 사유 패턴: userknn 리스트는 메인스트림 AAA 쏠림(유사유저 라이브러리 합산=인기 지배), condcos 리스트는 취향-특정 인디 픽(간선별 인기 debias). **해석: NDCG(보유 재현)는 인기 쏠림을 보상, judge(질적 적합)는 특정성을 보상 — 두 목적의 실재하는 긴장**. 가드레일 설계 목적("recall이 못 보는 것") 그대로 작동한 첫 사례.
- **함의(월요일 결정 ①에 직결)**: 랭커 교체 질문이 단면적이지 않음 — userknn은 지표 우위·condcos는 지각 적합 우위. 절충 후보: userknn+인기패널티(rp3β식 discount를 knn 집계에), 또는 Pareto 유지(용도별: 재현=knn/발굴·질감=condcos·rp3b). **후속 judge 확대(S1 vs S3, n↑)와 userknn-pop-discount 변형을 다음 라운드로.** 한계 명시: n=12·단일 judge(Sonnet)·카드 기반 — 방향 신호이지 확정 아님(Gemini 교차는 사용자 복귀 후).

## [2026-07-03 13:40] T19 — **knnpd03: 지표-judge 분기 해소, 전축 지배 후보 등극**
- 가설(T18 절충안): userknn 집계에 pop^β discount → **β 스윕: 0.3만 성립**(NDCG 0.2898 동률 유지 + SNIPS 0.0801→0.0888), β≥0.6 붕괴(과감쇠 — 예산: knn 합산의 인기 질량이 rp3β보다 커서 같은 β라도 더 세게 작동하는 듯).
- 조합 확장(4선호×5랭커): pvalue×knnpd03 공동 1위 · dblq×knnpd03 0.2864(SNIPS 0.0882)도 강세 · **앙상블(RRF condcos+knn) 기대 이하**(열세 쪽 희석 — 폐기) · rp3β는 0.6이 스윗스팟 재확인(0.3/0.9 열세).
- **judge 재실행(S1'=pvalue×knnpd03 vs S4, 동일 프로토콜 n=12)**: **적합도 9:0(무3), 발굴 11:1** — 라운드1의 4:7 패배가 β=0.3 하나로 완전 역전. 사유 패턴: knnpd03 리스트가 "취향 클러스터 직격 + 덜 뻔한 픽"으로 일관 평가.
- **리더 갱신(동결 아님)**: **S0 = pvalue_lognorm_eb × userknn25+popdiscount(β0.3)** — NDCG 공동1위·SNIPS 우위·judge 압승 = 현존 유일의 전축 비지배→지배 후보. 한계 동일(n=12·단일 judge) — Gemini 교차·OOD는 복귀 후.
- 다음: #9 masked-engagement 배선 → #11 의도 ablation → #12 → (CAUGHT UP 시) rarity E가족.

## [2026-07-03 13:42] T20 — masked-engagement 축 배선·측정 (#9 완료): S0 4축 석권
- 설계 준수: 타깃 = 중립 rel(후보 자기-s 금지 — 예측가능성 함정), holdout≥5 유저 199명, per-user Spearman.
- **결과: S0(pvalue×knnpd03) rho 0.1045 [0.068,0.139] > S1 0.0771 > S4 0.0686 > null −0.006**(축 건강 ✓). S0가 NDCG·SNIPS·judge·masked-engagement **측정한 전 축 선두** — 현 리더 지위 강화. 정직 기록: rho 절대값 자체는 낮음(강도 예측은 본질적으로 어려움; 보조축 역할에 충실).
- 다음: #11 의도 tier ablation(condcos≈1.0 동일오너셋 팩블록 병합 → ε-tier), #12 informed-negative BPR, CAUGHT UP 대기(rarity E).

## [2026-07-03 13:46] T21 — #11 의도 tier ablation: **기각(기본 제외 실측 확정)**
- 전처리 실효: 0분 321,725행 중 **121,793(38%)이 팩 형제로 차단**(소유 봉쇄율≥0.98 — 07-02 프로브 "팩 구조물 지배"와 정합), 199,932행에 ε 부여.
- **결과: ε=0.05 → 0.2895(무이득 vs base 0.2898) · ε=0.15 → 0.2859(하락)** — knnpd03/userknn 양쪽 동일 패턴, 용량↑=악화의 일관 용량-반응 = 노이즈 판정. **사전 기준("주축 유의 상승 시만 채택, 입증책임=포함측") → 기각, 기본 제외 유지.** 팩 병합을 해줘도 잔여 0분-의도에 주축 신호 없음 — "돈 낸 의도"는 취향 방향 정보가 없거나 세일/번들 노이즈에 매몰.
- wishlist ε-tier도 같은 논리 계열이나 미실험 — 0분(더 강한 의도)이 죽었으므로 기대값 더 낮음, 우선순위 강등(감사 가능하도록 명시).

## [2026-07-03 13:50] T22 — #12 informed-negative BPR: **유의 음성(−0.0514 SIG) — dropped는 BPR 네거티브로 쓰면 해롭다**
- paired(동일 시드·에폭): random-neg 0.1862 vs dropped-혼합-neg 0.1348, **diff −0.0514 [−0.0662,−0.0365]** — CI 전부 음수.
- **기제 해석**: dropped(pt≥10분·게임내 하위 25%·무완주·stale, 20,660쌍/1,071유저)는 '싫음'이 아니라 **'취향이지만 안 맞았음'** — 유저가 애초에 산 게임이라 랜덤(완전 무관)보다 취향에 가까움. 이를 랜덤 아래로 밀면 취향 방향 자체가 왜곡. 플랜의 "informed negative" 가설이 이 형태로는 반증됨.
- 정직 한정: "dropped에 신호가 없다"가 아니라 "**uniform-random보다 강한 네거티브로 쓰는 건 틀렸다**"까지만 입증. 대안 형태(자기 liked 대비 마진 네거티브, s 소폭 감쇠)는 열려 있으나 기대값 낮음 — 우선순위 강등.
- 이로써 **크롤-독립 열린 전선 소진**: 남은 것 = CAUGHT UP 후속(rarity E·per-game 업적통계 ②③·최종 재확인) + 문서 현행화. 능동 탐색은 크롤 완주 시 자동 재개.

## [2026-07-03 13:55] T23 — S0 private 1회 확인: "지배" → "무손실+유의이득"으로 정직 격하
- private(150명, **2번째 노출** — 리더 갱신 확인 목적 1회 한정, 이후 재사용 금지): S0 0.2789 vs S1 0.2879.
- paired CI: **NDCG 차 −0.0090 [−0.0195, +0.0018] = ns** / **SNIPS 차 +0.0158 [+0.0093, +0.0236] = SIG**.
- 판정: dev의 "NDCG 동률"은 private에서 소폭 후퇴(ns) — S0의 정확한 지위 = **"어느 축도 유의 손실 없음 + SNIPS(디바이어스)·judge(질감)·masked(강도) 유의/일관 우위"**. 전축-지배 표현은 리더보드에서 교정. 최종 관문 = OOD(P6).
- 크롤-독립 전선 소진 재확인 — 이후 루프: CAUGHT UP 감시(→ users 전환·최종 재추출·rarity E) + REPORT_MONDAY 갱신.

## [2026-07-04 02:40] T24 — **games 크롤 완주 → CAUGHT UP 핸들러 완결** (백로그 28.8k→0)
- 02:12 백로그 0 감지 → games-only 종료 → **daily_crawl.bat(users+games) 전환**(유저 크롤 재개) → 재추출: **최종 풀 38,435**(+53%, typed 39,142; 미타입 1,491=상장폐지류 제외) + rarity 집계(211k 쌍) + 게임 업적 프로파일 ②난이도(ach_pct_median/iqr/deep_frac) ③정보량(n_ach_defined) 컬럼 추가.
- **pool_recheck_final(38.4k)**: 순위 유지 + **S0(pvalue×knnpd03)가 NDCG 0.2808 단독 1위**(userknn 0.2745 추월) + SNIPS 0.0748 최고 — 카탈로그 커질수록(롱테일↑) 인기 패널티가 더 유효. 절대값 하락은 풀 확대 효과(정상).
- **E가족(rarity) 판정: 음성** — rarity_mastery 0.2670·rarity_depth 0.2663 < pctl 단독 0.2724 ≪ pvalue 0.2808 (rp3b 동일 패턴, blend 동형 직접 비교). 희귀도의 '코호트-독립' 이론 매력이 실측 신호로 이어지지 않음. **함의: 유저-크롤 업적 allowlist 축소(96% 절감) 논거 완성** — P4 신호는 완료율(이미 dense)로 충분, 희귀도는 P7 학습형 재료 여지만 남음.
- 이로써 #12 완료 — 플랜의 크롤-의존 항목 전부 소화. 남은 루프: users 크롤 진행 감시(10k 적립) + 보고서 최종화.

## [2026-07-04 10:18] T25 — 예산 리셋 확인, 유저 크롤 재개
- 07-03 예산 90k 전량 games 완주에 소진 → 크롤러가 매시 53분 체크로 대기(정상) → **09:53 KST(=00:53 UTC) 리셋 재개 확인**(budget 일자=UTC 실증). 유저 적립(1,669→10k) 백그라운드 진행 재개.

## [2026-07-04 11:55] T26 — 유저 크롤 재개 후 관찰: 발견(discovery) 구간
- budget 소비 활발(~5k콜/h)인데 public_done +1뿐 → users 상태 분해: 전체 3,997 = 공개완료 1,669 + 비공개 2,327 + 진행중 1. **판독: pending 234k 대기열의 요약·공개여부 선별(스노볼 발견) 구간** — 심층 수집(170콜/명)은 선별 이후 가속 예상. 에러 아님(1시간 내 유저 갱신 1건 확인). crawl_daily.log 08:53 이후 침묵은 stdout 버퍼링 추정(budget 증가가 실동작 증거). 수 시간 후에도 적립 ~0이면 10k ETA 우려를 보고서에 명시 예정.

## [2026-07-04 13:25] T27 — 유저 적립 전환 확인 (+9)
- public_done 1,669→1,678: discovery→심층 수집 전환. 초기 속도 ~18명/h(30분 관측) — 단순 외삽 시 10k까지 ~19일이나, 초기 관측이라 유동적(선별 큐 소진 후 가속 가능). 하루 단위로 재측정해 보고서에 ETA 반영 예정.

## [2026-07-05 18:15] T28 — 세션 일시정지(~6.5h) 자동 복구, 크롤 무중단
- 12:05~18:15 wakeup·크론 미발화(rate-limit 일시정지 추정 — 플랜 장애매트릭스의 예상 시나리오). 해제 후 큐 프롬프트 자동 발화로 재개(설계 작동 ✓). **크롤러는 독립 프로세스라 무중단**: 적립 2,156→2,336(+180, ~27명/h), 예산 42k/90k 정상 소비. 손실 0.

## [2026-07-05 18:45] T29 — Fresh-panel 준-OOD 검증(n=586) + β 강건성: 리더 구조 재현
- 사용자 "계속하라" 지시 → 신규 스노볼 유저(+667, 어떤 라운드에도 무노출)로 fresh-panel 검증 실행. **결과: 순위 구조 완전 재현** — S1 .2720 ≈ S2 .2703 ≈ S0 .2670(CI 중첩 동률권) > S4 .2549 ≈ S3 .2508 ≫ null .1083. **S0 SNIPS 우위 유지(.0814 vs S1 .0699)**. 패널 과적합 없음의 가장 강한 증거(n=586, P6 조기신호 긍정). 한정: fresh도 스노볼-연결이라 완전 OOD 아님.
- **β 강건성(fresh)**: β=0.2 → **NDCG .2777(전체 최고!)** + SNIPS .0783 / β=0.3 .2670/.0814 / **β=0.4 .2253 절벽**. 판정: β∈[0.2,0.3] 안정 고원 + 0.4부터 붕괴 — 취약-knob 우려 부분 해소. β=0.2 최적은 fresh 1회 관측이므로 일방 교체 금지 → **P6 사전등록 그리드 {0.2, 0.3}** 항목으로 이관.

## [2026-07-06 03:05] T30 — judge 3라운드(S0 vs S1, fresh n=16): **S0 압승 — 인기패널티 질감 효과 직접 입증**
- 무노출 fresh 유저 16케이스, blinded: **적합도 S0 13 : S1 2 (무 1), 발굴 S0 14 : S1 2.** 사유 패턴: S1은 오프-테마 메인스트림(BG3·Witcher3·GTA V·Elden Ring)로 새고, S0는 취향 클러스터 밀착(예: 소울라이크 유저에 Lies of P·REMNANT II, 물리 샌드박스 유저에 Clone Drone).
- **S0 증거 서류 완성**: NDCG 동률~우위(38.4k 풀 단독 1위) + SNIPS 유의 우위 + judge 2연승(vs S4 9:0, vs S1 13:2) + masked 1위 + fresh 재현 + β 고원. in-cohort에서 모을 수 있는 증거는 사실상 전부 수집 — 남은 관문은 P6 OOD(사전등록 완료)와 Gemini 교차(복귀 후).
- 한계 일관 유지: 단일 judge(Sonnet)·카드 기반. P6_PREREG에 Gemini 교차 프로토콜 명시됨.

## [2026-07-06 03:20] T31 — 크롤러 2번째 사망 → 워치독 재시작
- 03:18 틱에서 프로세스 0 감지(적립 2,585 정지, budget 진행률로 ~02:0x 사망 추정 — 원인 미상, 1번째와 마찬가지로 크래시 추정). daily_crawl.bat 재시작 완료(2프로세스), 재개형이라 손실 0. 사망 이력: 07-03 12:06, 07-06 ~02:0x — 빈도 낮음(2회/3일), 워치독 커버 범위 내.

## [2026-07-06 10:55] T32 — 적대적 감사(ultracode 5렌즈 워크플로, 44에이전트) → **S0 결론 하향 교정**
사용자 ultracode 지시로 S0="pvalue×knnpd03가 최선" 결론을 반증 시도. 39개 우려 검증(CONFIRMED 14·PLAUSIBLE 15·REFUTED 10). 5개 렌즈가 **독립적으로 같은 결함에 수렴** — 자기비판 정본화:

**핵심 결함 (CONFIRMED, 수렴):**
1. **S0의 "3축 우위"는 사실상 1축, 그 축은 순환.** 주 지표(popularity-neutral graded NDCG)에서 knnpd03의 인기패널티는 **무이득~미세손실**(recall@20은 유의 악화 Δ−0.011 [−0.017,−0.005]). S0의 "우위"는 전부 **SNIPS + judge-discovery**에서 오는데, 이 둘은 **같은 인기축을 두 번 센 것**(SNIPS=IPS 인기가중, judge=명시적으로 "덜 뻔한 픽 우대" 지시 → knnpd03이 기계적으로 인기 게임 감쇠 = 기준-기계 동어반복).
2. **judge fit/discovery 컬럼 붕괴**: 비-tie 34/35 케이스 동일 = 독립 2축 아님. S0 리스트 16/16이 S1보다 덜 인기 → "적합 승자=항상 덜 인기 리스트" = 순환.
3. **정답지 순환**: rel = per-game playtime 백분위. pvalue_lognorm_eb·pctl_game은 within-game playtime의 단조변환 → per-game Spearman(s, rel)≈1 by construction. **모든 검증축(masked·judge taste·fresh NDCG·심지어 P6 사전등록)이 동일 build_relevance 타깃 재사용** → 순환을 반박 못함. target-독립 신호(wishlist/구매 홀드아웃, 또는 즐김-기반 judge)만이 판정 가능.
4. **"38.4k 단독 1위 0.2808"은 노이즈 내**(+0.0063 ns, CI 0 포함) + 튜닝(dev) 패널. 홀드아웃(private·fresh)에선 **S0 vs S1 오히려 음의 방향**(S0 뒤, ns). 크로스풀 "강건성"은 unpaired(split+pool+target+후보셋 동시 변동, 196/200 유저 NDCG 상이).
5. **β 고원 [0.2,0.3] post-hoc·재현불가**(fresh 패널 멤버십 미영속, β=0.2가 실제 최고였음).
6. **다중비교 미보정**(~197 페어 셀) → 일부 "SIG"(blend-vs-binary·rp3b-vs-userknn SNIPS)이 FDR 통과 불확실.
7. **private 패널 2회 노출**로 S0 승격 → 해당 페어 통계 오염(descriptive-only).

**살아남는 정직한 코어 (REFUTED된 반론 + 감사 인정):**
- **preference main-effect 방어됨**: pvalue > pctl (+0.0033 SIG)·> dblq (+0.0041 SIG) 5랭커 풀링 → pvalue는 좋은 선호(단일 knnpd03 셀 아닌 풀링 근거로).
- **coarse 구조 재현**: userknn/knnpd/rp3b ≫ condcos ≫ null이 fresh 무노출·리샘플에서 재현 = 넓은 레짐 일반화는 진짜.
- 음성결과 대부분 유지(rarity paired-boot pvalue>rarity p≤0.001 등).

**교정된 결론**: S0의 pop-discount는 **측정된 품질 향상이 아니라 인기/신선도 knob(제품 선택)**. "S0가 S1보다 낫다"는 **target-독립 근거로는 미입증**. → 다음: (a) 결정적 read-only 재검(순환 정량화·wishlist target-독립 재평가·BH-FDR·split-seed 안정성) (b) LEADERBOARD/REPORT 하향 교정 (c) P6_PREREG에 target-독립 주지표(wishlist 홀드아웃) 추가.

## [2026-07-06 11:05] T33 — 결정적 재검(순환·target-독립·BH-FDR) → **정본 결론 재작성**
감사 CONFIRMED 항목을 read-only로 실측(audit_verify.py·audit_fdr.py, dev 패널만·private/Gemini 미사용):

**(A) 순환 정량화**: per-game Spearman(선호 s, rel 타깃) 중앙값 — pvalue **0.957**, pctl_game **0.957**, per_user_cap 0.660(9,959 게임). → pvalue/pctl은 자기 정답지의 단조 복사본. 주 지표(graded NDCG)는 "playtime 백분위를 얼마나 잘 복원하나"를 재는 셈 = 순환 확정.

**(B) target-독립 검증(wishlist 홀드아웃, playtime 무관)**: S0 wl-recall 0.0201 > S1 0.0145 > S2 0.0134, **S0−S1 = +0.0056 [−0.0002,+0.0124] ns**. → 순환 없는 유일 신호에서 S0가 점추정은 앞서나 **유의하지 않음**(경계). 인기패널티가 "원하지만 미보유(=덜 인기)" 발굴에 약하게 정렬된다는 힌트이나 미입증.

**(C) 주 지표 정직성(S0 vs S1, dev 페어드)**: NDCG **+0.0016 ns** · recall@20 **−0.0112 SIG** · SNIPS **+0.0081 SIG**. → knnpd03은 주 지표에서 무이득, **plain recall 유의 손실**, pop-debias 지표만 유의 이득(설계상 당연). = 품질 향상이 아니라 recall↔발굴 트레이드 knob.

**BH-FDR(m=13 헤드라인 페어)**: **살아남음** — userknn≫condcos(+0.0242, q=0.004)·≫ppmi/ease/jaccard·S0-S1 SNIPS(+0.0087,q=0.0007)·recall(−0.011,q=0.002)·pvalue>pctl@knnpd03(+0.0095,q=0.003). **탈락(ns)** — **S0-S1 NDCG(+0.0001, q=0.75)**·pvalue>pctl@userknn(ns)·userknn>rp3b(ns)·R5(ns).

**정본 결론(교정):**
1. **가장 강건한 실측 = 랭커 레짐**(모든 FDR 통과): **user-KNN 계열이 프로덕션 condcos를 +0.0242(q=0.004) 유의 격파** + 전 고전랭커(ppmi/jaccard/ease) 압도. **랭커가 선호보다 크고 진짜인 레버** — P5 실행 권고의 핵심.
2. **선호**: pvalue는 무난하나 pctl 대비 우위가 **랭커 교차 강건 아님**(knnpd03서만 SIG, userknn서 ns). 주 지표상 최단순 pctl_game과 userknn 위에서 구별 불가.
3. **knnpd03(=S0의 pop-discount)**: **측정된 품질 향상 아님**. NDCG ns·recall SIG-손실·SNIPS/judge는 순환적 by-construction 이득. wishlist(독립)선 ns. = 제품/가치 knob(발굴 강조), 확정 승자 아님.
4. **shortlist 재정의**: S0을 "확정 승자"에서 강등 → **P6 주후보 = S1/S2(pvalue-or-pctl × userknn), knnpd03은 ablation(발굴 knob)**. 최종 판정은 target-독립 주지표에서만.

## [2026-07-06 11:25] T34 — 웨이브2 재추출(2,655유저·풀 39,743) 결정적 재검: **wishlist 독립축 SIG 전환**
동일 read-only 재검을 더 큰 풀에서 반복:
- **(A) 순환 재현**: per-game rho pvalue/pctl 0.958(변함없음) — 순환은 표본과 무관한 구조적 사실.
- **(C) 주지표 정직성 재현**: S0 vs S1 — NDCG +0.0042 **ns** · recall −0.0095 **SIG 손실** · SNIPS +0.0096 SIG. knnpd03은 playtime-재현 축에선 여전히 무이득~손실.
- **(B) target-독립(wishlist) — ns → SIG 전환**: S0 0.0211 > S1 0.0139 > S2 0.0133, **S0−S1 = +0.0073 [+0.0011,+0.0142] SIG**(n=179, 이전 +0.0056 ns@178에서 표본·풀 확대로 유의화).
**정직한 재교정**: knnpd03의 인기패널티는 **playtime 재현(NDCG ns/recall 손실)이 아니라 "다음에 뭘 wishlist할지"(=미보유·덜인기 발굴)를 유의하게 더 잘 맞힌다** — 이 축은 playtime provenance가 없어 **비순환**. 따라서 knnpd03은 phantom이 아니라 **정당한 발굴-지향 knob**: playtime-recall ↔ 발굴 hit의 실재하는 트레이드. 다만 여전히 (i) 주지표(NDCG)선 무이득 (ii) in-cohort 단계 — OOD 재확인 필요. **랭커 교체(userknn≫condcos)가 강건 헤드라인이라는 결론은 불변**; knnpd03 상태만 "ns knob"→"비순환 근거 확보한 발굴 knob(OOD 대기)"로 상향.

## [2026-07-06 12:10] T35 — 🔴 감사 후속 대발견: cutoff 버그가 "무거운 모델 전패" 결론을 뒤집음
감사 CONFIRMED 'ease-cutoff-bug'를 실측: gauntlet recommend의 `if score<=0: break`는 유사도합 랭커(userknn/condcos, s≥0)엔 무해하나 **EASE의 선형 점수는 음수로 감 → 리스트 조기 절단**으로 EASE를 불리하게 했음.
- **공정 재평가(절단 제거·λ그리드 10~1000, dev)**: ease_l100 **NDCG 0.3381** vs userknn 0.2782 = **+0.0600 [+0.0474,+0.0727] SIG**, recall도 0.1431 vs 0.1248 우위. λ커브 단봉(10<30<100>300>1000)=정상 작동 서명. 구 gauntlet의 평탄 ~0.21은 절단이 지배한 인공물.
- **함의(중대)**: Stage B "userknn≫전랭커·EASE/MF 열세" 결론은 **버그 아티팩트**. 방금 커밋한 "랭커 강건 헤드라인=userknn≫condcos, userknn 교체 권고"도 **부정확** — 공정 재평가상 **EASE가 userknn·condcos 모두 상회**. MF(ALS/BPR/NMF)도 fold-in 점수가 음수라 같은 절단 피해 가능성 → 재검 필요.
- **조치**: 랭커 결론 "수정 중" 표기, 학습형 리랭커·MF 공정재검 실행 후 종합 재작성. 순환 주의는 여전 유효(EASE NDCG도 같은 타깃) — 최종은 target-독립·OOD.
- **메타 교훈**: 적대적 감사가 헤드라인을 뒤집는 실측 버그를 잡음 = 감사의 가치 실증. **가장 강건해 보였던 결론(FDR 통과 userknn>condcos)조차 공유 코드 경로 버그엔 취약**했다.

## [2026-07-06 12:15] T36 — 공정 랭커 최종 비교(dev, NDCG + target-독립 wishlist): **EASE가 정정된 랭커 승자**
| 랭커(공정) | dev NDCG | wishlist(독립) |
|---|---|---|
| **ease_l100(절단제거)** | **0.3189** | 0.0187 |
| knnpd03 | 0.2638 | **0.0191** |
| userknn25 | 0.2582 | 0.0128 |
| condcos(프로덕션) | 0.2175 | 0.0084 |
- **EASE − userknn: NDCG +0.0606 [+0.0486,+0.0729] SIG · wishlist +0.0059 [−0.0002,+0.0128] ns(경계)**.
- **정정 결론**: ① **서빙 랭커 = EASE(닫힌형 선형 item모델, λ≈100)** — NDCG 압도(+0.061 SIG) + 독립축 최상위권(0.0187, knnpd03과 ~동률), 1.1k유저 fit 0.9s(저비용). 구 "userknn 최고/EASE 열세"는 cutoff 버그 인공물. ② **독립축(wishlist)에선 발굴지향(knnpd03 0.0191 ≈ EASE 0.0187) > userknn 0.0128 > condcos 0.0084** — pop-discount·선형모델이 "다음 발굴" 예측서 우위. ③ **condcos(프로덕션) 양축 최하 → 교체 결론은 오히려 강화**(단 교체 대상은 userknn이 아니라 **EASE**).
- 순환 주의 유지(EASE NDCG도 동일 타깃) — 단 EASE는 독립축서도 최상위권이라 순환-only 아님. 최종은 OOD(P6). 학습형 리랭커 결과 대기 중(EASE 넘는지).

## [2026-07-06 12:18] T37 — 학습형 리랭커: 음성(감사 미탐색 항목 종결)
monotone HGB(피처 [userknn_score, condcos_score, pop_pct, lib_size], train유저 112,567행 학습, dev 1회):
- **결과: dev NDCG 0.1854 < userknn 0.2582 · knnpd03 0.2638** (리랭크 기반보다도 낮음) / wishlist 독립 0.0188 ≈ knnpd03 0.0191(최상위권).
- **해석**: 학습모델이 자유도상 pop_pct를 강하게 감쇠 학습 → 순환 NDCG 손해·독립축만 최상위(knnpd03과 동일 트레이드). 후보셋=userknn top-120 상한도 제약. **학습형 fusion이 EASE/knnpd03 대비 부가가치 없음** — 감사 지적 미탐색 항목(학습형 리랭커)을 음성으로 종결.
- 한정: 4피처·monotone·회귀손실의 소박한 구현 — 정식 LambdaMART(랭킹손실·다피처)는 이론상 열림이나, **EASE가 이미 NDCG 압도**하고 리랭커가 독립축서도 knnpd03 초과 못하므로 기대값 낮음.
- **감사 후속 종합**: EASE cutoff버그(헤드라인 뒤집음, T35~36) + 학습형 음성(T37) + 순환·knob 교정(T32~34). 미탐색 잔여 = 보정 fusion(크루드 RRF는 이미 기각·리랭커가 사실상 포함) → 실질 소진.

## [2026-07-06 13:22] T38 — EASE 승리 fresh 무노출 패널서 재현(n=854): 랭커 결론 종결
frozen(train/dev/private) 제외 신규 유저 854명(그래프 무노출):
- **ease_l100 0.3359 > userknn 0.2736 > knnpd03 0.2663 > condcos 0.2304**, **EASE−userknn = +0.0623 [+0.0566,+0.0679] SIG**(dev +0.061과 일치, CI 더 타이트).
- **랭커 결론 종결(in-cohort 한도)**: EASE(λ≈100)가 dev·fresh 양쪽서 userknn을 +0.062 SIG로 이김 = cutoff버그 정정이 표본·패널 무관하게 견고. **서빙 랭커=EASE, condcos(프로덕션) 양패널 최하 → 교체**. 최종 관문은 P6 OOD(target-독립 co-주지표 포함).
- 감사 발단(T32)~종결(T38) 요약: **헤드라인 2개 정정**(①S0=승자→발굴knob ②userknn=최고→EASE, 둘 다 실측 버그/순환 기인) + 미탐색 종결(학습형 음성). 자기비판 감사가 in-cohort 결론을 최대한 견고화함.

## [2026-07-07 05:25] T39 — P4 확장: 딥러닝 + 개별 업적 분석 (사용자 요청, 실행)
사용자가 여러 번 요청·내가 미룬 두 스레드 실행. 데이터 점검: torch 2.12.1 · 개별 업적 156만(텍스트+global_pct) · 위시리스트 75.6만행/2,912명(독립 라벨). 판정은 순환 없는 위시리스트.

**Phase A — 개별 업적 vs 집계 완료율 (blend 성분만 교체, EASE, dev, 독립 위시리스트):**
- base 집계완료율 wl 0.0209 · story-완주 0.0233(**+0.0024 [−0.002,+0.008] ns**, 최고 점추정) · skill ±0 · **rarity_depth 0.0198(−0.0011, 약간 음성)** · rare_frac +0.0004 ns.
- **판정: 개별/희귀도 업적이 "몇 개 깼나(집계 완료율)"를 독립 지표에서 유의하게 못 이김.** 희귀도는 NDCG에 이어 위시리스트에서도 죽음(부검 완료). 한계: 업적 156만 중 **93%가 일반진행형(misc)** — 유형 재료 자체가 적음(키워드 분류 거칠기도, 원래 대부분 업적이 진행 마일스톤이기도).

**Phase B1 — 신경 CF (Mult-DAE, torch) vs EASE:**
- Mult-DAE NDCG **0.1692** vs EASE **0.3189** = **−0.1497 [−0.1695,−0.1297] SIG 대패**. wl 0.0104 vs 0.0187도 열세.
- **판정: 이 규모(학습 1,133명·희소)에선 신경망이 선형에 압도적으로 밀림 — "DL 안 됨"이 추론 아닌 실측.** (튜닝해도 이 격차는 안 뒤집힘 — 알려진 small/sparse 영역.)

**Phase B2 — 업적-피처 신경 랭커(유저 업적스타일 + 아이템 업적프로파일 + EASE점수, torch MLP):**
- NDCG 0.3098 vs EASE 0.3189 = **−0.0091 ns**(주 지표선 EASE 못 이김) / wishlist **0.0246** vs 0.0187 = **+0.0059 [−0.0005,+0.0127] ns 경계선**(지금까지 최고 wl값).
- **판정: 개별 업적 콘텐츠가 주 지표는 못 올리나 독립 발굴(위시리스트)엔 약한 양성 힌트 — 미유의(경계).**

**종합 정직 결론:**
1. **딥러닝은 여기서 단순 방법을 못 이긴다** — 신경 CF 대패(−0.15), 업적 신경 랭커도 주 지표 ns-열세. 규모가 선형(EASE) 편.
2. **개별 업적은 집계 완료율을 못 이긴다** — A·B2 모두 발굴축에서 +0.005~0.007의 *경계선 양성*뿐, 유의 없음. knnpd03(wave1 ns→wave2 SIG)처럼 **유저 늘면 유의화 가능성**은 있으나 현재는 미입증.
3. **일관 패턴**: 업적/발굴 신호는 *재현(NDCG)* 이 아니라 *발굴(위시리스트)* 을 돕는 쪽으로만 약하게 정렬 — 전부 ns.

**크롤 방향 함의(사용자 결정):** 개별 희귀도/업적 detail이 값싼 집계 완료율을 못 이김 → **allowlist를 집계 완료율만 남기고 개별 업적 축소가 데이터상 합리적**. 발굴 힌트(경계선)를 좇으려면 개별 업적 depth보다 **유저 수↑(독립 라벨↑)** 가 효율적. 최종은 사용자 판단.

## [2026-07-07 07:40] T40 — 크롤 방식 전환: 무편향 무작위 + 업적 완전 제거 (사용자 결정)
P4-ext 실측(T39: 업적 무이득·DL 열세) 근거로 사용자가 크롤 축소+편향제거 지시.
- **업적 완전 제거**(`--no-achievements`): 게임별 GetPlayerAchievements(유저당 ~170콜=96% 비용) 스킵. 완료율 +0.0073 포기 대신 처리량 대폭↑. **스팀 API엔 유저 완료율 배치 호출이 없어**(GetPlayerSummaries·GetOwnedGames 다 확인) "집계만 싸게"는 불가 → 완전 제거가 합리.
- **무작위 accountID 샘플링**(`--user-source random`): 리뷰어-스노볼(편향) 대신 base+random accountID. **GetPlayerSummaries 100명/콜 배치로 공개프로필 선별** 후 GetOwnedGames. depth=-1로 OOD 태그. 스노볼 enqueue 차단(편향 재유입 방지).
- **실측 적중률(07-07)**: 무작위 81% 실존·79% 공개프로필·그중 11%만 게임목록 공개 → **~9% 크롤가능**. 소규모 실런: **~12콜/획득유저 → ~7,300명/일**(기존 ~500/일의 15배, 무편향).
- 기존 편향 풀(~3,044명)은 P4 분석용 보존, 신규는 무편향 풀로 분리 축적.
- 버그 1건 잡음: 무작위 스크리닝 호출이 예산소진 예외를 try 밖에서 던져 크래시 → run_users_chunk 소스선정을 예외처리로 감쌈.
- daily_crawl.bat 갱신·배포 완료(2프로세스 가동, 예산 리셋 대기). 워치독 재시작도 새 설정 사용.
- **함의**: 이 무편향 풀이 곧 P6(OOD) 패널. 충분히 쌓이면 EASE·선호·knnpd03·업적 힌트를 순환 없는 독립 라벨로 최종 판정 가능.

## [2026-07-09 05:41] T41 — 크롤러 사망(6h) → 재시작 (사용자 신고 "다시 해")
- 마지막 로그 07-08 23:26(cycle 615, throttle 누적 215) 이후 ~6h 정지. 예산 33,938/90k 남은 채 사망(원인 미상 — throttle 다발 후 크래시 또는 절전 추정). 자율 워치독 wakeup이 그새 끊겨 자동복구 안 됨.
- daily_crawl.bat 재시작 → 05:41:32 정상 기동(source=random ach=False snowball=False), 예산 증가 확인. 재개형이라 손실 0.
- **무편향 풀 현황: depth=-1 프로빙 61,966 → 총 public+complete 8,753**(기존 편향 3,044 + 무편향 ~5,700). 이미 목표 규모에 근접 — P6/OOD 판정 가능 수준.
- 재발 방지로 워치독 wakeup 재설정.

## [2026-07-13 01:27] T42 — 무작위 크롤 정체 버그 2건 진단·수정 (사용자 "재시작")
크롤러가 07-10(1,589콜)·07-11(424콜)로 거의 안 돌고 있었음. 재시작만으론 다시 정체 → 근본 버그 2개 발견:
1. **CAUGHT-UP 오판**: 무작위 모드에서 한 사이클 n==0(일시 빈배치/throttle)을 "다 크롤함"으로 보고 **loop_sleep 3600s(1시간) 수면**. 무작위 공간은 무한한데 catch-up 판정 → 하루 대부분 잠. → 수정: random이면 n==0에 60s 재시도, circuit-open도 5min(무한 대기 방지).
2. **고정 시드 재생(치명)**: `random.Random(42)`가 매 재시작마다 **동일 sid 시퀀스 재생** → 그 sid들은 이미 크롤돼 `users`에 있어 전부 필터 → `_random_candidates` 후보 0개 → 크롤 정지. 재시작 반복하며 소진된 앞부분만 반복. → 수정: `SystemRandom()`(OS 엔트로피)로 매 실행 새 공간 탐색.
- 검증: API 정상(공개 80/82), 수정 후 예산 ~95콜/분·public_done ~7명/분(=~420명/시, ~7,000/일) 회복, throttle=0.
- 원인 총평: 크롤러가 "죽은" 게 아니라 두 버그로 **하루 ~400콜만 쓰며 사실상 정지**였음. 이제 정상.
- 무편향 풀 현황: public_done ~8,960(게임보유), 총 users 68k(비공개 포함). 계속 축적.

## [2026-07-14 03:13] T43 — P6 실행 개시: 사전등록 수정안 v3(사용자 승인) + 실측 정합화
사용자 지시 "P6 계획 + 방법론 재점검 + 무편향 풀 신규 시도 발굴" → 계획 승인 완료, P6 착수.
- **실측(07-14, steam.db 읽기전용)**: depth=-1 공개+완료 **9,742명**(전체 usable 12,794 중; 편향 3,052). "≥12 raw 보유" 4,302 ≠ **유효 플레이 항목 ≥12 적격 ≈3,416**(build_relevance는 rel>0만 유지 — 혼동 주의). B-적격(날짜有 미보유 위시 ≥3) **1,971(≈58%)**. 라이트(5–11 유효) 1,316. OOD 위시 92,661행 100% date_added>0. **depth=-1 업적 행 0**(07-07 OFF 이후) → relevance는 OOD에서 playtime-pctl 단독.
- **감사 발견(치명)**: v2 슬롯 표(S0a~S4)에 **EASE 슬롯 부재** — H1("EASE 격파")이 등록된 평가 셋 안에서 반증 불가 상태였음. 수정안 A1로 S5a/b/c(EASE λ50/100/200, `ease_reclist` 공정 빌더) 추가, **H1 판정은 λ100만**.
- **수정안 v3 (A1~A8) 승인**: A2 relevance 축퇴 명문화 / A3 패널 재정의(전체 적격에서 무조건 추출 — 위시 조건부면 몰입 편향; **N=1,000 + reserve 500 격리**) / A4 혼합그래프 = train∪탐색풀(패널 완전 홀드아웃 유지, "절반 편입" 폐기) / A5 지표 B = 기존 audit_verify 조작정의 고정(owned 취득시각 부재로 문자적 시간분할 불가) / A6 judge Sonnet만 자율(Gemini 배석 연기) / A7 FDR 패밀리 m=8 고정 / A8 outputs/p6 1회 추출 동결.
- **소셜 신호 실측 사망**: depth=-1 내 친구 엣지 **13개**(전 코호트 84) — 랜덤 샘플링 구조상 in-cohort 엣지 형성 불가. 시도 목록에서 제외 확정.
- **신규 시도 확정(탐색 풀 전용)**: E1 코호트-시프트 정량화(공짜) · E2 무편향 인기도/SNIPS 재교정 · E3 라이트유저 기술통계 · E4 포화곡선(크롤 중단 결정). E5(EASE 정밀+융합)는 H1 성립 조건부. 기각: 위시 ε-tier(지표 B 오염 위험), LambdaMART(기대값 낮음).
- **게이트**: V1(fresh-854 재현) V2(앵커 분리) V3(T34 +0.0073 재현) V4(방화벽 단언+음성테스트) V5(결정론) V6(메모리) 전부 green + **드라이런 리더보드 사용자 사인오프** 후에만 확정 1회 실행.
- 다음: 게임 메타 보충(미분류 1,012 appid ≈1k콜) → `outputs/p6` 추출 → 패널 동결(T44).

## [2026-07-14 03:35] T44 — 데이터 동결 + 패널 동결(방화벽) + V1·V3 검증 통과
**보충 크롤 결과(정직 보고 — 전제 반증)**: 미분류 1,013 appid는 "미방문"이 아니라 **전부 방문완료+appdetails 실패**(이름·SteamSpy 있음, type만 NULL). 표적 재시도 105콜 실측 → **회수 0건**, 원시 응답 = HTTP 200 + `success:false` = **영구 단종(delisted)**. 나머지 ~900콜 중단(낭비). 억제 규모 실측: OOD 플레이 행 3.47%·플레이타임 질량 2.95% — "구매 불가 게임의 정당한 풀 제외"로 수용(추천 대상도 아님).
**데이터 동결(A8)**: `behavioral_extract --out outputs/p6` — 유저 12,875·상호작용 1,708,415·플레이행 950,864·풀 40,863(미분류 1,678 제외). 이후 크롤 진행은 P6에 무영향.
**패널 동결(freeze-once, seed 20260714)**: 적격(유효항목 ≥12) **3,436** → confirm **1,000** / reserve **500** / exploration **1,936** / light(5–11) **1,252**. confirm 내 지표B 적격 **521**(T34 n=179의 2.9배). 위시 스냅샷 93,478행(`outputs/p6/wishlist_ood.pkl`). 교집합=∅·구 P4 패널 겹침=∅ 단언 통과. **sha256(confirm)=6cc39e4d…608c8e, sha256(reserve)=63268273…5318de** (전체 해시는 `experiments/p6_ood/p6_panels.json`).
**하네스 신설**: `p6_common.py`(슬롯 레지스트리 S0a~S5c+null, `assert_firewall`, `build_wl_targets` A5 조작정의, `ease_reclist` 공정 빌더 경유) · `p6_panel_freeze.py` · `p6_confirm.py`(dryrun/fresh854/confirm, 1회성 강제 `--acknowledge-one-shot`+기존 디렉토리 거부) · `p6_fdr.py`(A7 8쌍 고정 BH).
**V1 통과(T38 재현, 새 코드 경로)**: S5b(ease100) **0.3359** / S1(userknn) **0.2736** / S0b(knnpd03) **0.2663** / V1cc(condcos) **0.2304** — 4개 전부 T38과 소수 4자리 일치. paired ease−userknn **+0.0623 [+0.0565,+0.0679] SIG**(T38 +0.0623 [+0.0566,+0.0679]; CI 차는 부트스트랩 시드 지터). 앵커 ORACLE 1.0 ≫ 슬롯 ≫ POP 0.1322 정상.
**V3 통과(T34 재현)**: dev 위시 적격 **n=179 정확 일치**, S0b−S1 wl **+0.0073 [+0.0009,+0.0140] SIG**(T34 +0.0073 [+0.0011,+0.0142]) — 공유 `build_wl_targets` 동등성 확인.
- 다음: V2(드라이런 앵커 분리)·V4(방화벽 음성테스트)·V5(결정론)·V6(혼합 그래프 메모리) → T45.

## [2026-07-14 03:44] T45 — 검증 건틀릿 V1~V6 전부 green: 확정 실행 준비 완료(사인오프 대기)
**V4**: 패널 해시 검증 OK + 음성테스트 — confirm/reserve id 주입 시 `assert_firewall`이 정확히 예외 발생.
**V2 (앵커 분리, 양 그래프)**: 동결 — ORACLE 1.0 ≫ 실슬롯 0.169~0.256 ≫ null 0.128 ≫ POP 0.099. 혼합 — ORACLE 1.0 ≫ 0.238~0.321 ≫ POP 0.148 ≫ null 0.101. 지표 건강.
**V5 (결정론)**: 동결 드라이런 2회(tag a/b) per-user CSV 전부 **바이트 동일**(리더보드는 timing 컬럼만 상이).
**V6 (메모리/런타임)**: 혼합 그래프 2,769유저×24,524게임에서 EASE 적합 **~3초**(dense ~540MB) — 완화 사다리 불필요. 확정 런(1,000명) 예상 소요 = 그래프당 수 분.
**버그 1건(설계 검증의 승리)**: 혼합-드라이런에서 "그래프∩패널=∅" 단언이 발화 — 드라이런 유저를 탐색풀에서 뽑는데 혼합 그래프가 탐색풀 전체를 포함했기 때문. 수정 = 혼합 그래프에서 드라이런 유저 차감(확정 런과 동일한 홀드아웃 의미론). 수정 후 **동결 경로 무변화 재확인**(tag c, per-user CSV a와 바이트 동일 — freeze rule 준수).
**드라이런 관찰(탐색풀 300명 — 서술적, 판정 아님)**:
- 동결 그래프: **EASE 계열 선두 유지**(S5b 0.2556; S5b−S1=+0.040 — in-cohort +0.062 대비 수축, winner's curse 가시화되나 방향 유지). λ50/100/200 사실상 평평(0.2547/0.2556/0.2559). H2 방향: S2(pctl) 0.2210 ≥ S1(pvalue) 0.2160. **H3 위험 신호**: S0b−S1 wl = +0.0043(in-cohort +0.0073보다 약함); 혼합 그래프에선 **역전**(0.0350 vs 0.0418).
- 혼합 그래프(OOD 1,636명 그래프 편입): 전 슬롯 상승(S5b 0.2556→0.3208, S1 0.2160→0.2748) — **데이터 스케일링 레버가 OOD에서도 작동**(E4 예고편). S4(condcos)도 0.2773으로 회복(3위).
- 지표 B 적격 155/300(=52%, confirm 예상 521과 일치).
**상태**: 사전 체크리스트 중 "드라이런 리더보드 사용자 사인오프"만 남음. 사인오프 후 `--panel confirm --graph frozen → mixed` 1회 실행 + p6_fdr(m=8).

## [2026-07-14 04:12] T46 — **P6 확정 판정 (1회성 실행 완료): H1 성립 → 서빙=EASE · H2 → pctl_game · H3(β0.3) 기각**
사용자 사인오프(승인) 후 확정 패널 1,000명(지표B 적격 521) 1회 실행 — 동결 그래프(판정) + 혼합 그래프(보조) + BH-FDR(m=8). 산출물 `experiments/p6_ood/confirm_frozen/`·`confirm_mixed/`(per-user CSV 로컬, fdr.csv 포함), config에 git 해시·패널 sha 기록.
**등록 패밀리 판정(동결 그래프)**:
- ① EASE−userknn [NDCG] **+0.0417 [+0.0355,+0.0479] q≈0 SIG** ② EASE−condcos **+0.0447 [+0.0382,+0.0515] q≈0 SIG** → **H1 성립. P5 서빙 랭커 = EASE(λ100) 확정.**
- ⑧ EASE−userknn [wishlist] **+0.0122 [+0.0052,+0.0189] q=0.0013 SIG** — target-독립 축까지 EASE 승리. **순환·코호트 편향 둘 다 벗어난 최초의 완전 확정.**
- ③ pvalue−pctl [NDCG] −0.0025 [−0.0047,−0.0002] q=0.023 SIG(pctl 우세) ④ [wl] ns → **H2: 판정축(B) ns → 최단순 pctl_game 채택.** (v2의 "구별 불가" 예상은 A축에서 미세하게 깨졌으나 방향이 pctl 우세라 채택 결론 동일 — 정직 기록.)
- ⑤ knnpd03(β0.3)−userknn [wl] +0.0021 ns ⑦ [NDCG] **−0.0156 SIG 해악** → **H3(β0.3) 반증 조건 발동: knnpd03 폐기.** ⑥ β0.2 [wl] +0.0042 q=0.0494 경계 SIG — 단 EASE가 양축 모두 지배(wl: EASE 0.0485 > S0a 0.0406)라 **발굴 knob으로도 서빙 가치 없음**(userknn-계열 레거시 레버로만 기록).
- 혼합 그래프(보조): 동일 순서, EASE 0.3264 선두 — 판정과 정합. 전 슬롯 리프트(EASE 0.2468→0.3264) = 유저 수 레버 OOD 작동 실증(E4가 정량화 예정).
- 앵커: 동결 ORACLE 1.0 ≫ 슬롯 ≫ null 0.1319 ≫ POP 0.0978 / 혼합 null 0.1032 ≫ POP 0.157?? → 혼합은 POP 0.157 > null 0.103 (정상 — 그래프 커져 POP 순위 개선). 지표 건강.
- **winner's curse 실측**: EASE−userknn in-cohort(fresh854) +0.062 → OOD +0.042 (~33% 수축) — 방향·유의 생존. 절대 규모도 수축(EASE 0.336→0.247).
- **절대 단위(계획 9-1)**: 추천 20개당 실제 미래 위시 적중 — EASE **0.326개** vs userknn 0.261 vs POP **0.098**(3.3×). 유저당 정답 평균 7.69개(중앙값 10). 오프라인 MNAR 하한선 명시.
- **잔여 정직 노트**: 서빙 조합 `pctl_game × EASE`는 등록 슬롯이 아니었음(EASE 슬롯은 pvalue). H2가 사실상 동률이라 영향 희박하나, P5 빌드 시 탐색 풀 sanity-check 1회 예정(확정 주장 아님).
- 문서 반영: results.md(P6 판정 표+절대 단위)·status.md·roadmap.md(P6 done)·decisions.md(서빙/선호/knob 확정). 다음: E1~E4 탐색 트랙(+E5 해금됨), 절대 루브릭 judge(9-2), P5.

## [2026-07-14 04:58] T47 — E1(코호트-시프트)·E2(무편향 인기도)·E3(라이트 유저) 완료 + EASE 정당성 가설 T-b 확증
스크립트: `p6_e1_cohort_shift.py`·`p6_e2_unbiased_pop.py`·`p6_e3_light_users.py` (전부 탐색풀/기존 산출물만 — 확정 패널 재조회 없음).
**E1 — winner's curse 전체 지도** (in-cohort fresh-854를 playtime-only 정답으로 재채점 = OOD와 apples-to-apples):
- 실슬롯 수축 **18~30%** (EASE λ100 −23.8%, S1 −22.4%, S3 −29.7%). **슬롯 순위는 대체로 보존: Kendall τ=0.822 (p=0.0004)** — in-cohort shortlisting은 "순위 신뢰, 절대값 불신"이 정량 결론.
- **이상 관찰(정직 기록)**: null(random_support)은 OOD에서 오히려 **+37% 상승**(0.096→0.132) — OOD 유저의 홀드아웃이 작고 인기작 위주라 인기 보존형 널이 유리해짐. 널 대비 마진이 OOD에서 좁아진다는 뜻이므로 향후 비교는 반드시 널-마진으로 볼 것.
- **T-b(EASE=회귀 우위 가설) 확증**: EASE−userknn 격차가 프로필 크기와 단조 증가 — in-cohort(pt-only) [0,15) **−0.003**(동률) / [15,40) +0.021 / [40+) **+0.068**; OOD +0.026 / +0.037 / +0.056. 공선성(큰 라이브러리)이 클수록 회귀(결합추정)가 유사도-합산을 벌린다는 예측 그대로. EASE 승리의 구조적 정당화가 실측으로 성립.
**E2 — 무편향 인기도**: OOD 9,823 vs 편향 3,052 소유율 Spearman **0.715** — 스노볼 인기도는 실제 인구와 상당히 다름. 최대 왜곡 = F2P/캐주얼/바이럴(Goose Goose Duck 실제 32위 vs 편향 1,590위, NARAKA·Stumble Guys·WoWs 등) — 리뷰어 코호트가 캐주얼 층을 체계적으로 과소평가. `outputs/p6/pop_unbiased.json`(21,160 appid) = P5 서빙용 무편향 인기도 prior 산출. **SNIPS 민감도**: EASE 1위는 propensity 모델 불변; 단 S0a(pop-discount)의 SNIPS 우위는 무편향 propensity에서 소멸(S1과 역전) — **knob의 SNIPS 이점 일부는 propensity 오추정을 착취한 것**이었다는 방증(P6 본판정과 정합).
**E3 — 라이트 유저(5–11 유효, n=1,252, 서술 전용)**: **개인화가 전형 유저에게도 유효** — EASE 0.2156 [0.1997,0.2314] vs null 0.1455 vs POP 0.0909 (NDCG 2.4배), recall@20 0.335 vs POP 0.148. EASE가 적격 컷 아래에서도 선두 유지. 홀드아웃 중앙값 2개 → 판정 없음, 서빙 함의(인기도 폴백 불필요 방향)만 기록.
- 남은 트랙: E4×E6(포화곡선+투타워 기울기 — `p6_twotower.py` 구현 완료, 러너 작성 중), E5(λ그리드+융합+SLIM·EDLAE+**T-a 음수클립 절제**), 9-2 절대 루브릭 judge.

## [2026-07-14 05:28] T48 — E4×E6(포화곡선+투타워)·E5(도전자) 완료: EASE 전 방어 + 정당성 T-a 확증 + 크롤 지속 판정
**E5 (탐색풀 400명, G2 그래프 2,669, 지표B 적격 206 — `p6_e5_challengers.py`)**:
- λ 정밀 그리드 {30..300}: λ30~100 평평(전부 ns; λ50 +0.0035 ns), **λ140+ 유의 열세** → λ100 유지. REPORT_MONDAY 잔여 리스크 ④ **null로 종결**.
- **T-a 확증(음수 가중치 절제)**: `ease_l100_nonneg`(B 음수항 0 클립, 정확 행 계산) **−0.0088 [−0.0134,−0.0046] SIG** — EASE의 음수 관계가 실신호. T-b(T47)와 함께 "왜 EASE인가"의 두 반증 가능 테스트 모두 성립.
- EDLAE(α 0.1/0.5/1.0) 전부 **유의 열세**(−0.057~−0.092) — 정규화-변형 계열이 아래로 분리 → **SLIM 연기 확정**(같은 계열 10-100× 비용, 상방 기대값 소멸 — 기록된 결정).
- 융합: z-blend 0.7 동률(ns), 나머지 열세 → null 종결. wl 축 전부 ns.
**E4×E6 (`p6_e4_scaling.py` — 고정 탐색 400명 평가, 그래프 사다리 1,133/1,901/2,669)**:
- **EASE 포화곡선**: 0.2333 → 0.2876 → 0.2981 — 상승 지속·감속 시작(+768명당 +0.054 → +0.010). **판정: 크롤 계속**(곡선 평탄화 전; P9 주기 재평가에서 재측정).
- **투타워 v1(피처 전용) → v2(id32+피처 하이브리드, 표준형)**: v1 0.016~0.033은 태그-쌍둥이 구분 불가의 구조적 핸디캡 → 공정성 자체 지적 후 v2 재실행. v2도 **0.027~0.066** — null(~0.13)에도 못 미침. 사전 예측 **P1 확증**(전 그래프에서 EASE 승).
- **P2 확증(결정타)**: 기울기 EASE **0.078**/log-user vs 투타워 **0.021~0.022** — 교차 없음, 이 체급에선 데이터가 늘수록 격차 **확대**. "얼마나 크롤하면 투타워가 유의미?"의 실측 답 = **크롤 가능 범위 내엔 없음**(문헌 MSD 34M 상호작용에서도 선형 승과 정합).
- **P3 방향 확증**: 콜드 아이템(그래프 support<3) recall — EASE **0.0000(구조적)** vs 투타워 0.013~0.020. 투타워의 유일 실효 니치 = 콜드 스코어링(단 절대값 미미).
- 정직 한계: 본 투타워는 축소 구현(dim64·10ep·CPU·태그+id32) — 절대값은 튜닝 여지 있으나 **기울기 비교**가 본 결론이며 그것은 구현 강도에 둔감.
- 다음: 9-2 절대 루브릭 judge(3암 블라인드 20명×30항목, `JUDGE_ABS_PREREG.md` 등록·Sonnet 판정 진행 중) → 종합 문서화.

## [2026-07-14 05:44] T49 — 절대 루브릭 judge 완료: EASE 절대 precision@10 = High 44.5% (탐색 트랙 전체 종료)
`JUDGE_ABS_PREREG.md` 설계 그대로 실행 — 탐색풀 20명(시드 20260715, 방화벽 단언), 3암(ease/pop/rand × top-10) 유저당 30항목 단일 셔플 블라인드, Sonnet 4에이전트 분담 판정(600 판정), `p6_judge_abs.py --aggregate`.
- **ease: High 44.5% [35.5,54.0] / High+Medium 71.0% [64.0,78.0]** · pop: 7.5% / 38.0% · rand: 6.5% / 27.0%.
- **판독 유효성(등록 기준) 충족**: ease ≫ rand CI 비겹침. 부수: pop의 strict가 rand와 동급(7.5 vs 6.5) — "유명해서 High"를 judge가 주지 않음(anti-familiarity 지시 작동), pop은 lenient에서만 분리.
- **유명작 편향 점검**: 판정별 게임 인기도 중앙값 High 1,133 / Medium 2,419 / Low 1,012 — High가 인기도에 끌리지 않음(등록된 1번 한계가 이번 런에선 미발현).
- 해석(등록된 한계 병기): 카드-기반 프록시이며 실인간 미검증. 그래도 절대 서사 완성 — **"블라인드 판정에서 추천 10개 중 4~5개가 명확한 취향 적합(무작위는 0.7개)"**.
- 잔여 후속(선택): 실인간 소표본(본인 프로필 데모), Gemini κ 교차(사용자 배석 시). **P6 + 탐색 트랙 전체 종료 — 다음 = P5 빌더 재배선.**

## [2026-07-14 05:43] T50 — 뒤집은 절대 지표(사용자 제안): "위시 전부 적중까지 추천 몇 위?" — 깊이 분포 실측
사용자 제안으로 hits@20을 뒤집어 순위-깊이를 측정(`p6_wl_rank_depth.py`, 탐색풀 206명·G2 그래프, EASE vs POP). **T(유저당 타깃 수) 처리 = 2중 보고**: (a) 타깃 단위 풀링(각 위시 항목의 순위 = 관측 1개 → T 의존 제거), (b) 유저 단위 커버리지 K(T 병기). 등록 정의(최근 ≤10) + 무제한 타깃 변형 둘 다.
- **타깃 단위(A5, 1,655개)**: EASE 중앙값 순위 **988위**(24.5k 랭킹 가능 중 상위 4%) vs POP 2,689위 — **2.7배 상위**. top-20 안 4.0%(POP 1.6%)·top-100 15.8%(7.2%)·top-500 38.3%(24.2%) — **전 깊이에서 2.2~2.9배 우위 유지**.
- **유저 단위**: 위시 **절반** 커버 K 중앙값 = EASE **933위**(POP 2,681위). **전부(100%)** 커버 K 중앙값 = **~23,700위 ≈ 사실상 전체 카탈로그** — 최악-순위 타깃 1개가 지배(유저마다 모델이 깊은 꼬리에 두는 니치 위시가 거의 반드시 존재 + 타깃의 3.8%는 co-play 인덱스 밖=랭킹 불가). **"전부 적중 K"는 어떤 랭커에도 실질 도달 불가 — 유효한 뒤집은 지표는 중앙값 타깃 순위와 K@50%.**
- 무제한 타깃 변형: T 평균 42.3(중앙값 11.5, max 1,307 — 고래 위시). 전부-커버는 구조상 전체 카탈로그.
- **정직한 함의**: hits@20(0.33개)은 헤드 성능만 보여줌 — 전형 타깃은 ~1,000위에 있고 top-20은 타깃의 4%만 잡는다는 게 과제의 실제 규모. 단 EASE의 우위가 깊이 전 구간에서 유지되므로 비교 결론은 불변. 절대 보고 표준에 "중앙값 타깃 순위 988위(상위 4%) / 위시 절반 커버 K=933" 병기 채택.

## [2026-07-14 07:02] T50-보강 — 커버리지 곡선 전체 분포(사용자 지적: "최대 깊이 말고 분포를 봐라") + 꼬리 역전 발견·정정
K_GRID 11점 CDF + 유저별 25/50/75/90/100% 커버 K 분위(중앙[p25,p75])로 확장.
- **풀링 CDF(A5 타깃 1,655)**: K=20에서 EASE 4.0% vs POP 1.6% · K=100 15.8/7.2 · K=500 38.3/24.2 · K=1,000 50.3/34.7 · K=5,000 69.7/65.4 — **서빙 유의 구간(K≤5,000) 전체에서 EASE 2~2.5배 우위**.
- **유저별 K@커버리지(EASE)**: 25% = 344 [134,1004] · 50% = 933 [392,3165] · 75% = 5,025 [1277,17694] · 90% = 17,388 — "전부 커버(max)"가 아니라 분포로 특성화 완료.
- **꼬리 역전 발견(직전 기술 정정)**: K≥10,000에서 POP가 EASE 추월(K=10k: 79.5 vs 76.0 / K=20k: 91.8 vs 83.3). 기제: (1) 인기 열거는 결국 위시(인기 편중)를 다 훑음 (2) EASE 랭킹 가능 인덱스가 24.5k로 풀(40.9k)보다 작아 인덱스 밖 타깃(63개)이 바닥 대체됨. **서빙과 무관한 인공물 구간이지만, 직전 T50의 "전 깊이 우위" 표현은 과장이었으므로 정정** — 정확한 표현: "서빙 유의 깊이(K≤5,000)에서 2~2.5배 우위, 초심층 꼬리는 역전(기계적)". results.md 반영.

## [2026-07-14 07:35] T51 — judge 천장 캘리브레이션(사용자 질문 "44.5%밖에 안돼?"의 답): **EASE = 계기 천장**
사후 캘리브레이션 암(`p6_judge_ceiling.py`, JUDGE_ABS_PREREG 부록 — 등록된 3암 결과는 불변): 동일 20명(시드 동일)의 **본인 실제 애호 게임**(참여도 9~18위 — judge가 보는 취향 카드 8장과 분리)을 추천인 척 동일 루브릭·블라인드로 판정.
- **천장: High 42.5% [35.5,49.2] / High+Medium 71.3% [63.4,78.8]** — 유저가 실제 사랑하는 게임조차 이 계기에선 42.5%만 High.
- **EASE 44.5% [35.5,54.0] / 71.0%** → **계기 천장과 통계적으로 구별 불가(명목상 동률+)**. "44.5%밖에"가 아니라 이 계기가 줄 수 있는 최대치. 잔여 품질 격차는 이 계기로는 측정 불가 — 더 좋은 계기(실인간·풍부한 프로필) 필요.
- 천장이 100%가 아닌 이유(계기 한계의 실체): ① judge는 취향을 카드 8장으로만 봄 — 8장 밖 취향 영역의 애호작은 신호 부족 판정 ② 루브릭상 인접 장르·부분 적합은 Medium ③ 카드(장르+160자)로는 메커닉/바이브 신호 소실.
- **정직 뉘앙스**: EASE≈천장이 "추천이 애호작만큼 좋다"는 뜻은 아님 — 이 계기는 "상위 8장 카드와의 적합"을 재고, EASE는 그것과 상관된 목적을 최적화함(본인 라이브러리는 top-8보다 다양해서 천장 암이 불리한 면도 있음). 정확한 진술: "**이 계기의 눈금으로는 구별 불가**".
- 부수 확인: 3암 대비 — 천장 42.5 / EASE 44.5 / POP 7.5 / rand 6.5 → 계기의 동적 범위가 6~45로 충분히 넓어 "EASE≈천장"이 계기 포화 탓이 아님(POP가 7.5에 깔려 있음).

## [2026-07-15 03:35] T52 — 계기 v2(사용자 질문 "해결할 수 없어?"의 답): 천장을 올려도 **EASE가 그대로 따라감** — 결론 계기-불변
v1의 3가지 한계를 각각 수리한 v2 계기: ① 취향 요약 = 라이브러리 **전체**의 참여도-가중 태그 분포 12개("Strategy 45%…") ② 넓이 신호 = 중위권(19위+) 보유작 6개 병기 ③ 후보 카드에 SteamSpy 태그 상위 5개 추가. 동일 20명·동일 암·동일 루브릭 재판정(3암 600 + 천장 200).
| 암 | v1 High | **v2 High** | v1 관대 | v2 관대 |
|---|---|---|---|---|
| 천장(본인 애호작) | 42.5 | **51.3 [44.1,58.0]** | 71.3 | 80.2 |
| EASE | 44.5 | **50.0 [41.5,58.0]** | 71.0 | 82.0 |
| POP | 7.5 | 28.0 | 38.0 | 57.5 |
| rand | 6.5 | 7.5 | 27.0 | 27.0 |
- **주결론**: 계기 개선으로 천장 +8.8pp 상승 → EASE도 +5.5pp 동반 상승, **여전히 천장과 구별 불가**(50.0 vs 51.3, CI 대폭 겹침). "44.5%밖에"의 답 = **추천기가 아니라 계기가 병목**이며, 이는 계기를 갈아끼워도 유지되는 계기-불변 결론. 잔여 품질 상한을 재려면 실인간 평가(3단계)뿐.
- **부수 관찰(정직)**: v2에서 POP가 7.5→28.0으로 급등 + 판정-인기도 상관이 생김(High 중앙 인기도 1,540 vs Low 64; v1은 무상관). 해석 이중성 — (a) 전체-라이브러리 태그 요약엔 대중적 태그가 포함되므로 인기작이 *정당하게* 더 맞음(인기작이 인기 있는 이유), (b) 태그 요약이 유명작 High의 명분을 제공(familiarity 재유입). 분리 불가 — 단 rand는 7.5로 불변이라 "무명작 무차별 상향"은 아님. v2는 더 정보량 많은 계기지만 인기도-상관 경고 병기.
- EASE 50 vs POP 28: 인기도에 최대 관용을 준 계기에서도 +22pp — 개인화 가치의 보수적 하한.

## [2026-07-20 04:38] T53 — **P5 빌더 재배선 완료: EASE가 실제 앱에 장착됨** (스모크 PASS, 커밋 4171a7e)
P6 확정 구성(EASE λ100 × pctl_game + 무편향 인기도)을 서빙 실물로. 스냅샷 `outputs/p5`(유저 23,347·플레이 1.24M행·풀 41,266).
**EASE 아티팩트(`build_ease_artifact.py`)**: 유효 ≥5 유저서 시드 12,000명 캡 적합(float32 그램·float64 역행렬, **43초**) → E5의 정확 B-행 청크 계산 재사용 → |값| top-K 희소화(음수 보존 — T-a 근거).
- **압축 사다리 실측**: K=512 −0.0183 SIG 탈락 → K=1024 −0.0089 탈락 → **사용자 승인으로 1칸 연장** → **K=2048 통과: −0.0027 [−0.0041,−0.0013] (허용 −0.005), top-20 Jaccard 0.966**. 아티팩트 345MB(gitignore, meta는 추적).
- **G-b(잔여 의문 종결)**: 서빙 조합 pctl×EASE가 pvalue×EASE 대비 **+0.0104 [+0.0071,+0.0139] SIG 우세**(탐색풀 400) — status.md에 걸려 있던 "등록 슬롯에 없던 조합" sanity 해소, 오히려 양성.
- **G-c**: 신규 유저용 ECDF 보간 가중치(21분위 그리드) ≈ 정확 pctl (Spearman 0.9961, e2e +0.0008).
**카탈로그(`build_catalog_db.py`)**: 전부 DB-네이티브 — 태그 행렬 9,956→**34,796게임**(큐레이티드 447태그), 품질 = steamspy pos/neg 동일 shrink(**34,735게임**, 구 ~8.6k), 인기도 = **현 시점 무편향 재추정(OOD 20,282명)**, catalog.json(제약 메타 41,266행), 타이틀 CSV 재생성. 신규 pytest 7종 포함 전체 39 green.
**서빙 스왑**: `EASERecommender` 어댑터(score/col/inv_col/game_avg_pt — 그래프 계약 유지, 컷오프 무배제 명문화). **서빙 코드의 cutoff 버그 패턴 3곳 제거**(hybrid._cf_ranked / agent_graph._interleave / seed_node — condcos 시절 무해했으나 EASE 음수 꼬리를 자르는 T35 재발 지점), steered 정규화 max-나눗셈→min-max(음수 안전), CatalogMeta CSV→catalog.json, 데모 라이브러리 CSV→steam.db, 시드 경로 = 명시 가중치 API(ECDF 오해석 방지), sync_data FAISS-시대 화이트리스트 8종 제거.
**스모크(LLM 우회, 실제 앱 코드 경로) PASS**: 데모 라이브러리(CS:S/포탈/L4D2 133게임) → 위쳐3·어몽어스·스타듀 등 20추천 / 시드 CS2 → PUBG·Apex·Aimlabs / 탐험 모드 top-10 9/10 교체(Slay the Spire 2 등) / 제약(협동+한국어) 18/30·품질 게이트 26/30 작동. **런타임 CSV 의존 0 달성**(로드맵 P5 완료 조건). 잔여 = P5-4 문서 + 풀 e2e(LLM 라우터, 사용자 배석 P8).

## [2026-07-21 09:50] T54 — **P8-A 완료: 실제 Gemini 라우터로 전 6경로 e2e 7/7 PASS** (배석 세션)
신규 `p8_e2e.py`: 실제 그래프(`build_agentic_graph`+`graph.invoke`)를 앱 예시 프롬프트 코퍼스로 구동, 경로별 단언(라우팅·후보·제약 준수·응답).
**LLM 모델 오디세이(실측 기록 — 서빙 운영 제약)**: `.env`의 gemini-2.5-pro = 무료 티어 할당량 **0**(전 콜 429; 앱 자체가 LLM 불능 상태였음 — 폴백 체인이 견딘 건 부수 확인) → 2.5-flash = 신규 사용자 은퇴 404 → flash-latest/3.5-flash = 503 폭주 → **`gemini-3-flash-preview` 채택**(프로브 200 OK; `.env` last-wins append로 전환, 앱 기본값도 flash로). **실질 제약 = 무료 일일 20콜/모델** — 배석 e2e/데모 설계는 이 예산 안에서.
**사전 식별 수정 4건의 실증 결과**:
- ① **통화 체인 수정+검증**: 실측상 가격은 KRW ~99.3%(엘든링 64,800원 정확) + 외화 273행 혼입(위쳐 "3.99"가 모든 상한 통과하는 누수). 수정 = catalog에 `currency` 필드, max_price=KRW 해석·비KRW 보수적 드롭, 라우터 프롬프트 원화 명시 → **e2e에서 "2만원 이하 협동" 300→99 정상 필터링 검증**.
- ④ 라우터 프롬프트 `single_player` 누락 보완.
- ②(anonymous 정확-일치 매핑) ③(빈 결과 가드): **e2e에서 미발현** — anonymous가 LLM 제목 10중 8매핑(카탈로그 41k 확대 덕), 빈 경로 미발생 → 관찰-우선 원칙대로 수정 보류, 위험만 기록.
**경로별(run3+run3b 합산 7/7)**: library ✓ / seed(다크소울→정라우팅) ✓ / explore ✓ / multi(300→85 필터) ✓ / 제약 협동+한국어(300→83) ✓ / 제약 가격(300→99) ✓ / anonymous 무라이브러리(8후보) ✓. pytest 39 green. **로드맵 P8 완료 조건("전 서빙 경로 e2e 통과 + 테스트 green") 충족** — 잔여 = Part B(본인 계정 데모)·Part C(Gemini κ, 일일 쿼터 제약으로 flash-lite 또는 쿼터 리셋 후).

## [2026-07-21 09:57] T55 — **P8-C 완료: Gemini 교차판정 — 두 독립 심사자가 "EASE ≈ 천장"을 재현** (JUDGE_ABS_PREREG 이행)
`p8_judge_kappa.py`(REST 직호출·페이싱·쿼터-우아한 중단): 등록된 v2 계기 페이로드 40케이스(3암 20 + 천장 20)를 `gemini-3.1-flash-lite`(별도 쿼터)로 동일 루브릭 재판정, 파싱 성공 40/40.
- **교차 일치도**: 3암 **κ=0.488**(600쌍, 일치 66.0%) / 천장 **κ=0.578**(180쌍, 74.4%) — 사전 명시 기준 κ≥0.4 충족 → **계기 신뢰 보강**. 암별 κ: ease 0.424 / rand 0.490 / pop 0.306(최저 — v2의 인기도-상관 경고 축과 정합).
- **Gemini 독립 절대 판정(소넷 미노출)**: ease **59.5% [53.0,66.5]** / 천장 **52.2% [46.8,58.1]** / pop 31.5 / rand 6.0 (관대: 94.0/85.8/75.0/27.0) → **독립 심사자도 EASE≈천장(명목상 상회) ≫ pop ≫ rand 순서 재현**. "심사자 단일 편견" 반론 실질 종결. 등록된 3암 결론 불변(사전 명시대로).
- 산출: `verdicts_gemini_v2.json`·`verdicts_gemini_ceiling_v2.json`·`summary_kappa_*.json`. Part B(본인 계정 데모)는 SteamID 대기.

## [2026-07-21 23:10] T56 — **P8-B: 본인 계정 실인간 평가(N=1) — 계기 수치와 정합 + 표면별 피드백 2건**
본인 라이브러리(98게임, ER 844h·인디 다수)로 엔진 데모(LLM 무관 경로) → 본인이 직접 평정. 기록은 로컬 `my_demo.md`(gitignore).
- **top-10 개인화 평정: 관심 7 / 모름 1 / 그닥 2** → 관심 70%·비부정 80% — **계기 예측(관대 82%·보정 추정 ~90%)과 실인간이 근접**. 실인간 평가 3단계의 N=1 데이터 포인트로, judge 프록시가 실취향과 정렬됨을 처음으로 직접 확인.
- **pctl 보정 실증(사용자 질문 → 실측)**: raw 1등 ER(844h)이 백분위 가중치론 3등(0.963), 1등은 SANABI 26h(1.000) — "온라인 게임 시간 인플레를 게임별 분포가 흡수"하는 P4 설계가 본인 계정에서 그대로 확인됨. 사용자에게 표로 시연.
- **피드백 1 — co-play "유사"의 의미 격차**: "GGD가 ER과 비슷한지 모르겠다" — 단 본인이 GGD 26h 보유·플레이(co-play 예측이 본인에게도 참). 콘텐츠-유사 기대 vs 플레이어층-겹침 정의의 UX 격차로 기록.
- **피드백 2 — 탐험 모드의 구조적 한계 사례**: 인디-중심 프로필에서 "미탐험 장르" ≈ 멀티/슈터로 수렴 → 탐험 추천이 "(멀티 말곤) 특징 없는 감성"으로 체감. novelty가 설계대로 작동했으나 이 프로필군에선 싫어하는 방향과 겹침. 기존 레버 = 제약 결합("싱글로 새로운 장르")·aspect 스티어링; 신규 개발은 백로그(과설계 자제).
- **피드백 3 — 유명작 편중 체감**: top-10 중 9개 기지(旣知) — depth 분석(헤드 집중)과 정합하는 세렌디피티 한계.

## [2026-07-21 23:20] T57 — 시드 경로 태그 게이트 (실인간 피드백 → 당일 제품 수정)
**발단(사용자)**: "ER 같은 거 → 유희왕이 말이 되냐" — 대중적 시드에서 co-play 유사가 **인구 차트로 퇴화**하는 구조 결함(P8 e2e는 라우팅만 검증, 내용 품질 미검증이었음을 인정).
**수정**: `seed_node`에 태그-코사인 게이트(`_tag_gate`, min_sim 0.25·미달 시 상위-절반 폴백·**태그 무데이터 = 미지≠비유사로 통과**) — Era-1 유사모드 검증 승자(태그-코사인 Vb)를 P5 재구축 태그 행렬(34.8k게임) 위에서 재사용. co-play가 품질·현실성("실제로 같이 함"), 태그가 콘텐츠 유사를 담당. 확정된 개인화 랭킹(EASE)은 불변.
**before/after (ER 시드 top-10)**: 유희왕·구스구스덕·Muse Dash·DbD 탈락 → **Immortal Soul: Black Survival(ER 직계 전신, sim 0.50)·SMITE(MOBA 0.45)·Albion(0.40)·KurtzPel(0.35)** 상승. 후보 300→87. sanity: Hollow Knight 시드는 게이트 후에도 Celeste/Dead Cells/Ori 유지(니치 시드 무해), Stardew는 BG3(0.15)·RDR2 탈락으로 코지 클러스터 조임.
**잔여 한계(정직)**: 경계값 0.25 부근(철권 0.25·DJMAX 0.25)은 여전히 통과 — 임계 상향은 과필터 위험과 트레이드오프, 실사용 피드백으로 재조정 여지.
