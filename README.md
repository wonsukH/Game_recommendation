# Steam Game Recommendation Agent

YBIGTA 27기 신입기수 팀 프로젝트로 만든 시스템을, 마치고 나서 다시 들여다보니 production 관점에서 부족한 부분들이 눈에 띄어 차근차근 다시 정리하고 키워나가는 레포.

원본 팀 작업은 `27th-project-game/`에 그대로 보존되어 있고, 본 레포는 그 시점의 clone에서 출발해 점진적으로 손을 본 흔적이 `git log`에 그대로 남는다.

---

## 무엇이 부족했나

팀 작업 직후 코드를 다시 읽으며 정리해본 약점들:

- `tmp/` 폴더에 미채택 v0 파이프라인(step10-15)이 그대로 살아있고, 어느 게 현역인지 표시되어 있지 않음
- 동일 로직의 `user_game_scores_penalty.py`가 `Crawling/`과 `FE/` 양쪽에 중복
- 9개 step 스크립트가 같은 I/O 코드(`index_maps.json` 로드, stats 저장 등)를 각자 들고 있음
- 하이퍼파라미터(γ, κ, α, η, λ, embedding_dim, text_model)가 argparse 디폴트로만 흩어져 있어 single source of truth 없음. 실제로 `params_v1.json`이 stale해진 채로 방치되어 있었음
- 프롬프트 few-shot이 Python triple-quoted string에 박혀있어 수정 diff가 코드 변경처럼 보임
- `st_app/app.py`가 215줄에 LangGraph 빌드 + Streamlit UI + 이벤트 핸들링을 다 가지고 있음
- 4개 파일에 bare `except:` (KeyboardInterrupt까지 삼킴)
- `outputs/`와 `st_app/data/` 사이 수동 sync (이미 어긋난 상태였음)
- 사용 안 하는 `EDA/visualize_review_length.py`, `FE/preprocessing.py`가 존재하지 않는 `database/` 폴더를 참조하며 남아있음

---

## 지금까지 정리한 것

`git log --oneline` 기준 8개 커밋:

- `chore: archive unused experiments and remove dead code` — `tmp/`를 `archive/`로 이동하고 안의 v0 파이프라인이 왜 LangGraph로 대체됐는지 설명 추가, 죽은 파일 3개 삭제
- `refactor: deduplicate user_game_scores_penalty` — CLI 버전으로 통일
- `refactor: extract shared I/O utilities into utils module` — `utils/io.py`로 흡수 + `pyproject.toml`로 editable install 가능하게
- `refactor: externalize hyperparameters into config/default.yaml` — 하이퍼파라미터 단일화, argparse는 override만 담당
- `refactor: externalize LLM prompts into prompts/ directory` — 프롬프트 외부화 + `utils/prompts.load_prompt()`
- `refactor: split monolithic app.py into graph + ui + app` — `graph.py`(LangGraph 빌드) / `ui.py`(Streamlit 렌더) / `app.py`(50줄 진입점)
- `feat: add structured logging and fix bare except blocks` — `utils/logging.get_logger()` 도입, bare except narrowing, retriever/parser/normalizer 마이그레이션
- `chore: add data sync script and rewrite README for personal research` — `scripts/sync_data.py` (whitelist 기반 자동 동기화) + README 정리

---

## 다음에 손볼 것

### Agent 가치 평가 인프라

LangGraph 멀티노드 구조가 단발 호출 대비 실제로 가치 있는지 측정해보고 싶다.

- 30-50개 정도 테스트 쿼리 (similar/vibe/hybrid + edge cases)
- 베이스라인 3종: 단발 LLM / 단순 1턴 RAG / 현재 풀 시스템
- 평가: LLM-as-judge + manual blind 채점 + 응답 시간 / 토큰 비용
- 어떤 쿼리 유형에서 멀티노드가 의미 있었는지 실패 분석

### Agent 기능 확장

- Steam Web API 라이브 호출 노드 (가격, 할인, 동시접속자)
- 멀티턴 메모리 ("그거 말고 더 가벼운 거" 같은 후속 질문 처리)
- Self-reflection 루프 (응답을 다시 평가해서 어긋나면 재검색)
- `novelty_score` 실제 구현 (현재 0.5 placeholder)

### 게임 데이터 활용

이미 수집한 리뷰 / 태그 데이터로 만들 수 있는 다른 응용:

- 부정 리뷰 클러스터링으로 개선 액션아이템 추출
- 태그 조합 기반 게임 컨셉 브레인스토밍
- 메타데이터 → Steam 페이지 카피 생성

### 인프라

- FastAPI 백엔드 분리
- 데이터 자산 DVC 또는 외부 스토리지 이동
- 평가 결과를 CI에서 자동 비교

---

## 자산

팀 baseline에서 만든 것 그대로 사용:

| 자산 | 형상 |
|---|---|
| `game_vecs.npy` | (1031, 128), 단위벡터 |
| `tag_vecs.npy` | (393, 128), PPMI + Truncated SVD |
| `tag_beta.npy` | (393,), Ridge 회귀 |
| `W_align.npy` | (4096, 128), Upstage Solar 임베딩 → 태그 공간 사상 |
| `faiss_index.faiss` | IndexFlatL2 |

상세한 학습 과정은 워크스페이스 루트의 `PROJECT_HISTORY.md` 참조.

---

## 아키텍처

```
사용자 쿼리
    |
[parser_node]        LLM이 mode/games/phrases/tags JSON으로 파싱
    |
[normalizer_node]    Bigram Jaccard로 게임명 캐노니컬화
    |
[route_by_mode]      similar / vibe / hybrid / general 분기
    |
    +-- similar_node    FAISS 유사 게임 검색
    +-- vibe_node       태그 expand + 임베딩 합성 + FAISS
    +-- hybrid_node     similar + vibe 가중 결합
    +-- general_node    -> END
    |
[rerank_node]        tag_match x novelty 가중치 (사이드바 슬라이더)
    |
[response_generator] LangChain LLM으로 한국어 자연어 응답
    |
   END
```

---

## 실행

### 환경

```powershell
.venv\Scripts\Activate.ps1
pip install -e .
# .env 또는 환경변수에 UPSTAGE_API_KEY
```

### 데이터 동기화 (outputs/ -> st_app/data/)

```powershell
python scripts/sync_data.py
python scripts/sync_data.py --dry-run   # 변경 미리보기
```

### 오프라인 파이프라인 (재학습 시)

각 step 디폴트는 `config/default.yaml`. CLI 인자로 override 가능.

```powershell
python FE/step1.py
python FE/step2.py
python FE/step3.py
python FE/step4.py
python FE/step5.py
python FE/step6.py
python FE/step7.py
python FE/step8.py --version v2 --backup
python FE/step9.py
python FE/create_faiss_index.py
python scripts/sync_data.py
```

### Streamlit 챗봇

```powershell
streamlit run st_app/app.py
```

---

## 디렉토리

```
Game_recommendation/
  config/                   하이퍼파라미터 single source of truth
    default.yaml
  prompts/                  LLM 프롬프트 외부화
    parser.txt
    response_generator.txt
  utils/                    공유 유틸
    io.py
    config.py
    prompts.py
    logging.py
  scripts/
    sync_data.py            outputs/ <-> st_app/data/ 자동 동기화
  Crawling/                 Steam / Metacritic 크롤러
  EDA/                      탐색적 분석 + 시각화
  FE/                       오프라인 임베딩 파이프라인 (step1-9 + faiss)
  outputs/                  파이프라인 산출물
  st_app/                   Streamlit + LangGraph
    app.py                  50줄 진입점
    graph.py                LangGraph 빌더
    ui.py                   Streamlit 렌더링
    data/                   앱이 읽는 산출물 사본
    rag/
      retriever.py
      nodes/
  archive/                  미채택 v0 온라인 파이프라인 보존
  pyproject.toml
```

---

## 알려진 제약사항

- 회귀 R² = 0.3877. `step9`가 자동으로 "Poor fit" 판정. 태그 효과는 보조 신호고 주 임베딩 합성은 PPMI+SVD 기반이지만, 그 가정 자체가 옳은지는 Agent 평가 인프라 갖춘 뒤 ablation으로 검증 예정.
- `novelty_score`는 현재 0.5 고정 placeholder. UI 슬라이더는 동작하지만 실제 점수 계산은 미구현.
- 영문 리뷰만 수집. 한국어 리뷰는 데이터셋에 없음.

---

## 기술 스택

Python 3.10+ · scikit-learn (Ridge, TruncatedSVD) · scipy (sparse) · FAISS-CPU · LangGraph · LangChain · Upstage Solar (chat + embedding) · Streamlit · pandas · numpy
