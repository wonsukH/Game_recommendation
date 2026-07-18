# Portfolio headlines — approved external framings

> type: portfolio · status: active · updated: 2026-07-17

Recruiter-facing copy for the recommender's results. **Policy (user-approved 2026-07-15): dual
notation** — every framing below is an arithmetic derivation of a recorded number in
[results](results.md) (the raw value rides along in parentheses); no post-hoc metric changes.
External materials avoid internal jargon (slot codes, candidate names, phase numbers) per the
portfolio rules. The Korean strings are the paste-ready copy.

## Headline set (Korean copy + derivation)

| # | 외부용 카피 (Korean) | Derivation / raw |
|---|---|---|
| 1 | **"블라인드 평가에서, 유저가 실제로 사랑하는 게임과 구별되지 않는 추천"** | judge High 50.0% vs own-loved-games ceiling 51.3% (overlapping CIs) |
| 2 | **"천장 정규화 정밀도 97%"** — 평가 도구의 상한(유저 본인 애호작 점수) 대비 | 50.0 / 51.3 |
| 3 | **"추천 10개 중 8개는 유저 취향에 닿음"** | High+Medium 82.0% (ceiling 80.2%) |
| 4 | **"무작위 대비 6.7배, 인기순 대비 +22%p — 순수 개인화 기여"** | 50.0% vs random 7.5% / POP 28.0% (v2 instrument) |
| 5 | **"한 번도 본 적 없는 미래 행동(위시리스트 추가)을 우연의 49배로 예측"** | 4.0% of future adds in top-20; chance 0.08% |
| 6 | **"유저 미래 위시리스트의 절반이 추천 랭킹 상위 2.3% 안"** | K@50% coverage = 933 of 40,863 |
| 7 | **"검증 끝에 살아남은 건 가장 단순한 모델 — 그리고 내 결론 2개가 틀렸음을 내 감사가 잡아냈다"** | EASE vs 15+ challengers incl. neural (all lost); cutoff-bug & knob headline reversals |
| 8 | **"무편향 1,000명 패널 사전등록 1회 확정 — 코호트 편향과 지표 순환을 모두 제거한 결론"** | P6 one-shot; H1 q≈0 both axes |

## Usage rules
- Always pair a framing with its raw derivation when space allows (footnote form is fine).
- #2 and the ~90%+ corrected estimate are **instrument-relative** claims — keep the "평가 도구
  상한 대비" qualifier attached; never present them as raw human-satisfaction rates.
- The honest-negative story (#7) is a differentiator, not an apology — lead with it in interviews.
- Do not use: raw judge percentages without the ceiling, K_for_100% coverage (worst-target
  artifact), deep-tail (K ≥ 10k) comparisons (artifact zone).

## Cross-links
Canonical numbers: [results](results.md) · method: [evaluation](evaluation.md) · evidence:
`experiments/p4_sweep/JOURNAL.md` T43–T52.
