# P4 자율 운행 체크포인트 보고서 — 월요일 (v7 — 적대적 감사 반영)

> **유형**: experiment-report · **상태**: active · **갱신**: 2026-07-06 11:15 (v6를 자체 적대적 감사로 교정 — v6의 "S0 확정 승자" 프레이밍은 아래 T32~T33으로 하향됨)

> 읽는 순서: 이 보고서(요약·결정) → `LEADERBOARD.md` → `P6_PREREG.md`(target-독립 주지표 추가됨) → `JOURNAL.md`(전 과정 감사, T0~T33) → run 디렉토리.

## ⚠️ 자체 감사 교정 (T32~T33 — 반드시 먼저 읽을 것)
v6는 **S0 = pvalue×user-KNN+인기패널티(β0.3)를 "확정 승자"로 과대포장**했습니다. ultracode 적대적 감사(5렌즈·44에이전트, 39우려 검증)가 이를 반증했고, 결정적 read-only 재검(dev, private/Gemini 미사용)으로 확정했습니다:
- **주 지표(graded NDCG)는 순환**: per-game Spearman(선호 s, 정답 rel) = **0.957**(pvalue·pctl 둘 다) — 선호가 자기 정답지의 단조 복사본. 모든 검증축(masked·judge·fresh NDCG·기존 P6안)이 같은 타깃 재사용 → 순환 미반박.
- **S0의 "우위"는 순환/이중계상**: dev 페어드 — NDCG **ns(+0.0016)** · recall@20 **유의 손실(−0.0112)** · SNIPS **+0.0081 SIG**(단 pop-debias는 knnpd03이 설계상 움직이는 축). judge의 "덜 뻔한 픽 우대" 기준이 pop-discount와 동어반복(적합/발굴 컬럼 34/35 동일 = 1축). = **품질 향상이 아니라 recall↔발굴 트레이드 knob**.
- **target-독립 유일 검증(wishlist 홀드아웃)**: S0−S1 = **+0.0056 [−0.0002,+0.0124] ns**(점추정 앞서나 미유의).
- **살아남는 진짜 결과(BH-FDR 통과)**: **user-KNN 계열 ≫ 프로덕션 condcos +0.0242(q=0.004)** + 전 고전랭커 압도. **랭커가 선호보다 크고 강건한 레버**.

## TL;DR (교정본)
P4의 **실측으로 방어되는 결과는 "랭커 교체"**입니다 — user-KNN(및 RP3β)이 현 프로덕션 co-play CF(condcos)를 유의하게(FDR 통과) 이깁니다. **선호 정의**는 pvalue/pctl 모두 무난하나 주 지표상 서로 구별이 강건하지 않고(순환 타깃 한계), **knnpd03 인기패널티(구 "S0")는 측정된 승리가 아니라 발굴-강조 knob**입니다. games 크롤 완주(풀 38,435), 유저 2,655/10k. **최종 선택은 target-독립 주지표를 넣은 P6에서만** — 그 프로토콜은 이 감사로 보강됨.

## 결정해주셔야 할 것 (교정·우선순위순)
1. **랭커(강건 결과)**: **user-KNN/RP3β로 교체 권고** — condcos 대비 +0.0242(BH-q=0.004) 유의, 전 고전랭커 압도. P5 재배선의 실질 내용. *유일 유의사항: 규모 의존성(10k서 EASE/ALS 재평가) — 현재 1.7k에선 userknn 우세.*
2. **선호 = pvalue vs pctl_game**: 주 지표상 userknn 위에서 **구별 불가(ns)**. pvalue는 knnpd03서만·wishlist서 약하게 앞섬. *권고: 최단순 pctl_game을 기본으로, pvalue는 동급 후보로 P6 병행.*
3. **knnpd03(구 S0) 처리**: **주지표 승자 아님(NDCG ns·recall −0.0095 SIG 손실)** — 단 웨이브2(2,655유저)에서 **target-독립 wishlist축이 +0.0073 SIG로 전환**(T34) → phantom 아닌 **정당한 발굴-지향 knob**(playtime-재현↔발굴 트레이드, 비순환 근거 확보). *권고: "playtime 재현"이 목표면 순정 userknn, "다음 구매/발굴 예측"이 목표면 knnpd03 — 제품 목표에 따라 선택. 최종은 P6 OOD로 확정.*
4. **P6 사전등록 승인(보강본)**: `P6_PREREG.md`에 **target-독립 co-주지표(wishlist 홀드아웃)** 추가됨 — 순환 없는 판정만이 knnpd03·선호 우열을 가른다. 랜덤-accountID 패널·반증조건·비용(~하루 예산).
5. **유저-크롤 allowlist 축소**(96% 절감): rarity E 음성으로 논거 유지 — 완료율만 유효. 채택 시 10k ETA 대폭 단축.
6. **음성결과 수용(5종)**: 학습형 blend ns · 의도 ε-tier 기각 · informed-neg BPR −0.0514 SIG · rarity E 음성 · MF 전패. (감사에서 EASE 람다그리드·학습형 리랭커 미탐색이 열린 항목으로 지적됨 — P6 전 재검 권고.)

## 후보 (감사 교정 반영 — LEADERBOARD.md 상세)
| 구성 | 주 지표(NDCG, 순환 주의) | recall@20 | SNIPS(pop-debias) | judge(pop-정렬) | 정직 상태 |
|---|---|---|---|---|---|
| pvalue×userknn (구 S1) | private 0.2943·dev 0.2776 | **높음** | 낮음 | — | **P6 주후보** |
| pctl×userknn (구 S2) | ≈ 위와 구별불가(ns) | 높음 | 낮음 | — | **P6 주후보(최단순)** |
| pvalue×knnpd03 (구 "S0") | dev +0.0016 **ns** vs S1 | **−0.0112 SIG 손실** | +0.0081 SIG | vs S1 13:2·vs S4 9:0(순환) | **발굴 knob(ablation)** — 승자 아님 |
| cap_blend×rp3b (구 S3) | 하위 | — | 0.0994 | — | 발굴형 대안 |
| cap_blend×condcos (구 S4) | 하위 | — | 낮음 | — | 프로덕션 baseline(교체 대상) |
| random_support×* (null) | 0.11~0.13 | — | — | — | 바닥 분리 ✓ |

- **랭커 축(강건·FDR 통과)**: userknn ≫ condcos +0.0242(q=0.004) ≫ ppmi/jaccard/ease. RP3β도 condcos 상회. **이게 P4의 실측 산출.**
- **judge·SNIPS 주의**: 둘 다 인기축을 재므로 knnpd03에 by-construction 유리 — knnpd03의 "우위" 근거로 쓰면 순환(T32~T33). 독립 근거(wishlist)선 ns.
- **fresh-panel(n=586)**: coarse 순위(userknn계열≫condcos≫null)는 재현되나, S0 vs S1/S2 미세 우열은 CI 중첩(paired 미검) — "패널 과적합 없음"은 **레짐 수준**에서만 성립.

## 크롤 현황 (월 07:45)
- games **완주**(07-04 02:12, 28.8k→0) → 풀 38,435 확정(미타입 1,491=상장폐지류만).
- 유저 **2,614/10k**: 07-04 예산일 +436, 07-05 +509(가속 확인 — discovery 오버헤드 감소). **ETA ~15-18일**, allowlist 축소 시 단축. 오늘 09시 리셋 후 재개, +22명 도달 시 **fresh 2차 웨이브 검증 자동 실행**(트리거 배선됨).
- 크롤러 사망 2회(07-03 12:06, 07-06 ~02시 — 둘 다 원인미상 크래시, 워치독 즉시 복구, 손실 0).

## 이슈·에러 로그 (전부 저널 상세)
rtime Valve-미반환 확정(무작위 70/30 fallback) / 재현은 manifest 설정으로(교훈) / 크롤러 사망 2회 복구 / RUNSTATE 시각버그 교정 / 세션 rate-limit 정지 1회(6.5h — 자동 재개, 크롤 무중단; 이후 저부하 1h 체인 운용) / ALS seed 버그 1회 수정 / 소셜 F5 측정불가(간선 20).

## 잔여 위험 (구조적으로 못 본 곳 — 감사 후 갱신)
**① 정답지 순환(최상위 위험, T32~T33)**: 주 지표가 선호와 playtime 백분위를 공유(rho 0.957) — 모든 in-cohort 검증이 이 한계를 공유. **해소는 target-독립 신호(wishlist/구매 홀드아웃 또는 즐김-기반 judge)뿐** → P6_PREREG에 co-주지표로 추가함. · ② in-cohort 편향(레짐은 fresh 재현, 미세 우열은 P6 OOD) · ③ judge 단일모델·pop-정렬 기준(독립 근거 아님; Gemini 교차는 복귀 후) · ④ 미탐색: 학습형 리랭커(LambdaMART/GBM)·EASE 람다그리드·보정 fusion — knnpd03보다 나은 후보 가능성 잔존 · ⑤ 랭커 규모 의존성(10k서 EASE/ALS 재평가) · ⑥ long-tail ~0 상존.
