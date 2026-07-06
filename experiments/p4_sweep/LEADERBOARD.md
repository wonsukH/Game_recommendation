# P4 종합 리더보드 — 현재 리더 (2026-07-03~, **탐색 계속 중 — 동결 아님**)

> **유형**: experiment-report · **상태**: active · **갱신**: 2026-07-06 (적대적 감사 T32~T33 반영)

> ⚠️ **감사 교정(T32~T33, 아래 표보다 우선)**: 이 문서의 "S0(pvalue×knnpd03) 등극/전축 우위" 서술은 **과대포장으로 판명·하향**됨. 실측: ① 주 지표는 순환(per-game rho 0.957) ② S0 vs S1 — NDCG **ns**, recall **−0.0112 SIG 손실**, SNIPS만 +유의(순환) ③ target-독립(wishlist)선 **ns** ④ judge 적합/발굴 34/35 동일 = 1축, pop-discount와 동어반복. **실측 방어되는 결과 = 랭커: user-KNN ≫ condcos +0.0242(BH-q=0.004).** knnpd03은 발굴 knob(승자 아님). 상세 = `REPORT_MONDAY.md` 상단 + `JOURNAL.md` T32~T33. 아래 표는 감사 이전 프레이밍이라 그대로 신뢰 금지.

> Stage A(선호 진화 R0~R4, 46평가) → Stage B(랭커 11구성) → Stage C(소교차+패자부활전) → private 패널(150명) → **탐색 재개 후속**(MF 가족·wishlist 축·R5 조합·judge 가드레일·knnpd·masked-engagement·의도 ablation·informed-neg BPR).
> 전 평가의 per-user CSV·config = `rounds/`·`stageB/`·`stageC/`·`private_check/`·`mf_family/`·`judge/`·`intent0_ablation/` 등. 서사 = `JOURNAL.md` (T0~T22).

## 🏆 현재 리더 (사용자 확정 대기 — "동결" 아님, 탐색 계속)

| # | 구성 (선호 × 랭커) | NDCG@20 | SNIPS | judge | masked-ρ | 성격 |
|---|---|---|---|---|---|---|
| **S0** | **pvalue_eb × userknn25+popdiscount(β0.3)** | 0.2789(private; vs S1 차 −0.009 **ns**) | **0.0925**(vs S1 **+0.0158 SIG**) | **적합 9:0·발굴 11:1 vs S4** | **0.1045** | **NDCG 유의 손실 없음 + SNIPS·judge·masked 우위** — β=0.3 인기패널티가 메인스트림 쏠림 제거(지표-judge 분기 해소) |
| S1 | pvalue_lognorm_eb × user-KNN25 | 0.2943(private) | 0.0878 | 적합 4:7 **패** | 0.0771 | private 1위·패자부활전 부활자 — 단 judge에서 AAA 쏠림 노출 |
| S2 | pctl_game × user-KNN25 | 0.2925(private) | 0.0916 | — | — | 가장 단순·해석 용이 |
| S3 | cap_a03_blend04 × RP3β(0.6) | 0.2800(private) | **0.0994** | — | — | 발굴형(SNIPS 최고) — Pareto 비지배 |
| S4 | cap_a03_blend04 × condcos | 0.2667(private) | 0.0860 | 적합 7:4 승(vs S1)·**0:9 패(vs S0)** | 0.0686 | 프로덕션-호환(랭커 교체 없는 경우) |
| — | random_support × * (null) | 0.126~0.180 | — | — | −0.006 | 바닥 분리 ✓ (전 축 지표 건강) |

※ S0 private 1회 확인 완료(13:49, **패널 2번째 노출** — 사유: 리더 갱신에 따른 확인, 이후 private 재사용 금지). dev의 "NDCG 동률"은 private에서 "−0.009 ns"로 소폭 후퇴 — 과대포장 없이 기록. **최종 관문은 OOD(P6)**. judge는 n=12·단일 Sonnet(방향 신호; Gemini 교차는 복귀 후).

## 핵심 발견 연쇄 (서사는 JOURNAL, 여기는 요약)
1. **support(누가-뭘-플레이)가 그래프 신호의 등뼈** — 가중은 2차 (smoke01).
2. **완료율(업적)이 유일한 유효 그레이드 신호** (+0.0073 SIG; pt등급화 단독 무익).
3. **per-user 질량 캡 = condcos 최대 레버** (+0.0161 SIG) — condcos 전용(userknn은 내장).
4. **weighted-C 귀속**: 그레이드 이득 ~75%는 간선 가중 (R3·R4).
5. **랭커가 선호보다 큰 레버**: userknn > condcos +0.0242 SIG (Stage B).
6. **[신규] 지표-judge 분기와 해소**: NDCG는 보유-재현이라 인기 쏠림을 보상 — userknn이 지표 이기고 judge 지는 긴장 발견 → **pop^0.3 discount가 두 축을 동시에 잡음**(S0). 가드레일 설계 목적의 실증.
7. **[신규] 무거운 학습형 전패(측정으로 확정)**: ALS 0.267(MF 최강) < userknn; BPR 0.186·NMF-KL 0.219·EASE 0.21~0.22 — 1.7k 규모에서 "DL이 오래 걸려서 안 한 게 아니라 해봤더니 지더라"로 전환. 10k 재평가 잔류: ALS·EASE만.
8. **[신규] 음성결과 추가**: R5 승자조합 전멸(S1이 버팀) · 의도 ε-tier 기각(팩병합 38% 차단 후에도 무이득 — 기본 제외 실측 확정) · **informed-neg BPR −0.0514 SIG**(dropped는 '싫음'이 아니라 '취향인데 안 맞음' — 랜덤보다 강한 네거티브로 쓰면 해로움) · 앙상블 RRF 기각.
9. **[신규] 보조축 2종 배선**: wishlist(인기-null 대비 +35%, 리더 간 저해상도) · masked-engagement(S0 1위, null≈0 건강).

## ⚠️ 사용자 결정 필요 (복귀 시)
- **랭커**: S0(knnpd03)가 지표+질감 동시 석권 — condcos 유지 명분 크게 약화. 단 P5/P8 재배선 구조 영향 + private/OOD 미검증 리스크 병기.
- shortlist 최종 선정(S0~S4) — OOD(P6) 재실험 대상.
- 유저-크롤 업적 allowlist: 완료율만 유효 — 희귀도 크롤 스코프 재논의(rarity E가족 결과 나오면 함께).
- 학습형·의도·informed-neg 음성결과 3종 수용 확인.

## 잔여 위험 (구조적으로 못 본 곳)
- in-cohort dev/private 모두 같은 편향 코호트 — 최종 판정은 OOD(P6).
- S0는 dev에서만 검증(private·25k 재확인 미실시 — 복귀 전 실행 예정).
- judge n=12·단일 모델 — 방향 신호. Gemini 교차 대기.
- long-tail 슬라이스 ~0 문제 상존(rp3b만 non-zero).
