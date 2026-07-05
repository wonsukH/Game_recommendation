# P6 OOD 재실험 — 사전등록 프로토콜 (v1, 2026-07-06 자율운행 중 작성)

> **유형**: pre-registration · **상태**: draft(사용자 승인 대기) · **작성 시점 고정**: 이 문서는 OOD 데이터를 보기 **전에** 등록한다. 등록 후 수정은 append-only(수정 이력 명시)로만.

## 목적
P4 shortlisting은 편향 코호트(리뷰어-스노볼)에서의 잠정 순위다. P6는 **de-biased 패널에서 리더 구성을 재실험**해 최종 확정한다 — winner's curse의 confirmation 단계. fresh-panel(T29, n=586)이 준-OOD 신호를 이미 줬지만 스노볼-연결이라 완전 독립이 아니다.

## 사전등록 가설
- H1(주가설): S0(pvalue×knnpd03)는 OOD 패널에서 S4(프로덕션 condcos) 대비 **주축 비열등 + SNIPS 유의 우위**를 유지한다.
- H2: 리더 순위 구조(knn계열 > rp3b ≈ condcos > null)가 OOD에서 재현된다.
- H3(knob): β∈{0.2, 0.3} 고원이 OOD에서도 성립하고 β=0.4 절벽이 재현된다.
- 반증 조건 명시: S0의 NDCG가 S4 대비 유의 열세거나 null과의 분리가 붕괴하면 **S0 기각**(대안: S2 최단순 또는 S4 호환).

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

## 지표 (P4와 동일 — 변경 금지)
graded NDCG@20(주축, per-game engagement 백분위+완주 보정) / SNIPS recall(클립 10) / recall@20 / null 분리 확인. paired bootstrap CI 병기.

## judge 교차검증 (질감 축)
- Sonnet blinded 쌍대(기존 프로토콜: grounded 카드, A/B 랜덤화, fit/discovery) n≥16 + **Gemini(flash급) 동일 페이로드 독립 실행** → 모델 간 일치도(cohen's κ) 보고. 페이로드 생성기는 `judge_payload.py`(JUDGE_VARIANT 확장)로 재사용.
- judge는 보조 축: 주축 판정을 뒤집지 않고, S0-계열 내 동률(β 0.2 vs 0.3 등) 타이브레이커로만.

## 실행 비용 추정
랜덤 프로브 히트율(공개+12게임) ~5-10% 가정 시 500명 확보 ≈ 5k~10k 프로브 콜 + 심층 ~170콜/명 ≈ 90~100k콜(약 하루 예산). allowlist 축소 채택 시 대폭 감소.

## 사용자 결정 필요(실행 전)
① 이 프로토콜 승인/수정 ② 예산 배분(유저 적립 vs OOD 프로브 — 하루치 경합) ③ allowlist 축소와의 순서.
