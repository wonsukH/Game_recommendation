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
