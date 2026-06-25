# experiments/ — 구조 안내 (목적별 정리)

> 위치 주의: 이 폴더는 **프로젝트 최상위 `experiments/`** 다. (예전엔 `outputs/experiments/`에 있었으나, `outputs/`는 build_offline로 재생성되는 *파이프라인 산출물*용이자 `.gitignore` 대상이라, 재생성 불가능한 *연구 증거*인 실험을 그 안에 두는 건 부적절 → 최상위로 분리. 코드의 출력 경로도 `REPO_ROOT/experiments`로 갱신됨.)

이 폴더는 "이 추천 시스템의 구성이 의미 있는가"를 검증한 모든 실험의 **증거(artifact)** 모음이다.
목적별 하위폴더로 정리했고, 최상위에는 전체를 잇는 **마스터 문서 3종**을 둔다.

## 최상위 (마스터)
| 파일 | 용도 |
|---|---|
| `INDEX.md` | 모든 실험의 카탈로그(질문·결과·파일) — 여기서 시작 |
| `registry.jsonl` | 머신리더블 run 레지스트리(append-only, 한 줄 = 한 run) |
| `DELIBERATION_LOG.md` | 고민·문제해결 *과정*의 서사(왜·무엇을·반박·전환) |

## 목적별 하위폴더 (논리적 순서)
| 폴더 | 무엇을 검증 | 핵심 결과 | 대표 파일 |
|---|---|---|---|
| `01_similar_eval/` | similar(게임으로 검색): SVD vs 태그-cosine, masked-tag 일반화 | SVD가 유의하게 나쁨(p=1.5e-17); SVD 일반화 10–14×chance이나 modest | `phase1_final/report.md`, `phase1_final/metric_trust_report.md`, `masked_tag_report.md` |
| `02_vibe_walign/` | vibe(자연어 검색): W_align vs 수정안 Ve vs 태그-cosine (blinded judge) | Ve(Gemini-NN) 최선, W_align 꼴찌(전부 유의) | `vibe_judge_report.md` |
| `03_decisive_tags_vs_llm/` | 태그 경유 vs LLM-설명문 임베딩 직결 | 태그(vote합의)가 설명문보다 나음(Ve−Vf=+0.60 유의) | `decisive_report.md` |
| `04_paradigm_vs_llm/` | 시스템 vs 생성형 LLM (best-fit & 공정 발굴) | 시스템 승률 0.04 — LLM이 ~96% 승(발굴 프레이밍서도) | `paradigm_report.md`, `gem_report.md` |
| `05_personalization/` | **개인화 CF vs "LLM+내 라이브러리" (hold-out)** | **CF가 유의하게 승(recall@20 0.293 vs 0.173) — 첫 승리 영역** | `personalization_report.html`, `personalization_full/report.md` |
| `_workflow_scripts/` | Claude 서브에이전트 심판에 쓴 임시 워크플로우 JS | (참고용, 재실행 불필요) | `_*.js` |

## 한 줄 결론의 흐름
원래 시스템은 모든 익명 추천 프레이밍에서 LLM에 ~96% 패배(01–04) → **단, 개인 라이브러리 기반 개인화(05)에서 처음으로 LLM을 유의하게 이김** → 의미 있는 재설계 방향 = 개인화.

## 재현 / 주의
- 각 run 디렉터리(`phase1_full/`, `personalization_full/` 등)는 `report.md`+`manifest.json`(아티팩트 sha256 지문)+`per_query.csv`+`aggregate.json`로 자기완결적.
- **주의:** *완료된 judge 체인 스크립트*(vibe/decisive/paradigm/gem)는 중간파일을 `EXP`(=`experiments/`) 루트에서 읽지만, 정리 후 그 파일들은 하위폴더(`02_vibe_walign/` 등)에 있다 → **그대로 재실행하면 경로가 안 맞는다**. 이미 끝난 증거라 무방하며, 재실행이 필요하면 입력 경로를 해당 하위폴더로 갱신하면 된다. (keeper 스크립트 `personalization_experiment.py`/`experiment.py`/`masked_tag.py`는 옮겨진 중간파일을 읽지 않으므로 정상 동작 — 새 run 디렉터리를 `experiments/` 루트에 생성.)
- 생성 코드 위치: 평가 라이브러리 `pipeline/game_rec/evaluation/`, 실험 드라이버 `pipeline/orchestration/`. (코드 자체의 목적별 그룹화는 다음 "재설계" 단계에서 함께 정리 예정.)
