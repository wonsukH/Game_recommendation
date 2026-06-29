# 문서 위키 — 홈 (Doc Wiki Home)

> **유형**: index · **상태**: active · **갱신**: 2026-06-29

> 이 레포 문서의 **진입점**. LLM이든 사람이든 여기서 출발한다. **현행(정본)부터** 보고, 폐기 문서는 이력으로만 참고한다. 서식·위키 규칙은 [STYLEGUIDE.md](STYLEGUIDE.md).

## 현행 정본 (active)

| 문서 | 무엇 | 언제 보나 |
|---|---|---|
| [../README.md](../README.md) | 프로젝트 개요·실행 | "이게 뭐 하는 프로젝트?" |
| [ROADMAP.md](ROADMAP.md) | 현황·핸드오프(리셋 진입점)·로드맵 P4~P9 | "지금 상태/다음 할 일/크롤?" |
| [STYLEGUIDE.md](STYLEGUIDE.md) | 문서 서식 + 이 위키의 규칙 | "문서 어떻게 쓰고 정리하나?" |
| [../experiments/INDEX.md](../experiments/INDEX.md) | 모든 실험 비교·질문·핵심결과·아티팩트 카탈로그 | "X 실험 결과/수치?" |
| [../experiments/DELIBERATION_LOG.md](../experiments/DELIBERATION_LOG.md) | 고민·결정의 서사 (append-only) | "왜 이렇게 결정/방향전환?" |
| [../experiments/README.md](../experiments/README.md) | experiments 폴더 구조 안내 | "실험 폴더 어디에 뭐가?" |

## 폐기·이력 (deprecated — 피벗 이전, 정본 아님)

각 허브는 짧은 인덱스이고 본문은 자식 폴더에 모듈로 분할되어 있다. **현행으로 인용하지 말 것.**

| 허브 | 무엇 | 자식 모듈 |
|---|---|---|
| [INTENT.md](INTENT.md) | 옛 설계 의도(태그유사도 스택) | [intent/](intent/) |
| [README_PIPELINE.md](README_PIPELINE.md) | 옛 파이프라인 스펙 | [pipeline/](pipeline/) |
| [ISSUES.md](ISSUES.md) | 옛 파이프라인 디버깅 기록(이슈 16건) | [issues/](issues/) |
| [runbook_pool_expansion.md](runbook_pool_expansion.md) | 옛 게임풀 1031→10K 확장 런북 | — |

## 질문 → 어디 보나 (retrieval hints)

- **현황 / 크롤 / 다음 할 일** → [ROADMAP.md](ROADMAP.md)
- **실험 결과·수치** (CF vs LLM, ranker, steering, scaling 등) → [../experiments/INDEX.md](../experiments/INDEX.md) → 해당 run의 `report.md`
- **왜 그렇게 결정/방향 전환했나** → [../experiments/DELIBERATION_LOG.md](../experiments/DELIBERATION_LOG.md)
- **추천이 실제로 어떻게 도나(코드)** → [../README.md](../README.md) + `pipeline/game_rec/agent/cf_recommender.py`·`content.py`
- **포트폴리오(채용용)** → `docs/portfolio/` (로컬 전용, gitignored)

> 폐기 문서를 현행으로 인용하지 말 것 — 각 문서 메타블록의 `상태`(`active` vs `deprecated`/`frozen`)로 구분하고, 폐기 문서엔 `정본:` 링크가 달려 있다.
