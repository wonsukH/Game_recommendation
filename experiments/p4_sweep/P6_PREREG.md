# P6 OOD 재실험 — 사전등록 프로토콜 (v1, 2026-07-06 자율운행 중 작성)

> **유형**: pre-registration · **상태**: draft(사용자 승인 대기) · **작성 시점 고정**: 이 문서는 OOD 데이터를 보기 **전에** 등록한다. 등록 후 수정은 append-only(수정 이력 명시)로만.

## 목적
P4 shortlisting은 편향 코호트(리뷰어-스노볼)에서의 잠정 순위다. P6는 **de-biased 패널에서 리더 구성을 재실험**해 최종 확정한다 — winner's curse의 confirmation 단계. fresh-panel(T29, n=586)이 준-OOD 신호를 이미 줬지만 스노볼-연결이라 완전 독립이 아니다.

## 사전등록 가설 (감사 T32~T33로 재작성 — v2)
- **H1(주가설, 강건 결과 확인)**: user-KNN(및 RP3β) 랭커가 OOD 패널에서 프로덕션 condcos를 **주지표 A에서 유의 격파**한다(in-cohort +0.0242, BH-q=0.004). → 성립 시 P5에서 랭커 교체 확정.
- **H2(선호)**: pvalue와 pctl_game은 주지표 A에서 **구별 불가**하다(귀무 유지 예상). 어느 하나가 target-독립 지표 B에서 유의하면 그것을 선호로 채택, 아니면 **최단순 pctl_game**.
- **H3(knnpd03 knob)**: knnpd03이 순정 userknn 대비 **target-독립 지표 B(wishlist)에서 유의**하면 발굴 knob으로 채택, 아니면 기각(현 in-cohort ns). *지표 A/SNIPS/judge는 순환이라 이 판정에서 제외.*
- **반증 조건**: H1 붕괴(랭커 교체 근거 상실) → condcos 유지. H3의 지표 B ns 지속 → knnpd03 폐기, 순정 userknn 확정.

## 평가 구성 (고정 — 사후 추가 금지)
| 슬롯 | 구성 |
|---|---|
| S0a / S0b | pvalue_eb × userknn25+popdiscount **β=0.2 / β=0.3** (그리드는 이 2점뿐 — fresh 1회 관측 기반, 추가 탐색 금지) |
| S1 | pvalue_eb × userknn25 |
| S2 | pctl_game × userknn25 (최단순 대조) |
| S3 | cap_a03_blend04 × rp3b (발굴형) |
| S4 | cap_a03_blend04 × condcos (프로덕션 호환) |
| null | random_support × userknn25 (지표 건강) |

## 패널 설계
- **소스**: 랜덤 accountID 프로브(SteamID64 = 76561197960265728 + U[0, ~1.6e9] 균등 샘플) → 공개 프로필 + 라이브러리 12+게임 필터. 스노볼 링크 무관 = 코호트 독립.
- **크기**: 최소 300명(CI 폭 fresh-panel 수준), 목표 500.
- **그래프**: 기존 train 1,133 고정(순수 일반화) **및** OOD-혼합 그래프(절반 편입) 2셋 — 후자는 "데이터가 저럴 때 배포하면"의 근사.
- **1회성**: 이 패널은 확정 판정에 1회만 사용. 반복 조회 금지.

## 지표 (감사 T32~T33로 보강 — v2)
> **감사 교정**: v1은 graded NDCG(=build_relevance)를 단일 주지표로 뒀으나, 그 타깃은 선호와 playtime 백분위를 공유(per-game rho 0.957)해 **순환**. in-cohort NDCG/SNIPS/masked/judge가 전부 이 타깃을 재사용하므로 순환을 반박 못함. → **target-독립 co-주지표를 추가하고, knnpd03·선호 우열은 이것으로만 판정**한다.
- **co-주지표 A (순환 축, 유지)**: graded NDCG@20 — playtime-백분위 정답. paired bootstrap CI.
- **co-주지표 B (target-독립, 신규·knnpd03 판정 기준)**: **held-out wishlist recall@20** (컷오프 T 이후 추가된 미보유 wishlist를 카탈로그 랭킹에서 발굴 — playtime provenance 없음). 시간분할로 누수 차단(입력=T 이전 owned, 정답=T 이후 wishlist). paired bootstrap S0-vs-S1, S0-vs-S2.
  - *현 in-cohort 예비값(dev, T33)*: S0−S1 = +0.0056 [−0.0002,+0.0124] **ns** → OOD에서 유의 전환해야 knnpd03 채택.
- **보조**: SNIPS recall(클립 10)·recall@20·null 분리. **단 SNIPS·judge-discovery는 pop-debias 축이라 knnpd03에 by-construction 유리 → knnpd03 판정의 독립 근거로 쓰지 않음**(확인용만).
- **다중비교**: 헤드라인 페어에 BH-FDR 적용(T33에서 하니스 audit_fdr.py 확립).

## judge 교차검증 (질감 축)
- Sonnet blinded 쌍대(기존 프로토콜: grounded 카드, A/B 랜덤화, fit/discovery) n≥16 + **Gemini(flash급) 동일 페이로드 독립 실행** → 모델 간 일치도(cohen's κ) 보고. 페이로드 생성기는 `judge_payload.py`(JUDGE_VARIANT 확장)로 재사용.
- judge는 보조 축: 주축 판정을 뒤집지 않고, S0-계열 내 동률(β 0.2 vs 0.3 등) 타이브레이커로만.

## 실행 비용 추정
랜덤 프로브 히트율(공개+12게임) ~5-10% 가정 시 500명 확보 ≈ 5k~10k 프로브 콜 + 심층 ~170콜/명 ≈ 90~100k콜(약 하루 예산). allowlist 축소 채택 시 대폭 감소.

## 사용자 결정 필요(실행 전)
① 이 프로토콜 승인/수정 ② 예산 배분(유저 적립 vs OOD 프로브 — 하루치 경합) ③ allowlist 축소와의 순서.
