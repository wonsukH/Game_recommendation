# Steam Game Recommendation Agent

YBIGTA 27기 신입기수 팀 프로젝트로 만든 시스템을, 마치고 나서 다시 들여다보니 production 관점에서 부족한 부분들이 눈에 띄어 차근차근 다시 정리하고 키워나가는 레포.

원본 팀 작업은 `27th-project-game/`에 그대로 보존되어 있고, 본 레포는 그 시점의 clone에서 출발해 점진적으로 손을 본 흔적이 `git log`에 그대로 남는다.

---

## 무엇이 부족했나

팀 작업 직후 코드를 다시 읽으며 정리해본 약점들:

- `tmp/` 폴더에 미채택 v0 파이프라인이 그대로 살아있고, 어느 게 현역인지 표시되어 있지 않음
- 동일 로직의 `user_game_scores_penalty.py`가 `Crawling/`과 `FE/` 양쪽에 중복
- `FE/step1.py` ~ `step9.py` 같은 절차적 이름이라 어떤 step이 뭔지 알려면 README를 따로 봐야 함
- 9개 step 스크립트가 같은 I/O 코드(`index_maps.json` 로드, stats 저장 등)를 각자 들고 있음
- 하이퍼파라미터(γ, κ, α, η, λ, embedding_dim, text_model)가 argparse 디폴트로만 흩어져 있어 single source of truth 없음. 실제로 `params_v1.json`이 stale해진 채로 방치되어 있었음
- 프롬프트 few-shot이 Python triple-quoted string에 박혀있어 수정 diff가 코드 변경처럼 보임
- `st_app/app.py`가 215줄에 LangGraph 빌드 + Streamlit UI + 이벤트 핸들링을 다 가지고 있음
- 4개 파일에 bare `except:` (KeyboardInterrupt까지 삼킴)
- `outputs/`와 `st_app/data/` 사이 수동 sync (이미 어긋난 상태였음)
- `utils/`가 패키지가 아닌 flat 폴더라 `pip install -e .` 불가, sys.path hack에 의존
- 디렉토리 명명이 일관성 없음 (`Crawling`, `EDA`는 PascalCase, `st_app`은 `st_` 접두사)

---

## 지금까지 정리한 것

`git log --oneline` 기준 13개 커밋.

**기초 정리 (`66e577e` ~ `3d414c4`, `b66068b`)**

- 미사용 실험 코드를 `archive/`로 격리, 죽은 파일 3개 삭제
- `user_game_scores_penalty` 중복 제거 (CLI 버전으로 통일)
- 공유 I/O 헬퍼를 `utils/io.py`로 추출 + `pyproject.toml` 추가
- 하이퍼파라미터를 `config/default.yaml`로 단일화
- LLM 프롬프트를 `prompts/*.txt`로 외부화
- 모놀리식 `app.py`를 `graph.py` + `ui.py` + `main.py`로 분할
- `utils/logging.py` 구조화 로깅 + bare `except:` 4개 파일 narrowing
- `scripts/sync_data.py` 자동 동기화 + README 정리
- README 톤 정리 (이모지 제거, 자연스러운 문체로)

**레이아웃 리팩토링 (`f65e25d` ~ this commit)**

- `utils/` -> `game_rec/` 패키지로 승격, `logging.py` -> `log.py` (stdlib shadow 회피)
- `FE/step1..9.py` -> 의미 있는 도메인 이름으로 재배치:
    - `FE/step1.py` -> `game_rec/data/tag_vocab.py`
    - `FE/step2.py` -> `game_rec/data/game_tag_matrix.py`
    - `FE/step3.py` -> `game_rec/data/game_weights.py`
    - `FE/step4.py` -> `game_rec/models/tag_embeddings.py`
    - `FE/step5.py` -> `game_rec/models/tag_effects.py`
    - `FE/step6.py` -> `game_rec/models/game_vectors.py`
    - `FE/step7.py` -> `game_rec/models/text_alignment.py`
    - `FE/step8.py` -> `game_rec/evaluation/metadata.py`
    - `FE/step9.py` -> `game_rec/evaluation/quality.py`
    - `FE/create_faiss_index.py` -> `game_rec/index/faiss_index.py`
    - `FE/tag_similarity_matrix.py` -> `game_rec/index/tag_similarity.py`
- `st_app/rag/` -> `game_rec/agent/` (노드 파일은 `_node` 접미사 제거)
- `Crawling/` -> `crawlers/`, `EDA/` -> `eda/`, `st_app/` -> `app/`
- `pipelines/build_offline.py` — 9개 모듈을 차례로 호출하는 단일 진입점

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
- 메타데이터 -> Steam 페이지 카피 생성

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
| `W_align.npy` | (4096, 128), Upstage Solar 임베딩 -> 태그 공간 사상 |
| `faiss_index.faiss` | IndexFlatL2 |

상세한 학습 과정은 워크스페이스 루트의 `PROJECT_HISTORY.md` 참조 (팀 baseline 시점 기준의 history 문서).

---

## 아키텍처

```
사용자 쿼리
    |
[parser]        LLM이 mode/games/phrases/tags JSON으로 파싱
    |
[normalizer]    Bigram Jaccard로 게임명 캐노니컬화
    |
[route_by_mode] similar / vibe / hybrid / general 분기
    |
    +-- similar    FAISS 유사 게임 검색
    +-- vibe       태그 expand + 임베딩 합성 + FAISS
    +-- hybrid     similar + vibe 가중 결합
    +-- general    -> END
    |
[rerank]        tag_match x novelty 가중치 (사이드바 슬라이더)
    |
[response]      LangChain LLM으로 한국어 자연어 응답
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

### 오프라인 파이프라인

전체를 한 번에:

```powershell
python -m pipelines.build_offline
```

API 키나 일부 의존성이 없을 때 단계 건너뛰기:

```powershell
python -m pipelines.build_offline --skip-text-alignment --skip-faiss
```

개별 단계 직접 실행 (각각 `--help`로 인자 확인 가능):

```powershell
python -m game_rec.data.tag_vocab
python -m game_rec.data.game_tag_matrix
python -m game_rec.data.game_weights
python -m game_rec.models.tag_embeddings
python -m game_rec.models.tag_effects
python -m game_rec.models.game_vectors
python -m game_rec.models.text_alignment
python -m game_rec.evaluation.metadata --version v2 --backup
python -m game_rec.evaluation.quality
python -m game_rec.index.faiss_index
```

각 단계의 기본 하이퍼파라미터는 `config/default.yaml`에 있으며 CLI 인자로 override 가능.

### 데이터 동기화 (outputs/ -> app/data/)

```powershell
python scripts/sync_data.py
python scripts/sync_data.py --dry-run   # 변경 미리보기
```

### Streamlit 챗봇

```powershell
streamlit run app/main.py
```

---

## 디렉토리

```
Game_recommendation/
  game_rec/                         # 라이브러리 패키지
    config.py / io.py / log.py / prompts.py
    data/                           # 오프라인 데이터 준비
      tag_vocab.py
      game_tag_matrix.py
      game_weights.py
    models/                         # 임베딩/회귀
      tag_embeddings.py
      tag_effects.py
      game_vectors.py
      text_alignment.py
    index/
      faiss_index.py
      tag_similarity.py
    evaluation/
      metadata.py
      quality.py
    agent/                          # 온라인 추천 에이전트
      retriever.py
      nodes/
        parser.py / router.py / normalizer.py
        recommendation.py / response.py / general.py

  pipelines/
    build_offline.py                # 전체 파이프라인 오케스트레이션

  app/                              # Streamlit 진입점
    main.py / graph.py / ui.py
    data/                           # 앱이 읽는 산출물 사본

  crawlers/                         # Steam / Metacritic 크롤러
  eda/                              # 탐색적 분석 + 시각화
  outputs/                          # 파이프라인 산출물 (gitignored)
  config/                           # default.yaml
  prompts/                          # parser.txt, response_generator.txt
  scripts/                          # sync_data.py
  archive/                          # 미채택 v0 온라인 파이프라인 보존

  pyproject.toml
```

---

## 알려진 제약사항

- 회귀 R² = 0.3877. `game_rec.evaluation.quality`가 자동으로 "Poor fit" 판정. 태그 효과는 보조 신호고 주 임베딩 합성은 PPMI+SVD 기반이지만, 그 가정 자체가 옳은지는 Agent 평가 인프라 갖춘 뒤 ablation으로 검증 예정.
- `novelty_score`는 현재 0.5 고정 placeholder. UI 슬라이더는 동작하지만 실제 점수 계산은 미구현.
- 영문 리뷰만 수집. 한국어 리뷰는 데이터셋에 없음.

---

## 기술 스택

Python 3.10+ · scikit-learn (Ridge, TruncatedSVD) · scipy (sparse) · FAISS-CPU · LangGraph · LangChain · Upstage Solar (chat + embedding) · Streamlit · pandas · numpy
