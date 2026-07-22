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

## Live demo evidence (2026-07-22 — consented accounts, IDs withheld)
Real libraries → live EASE recommendations. 5 accounts: the author + 4 friends **with explicit
consent to publish** (one friend's library was private → excluded). No SteamIDs in this document.
Profiles sorted by the engine's actual signal (per-game playtime percentile), not raw hours.

| 계정 | 취향 (가중치 상위) | 추천 top-5 |
|---|---|---|
| 본인 | SANABI(1.00) · ENDER LILIES(.97) · **Eternal Return 844h(.96 — 백분위가 온라인게임 인플레를 흡수)** · Core Keeper · NieR:Automata | Hades · Don't Starve Together · Slay the Spire · Cuphead · DELTARUNE |
| 친구 1 | Limbus Company 718h(.93) · Skul(.83) · SANABI(.76) · L4D2 | Terraria · Don't Starve Together · R6 Siege · Portal 2 · Buckshot Roulette |
| 친구 3 | Eternal Return(.89) · Party Animals(.87) · Palworld(.85) · R6 Siege 296h(.81) | Monster Hunter: World · Apex · Terraria · Stardew Valley · Marvel Rivals |
| 친구 4 | Eternal Return 306h(.95) · Skul(.91) · Warframe(.82) · Subnautica(.80) | PUBG · Destiny 2 · Slay the Spire · Risk of Rain 2 · **Subnautica: Below Zero(속편 인지)** |

- **본인 자기평정(블라인드 아님)**: top-10 중 관심 7 · 모름 1 · 비선호 2 — LLM 심사 계기의 예측
  (관대 82%)과 정합.
- **실사용 피드백 → 당일 개선 사례**: "이터널 리턴 같은 거 → 유희왕?"(대중적 시드에서 co-play
  유사가 인구 차트로 퇴화) → 태그-유사도 게이트 추가 → 유희왕·리듬게임 탈락, **Black Survival
  (ER의 직계 전신)·SMITE(MOBA)** 진입.
- 정직 각주: 크롤 수집 사용자의 라이브러리는 익명화해도 재식별 위험이 있어 **게시하지 않음**(동의
  계정만 게시); 초저플레이 소품 게임의 백분위 노이즈(예: 무료 데모작 고가중치)는 알려진 한계.

## Cross-links
Canonical numbers: [results](results.md) · method: [evaluation](evaluation.md) · evidence:
`experiments/p4_sweep/JOURNAL.md` T43–T58.
