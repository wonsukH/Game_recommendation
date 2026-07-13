# 7. 다음 방향 (이번 plan 범위 밖)

> **유형**: design-spec · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [INTENT.md](../INTENT.md) · 정본: [README.md](../../README.md) · [ROADMAP.md](../ROADMAP.md)


## 더 풍부한 데이터

- 게임 설명 텍스트 (`steam_appdetails.csv`의 description) — M9.A에서 시도했지만 단순 추가는 효과 X. mainstream-위주 sampling 또는 다른 활용 방법 필요
- 유저 리뷰 텍스트 (steam_reviews.csv) — 이미 있음, 미사용

## user_reviews 페이지네이션 fix

user당 전체 리뷰 수집 → sentence 길어짐 → Item2Vec 재활성 시도 가능 (현재는 noise라 OFF).

## 시스템 가치 강화

- **FastAPI 백엔드 분리** — Streamlit은 prototype, production은 API
- **Session memory** — 익명 session 기반으로 추천 history 학습
- **A/B test infra** — 두 시스템을 사이드바 토글로 비교 가능하게

---
