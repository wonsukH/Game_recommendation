# 문서 스타일 가이드 (STYLEGUIDE)

> **유형**: design-spec · **상태**: active · **갱신**: 2026-06-29

> 이 레포의 모든 문서가 **목적(유형)별로 일관된 서식**을 갖도록 하는 정본 규칙이다. 핵심 원칙: **본문 내용·수치·문장은 절대 바꾸지 않는다(요약 금지). 서식·구조·분할만 표준화한다.** 새 문서를 쓰거나 기존 문서를 정리할 때 이 가이드를 따른다.

## 1. 메타블록 (모든 문서 공통 헤더)

모든 문서는 `# H1` 제목 **바로 아래**에 blockquote 한 줄의 메타블록을 둔다:

```
# <제목>

> **유형**: <type> · **상태**: active | deprecated | frozen · **갱신**: YYYY-MM-DD
```

- **상태 = deprecated/frozen**이면 메타블록 **다음 줄**에 표준 폐기 배너를 둔다:
  ```
  > ⚠️ **[폐기·이력]** <한 줄 사유>. 정본: [`../README.md`](../README.md) · [`ROADMAP.md`](ROADMAP.md).
  ```
- **roadmap** 유형은 메타블록에 브랜치/origin을 덧붙인다:
  `> **유형**: roadmap · **상태**: active · **갱신**: YYYY-MM-DD · **브랜치**: \`feat/…\` · origin = github.com/…`
- **experiment-report** 유형은 `· **run**: \`<run_id>\``를 덧붙인다.

`상태` 정의: `active`(현행) · `deprecated`(피벗 이전 기록, 정본 아님) · `frozen`(생성기 삭제 등으로 동결되어 수기로만 갱신).

## 2. 공통 서식 규칙

- **헤더**: `##`=섹션, `###`=하위섹션. `**볼드**`나 ALLCAPS를 헤더 대용으로 쓰지 않는다. 깊이는 실제 내용 중첩을 반영한다.
- **날짜**: ISO `YYYY-MM-DD`. (단, 실행 디렉터리 이름의 `YYYYMMDD_HHMMSS` 타임스탬프는 그대로 둔다.)
- **링크**: 파일 참조는 상대 markdown 링크 `[`경로`](경로)`. `[[wiki-link]]`는 **메모리 상호참조 전용**(예: `[[confirm-before-code-change]]`).
- **언어**: 한국어 본문 + 코드·CLI·식별자·지표명은 영어(기존 컨벤션 유지).
- **blockquote `>`**: 메타블록·폐기 배너·문서당 1개의 TL;DR 콜아웃에만 사용한다. 일반 강조용으로 남발하지 않는다.
- **리포트 결론**: `## 결정` 섹션 또는 마지막 `**결정(decision)**: …` 한 줄로 통일한다.

## 3. 유형(type) 어휘와 템플릿

| 유형 | 무엇 | 대표 파일 |
|---|---|---|
| `behavior-rules` | 작업 규칙 | `../CLAUDE.md` |
| `overview` | 프로젝트 개요 | `README.md` |
| `roadmap` | 현황·핸드오프(리셋 진입점) | `docs/ROADMAP.md` |
| `design-spec` | 설계 의도·스펙 | `docs/INTENT.md`, `docs/README_PIPELINE.md`, 이 문서 |
| `bug-log` | 진단된 이슈 기록 | `docs/issues/*` |
| `runbook` | 운영 how-to | `docs/runbook_pool_expansion.md` |
| `index` | 네비게이션·카탈로그 | `experiments/INDEX.md`, `experiments/README.md` |
| `reasoning-log` | append-only 고민 서사 | `experiments/DELIBERATION_LOG.md` |
| `experiment-report` | 실행별 결과 리포트(자동생성) | `experiments/<run>/report.md` |
| `metric-report` | 지표 신뢰성 검증 | `metric_trust_report.md` |
| `eval-output` | 평가 산출물 | `outputs/*.md` |
| `portfolio` | 채용·발표용 | `docs/portfolio/*` |
| `html-reference` | HTML 참고자료 | `docs/technical_reference.html` |

**experiment-report 골격**(생성기가 `RunLogger.standard_report`로 생성):
```
# <run_id> — <한 줄 요지>

> **유형**: experiment-report · **상태**: active · **run**: `<run_id>` · **갱신**: YYYY-MM-DD

<설정 1–2줄: n, k, 방법>

## 결과
<표>

## 결정
**결정(decision)**: …
```

## 4. 모듈화(분할) — 요약 금지, 코드처럼 분할

문서가 **~300줄**을 넘으면 **요약하지 말고** 기존 섹션 경계를 따라 여러 모듈로 **분할**한다. 분할 결과의 합집합은 원문과 **글자 단위로 동일**해야 한다(verbatim 이전, 삭제·요약 0).

- **허브-스포크**: 원본 파일은 **짧은 인덱스(허브)** 로 바꿔 각 자식을 "1줄 라벨 + 링크"로 나열한다(라벨은 원문 축약이 아니라 네비게이션 제목). 본문은 형제 폴더의 자식 파일로 옮긴다. 원본 경로는 허브로 유지해 링크 깨짐을 막는다.
- **자명한 제목/파일명**: 자식 파일은 H1·파일명만으로 무엇을 설명하는지 즉시 이해되게 한다. 파일명 = `NN-주제-kebab.md`. 예: `issue-04-weighted-ppmi-matrix.md`.
- 각 자식도 §1 메타블록 + `> 상위: [<허브>](./README.md)` 한 줄을 갖는다.
- 자동생성 `report.md`는 본래 짧으므로 분할 대상이 아니다(생성기가 짧게 유지).

분할 매핑(현행):

| 원본(→허브) | 자식 | 입도 |
|---|---|---|
| `docs/ISSUES.md` | `docs/issues/issue-NN-*.md` | 이슈 1개당 1파일 |
| `docs/INTENT.md` | `docs/intent/NN-*.md` | 번호 섹션별 |
| `docs/README_PIPELINE.md` | `docs/pipeline/NN-*.md` | 파이프라인 스테이지별 |
| `experiments/DELIBERATION_LOG.md` | `experiments/deliberation/NN-*.md` + 인덱스 | 닫힌 Phase는 아카이브로 이전, 라이브 tail만 원본에 유지 |

## 5. 처리 클래스 (서식을 "어디서" 고치나)

| 클래스 | 대상 | 규칙 |
|---|---|---|
| **수기** | 직접 쓰는 문서 전부 | 파일을 직접 reformat |
| **자동생성** | `experiments/<run>/report.md`, `outputs/ablation_summary.md`·`true_hallucination.md`, `metric_trust_report.md` | **생성기 코드의 템플릿을 고친다**(파일을 손으로 고치면 재실행 시 되돌아감). 기존 산출물은 새 템플릿에 맞춰 수기 정규화. |
| **append-only** | `experiments/DELIBERATION_LOG.md`, `registry.jsonl` | 과거 항목 in-place 수정 금지. 메타블록·앞으로의 엔트리 헤더만 통일. 자동 append는 `RunLogger.append_deliberation` 공용 헬퍼로. |
| **동결** | `outputs/llm_vs_system*.md` (생성기 삭제됨) | 수기로만 정규화(표·수치 verbatim). |
| **제외(손대지 않음)** | 메모리 `~/.claude/.../memory/*.md`(고정 YAML 스키마, system 관리), `aggregate.json`/`per_query.csv`/`manifest.json`/`registry.jsonl`(데이터), `.claude/*` | 서식 정리 대상 아님 |

## 6. 검사 (강제)

`scripts/check_doc_format.py`(읽기전용)가 추적 문서별로 (a) H1 존재, (b) 메타블록의 유형/상태/갱신 유효, (c) deprecated/frozen이면 표준 배너+정본 링크, (d) ISO 날짜, (e) 볼드-헤더 없음을 검사하고 위반 시 비0으로 종료한다. 경로↔유형은 스크립트 내 `DOC_TYPES`로 관리한다.

내용 보존은 `scripts/check_doc_content_preserved.py`로 검증한다(정규화: 토큰 제거 후 본문 해시 전/후 동일; 분할: 자식 본문 concat = 원문).

## 7. 내용 보존 원칙 (최우선)

서식 작업의 어떤 단계에서도 **본문 텍스트·숫자·문장을 바꾸거나 줄이지 않는다.** 길면 분할하고, 낡았으면 `상태: deprecated` + 배너로 표시하되 내용은 보존한다. 삭제·요약이 필요해 보이면 먼저 사용자에게 확인한다([[confirm-before-code-change]]).
