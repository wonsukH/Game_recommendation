# Steam Game Recommendation Agent — 개인 후속 연구

YBIGTA 27기 신입기수 **팀 프로젝트(원본 레포: `27th-project-game`)** 에서 출발한 개인 후속 연구. 팀에서 구축한 임베딩 자산을 활용해 LLM Agent 구조의 production-readiness와 측정 가능한 가치를 검증하는 것이 목표.

> **현재 상태**: 토대 정리 단계 완료. 다음 단계는 Agent 평가 인프라 + 새 기능 추가.

---

## 1. 프로젝트 맥락

- **팀 baseline**(2025-08 ~ 09): Steam 게임 1,031개 · 태그 393개 · 128차원 임베딩 / LangGraph 기반 RAG 챗봇 v0
- **개인 연구**(2026-05 ~): LLM Agent 엔지니어 포지션 포트폴리오를 목표로 production hygiene + 측정 가능한 가치 검증

팀 작업은 별도 레포(`27th-project-game/`)로 동결 보존. 본 레포는 그 시점의 clone을 시작점으로 점진적 개선 history를 쌓아간다 (`git log --oneline` 참고).

---

## 2. 팀 baseline에서 받은 자산

| 자산 | 형상/규모 |
|---|---|
| 게임 임베딩 | `game_vecs.npy` (1031, 128), 단위벡터 |
| 태그 임베딩 | `tag_vecs.npy` (393, 128), PPMI + Truncated SVD |
| 태그 효과 β | `tag_beta.npy` (393,), Ridge 회귀 |
| 텍스트→태그 정렬 | `W_align.npy` (4096, 128), Upstage Solar 임베딩 기반 |
| FAISS 인덱스 | `faiss_index.faiss`, IndexFlatL2 |
| LangGraph RAG | parser → normalizer → router(similar/vibe/hybrid/general) → rerank → response |

상세는 워크스페이스 루트의 `PROJECT_HISTORY.md` 참고.

---

## 3. 본인이 추가한 것 (개인 연구)

### 토대 정리 (완료)

- [x] **Commit 1** — 미사용 실험 코드(`tmp/` 온라인 파이프라인 v0)를 `archive/`로 격리 + 죽은 코드 3개 삭제
- [x] **Commit 2** — `user_game_scores_penalty` 중복 제거 (CLI 버전으로 통일)
- [x] **Commit 3** — `utils/io.py` 공유 모듈 추출 (`load_index_maps`, `load_csr`, `load_vectors`, `save_stats`, `load_tag_vocab`); `pyproject.toml`로 패키지화
- [x] **Commit 4** — 하이퍼파라미터(γ/κ/α/η/λ_reg/embedding_dim/text_model)를 `config/default.yaml`로 단일화 + `utils/config.py` 로더
- [x] **Commit 5** — LLM 프롬프트를 `prompts/*.txt`로 외부화 + `utils/prompts.py` 로더 (parser, response_generator)
- [x] **Commit 6** — `st_app/app.py` 215줄 모놀리식 → `graph.py`(LangGraph 빌더) + `ui.py`(Streamlit 렌더) + `app.py`(50줄 진입점) 3분할
- [x] **Commit 7** — `utils/logging.py` 구조화 로깅 도입 (stderr, ISO timestamp) + bare `except:` 4개 파일 narrowing + 핵심 노드(retriever, parser, normalizer) 마이그레이션
- [x] **Commit 8** — `scripts/sync_data.py` 자동 동기화(`outputs/` ↔ `st_app/data/`) + README 개인 연구 맥락으로 재작성

### 다음 단계 (로드맵)

#### 🔥 Phase A — Agent 가치 평가 인프라 (1주)

LangGraph 멀티노드 구조가 단발 LLM 호출 대비 실제로 가치 있는지 측정 가능한 형태로 증명한다.

- [ ] **Test query 셋 30-50개** 작성 (similar/vibe/hybrid + edge cases 비율 균등)
- [ ] **베이스라인 3종**:
  - A. Single-shot GPT/Solar (retrieval 없음)
  - B. 단순 RAG (mode 라우팅 없는 1턴 검색 + 생성)
  - C. 현재 LangGraph 풀 시스템
- [ ] **평가 방식**: LLM-as-judge + manual eval (1-5점 blind 채점) + latency/cost
- [ ] **결과**: README에 비교 표 + 어떤 쿼리 유형에서 멀티노드가 유의미했는지 실패 분석 1페이지

#### 🔥 Phase B — Agent 기능 확장

- [ ] **Tool use 노드**: Steam Web API 실시간 호출 (가격, 할인, 동시접속자)
- [ ] **멀티턴 메모리**: 이전 추천 컨텍스트 보존 ("그거 말고 더 가벼운 거" 같은 후속 질문)
- [ ] **Self-reflection 루프**: 응답을 LLM이 재평가해서 user query와 어긋나면 재검색
- [ ] **`novelty_score` 실제 구현** (현재 0.5 placeholder)

#### 🟡 Phase C — 게임 개발자용 미니 에이전트

JD의 "**게임 콘텐츠 / 제작 도구 / 업무 자동화**" 영역에 직격하는 사이드 프로젝트.

- [ ] **리뷰 → 개선 액션아이템 추출** (negative review clustering + 카테고리화)
- [ ] **게임 컨셉 브레인스토밍** (태그 조합 + 유사 사례 → 가상 컨셉서)
- [ ] **Steam 페이지 카피 생성** (메타데이터 → 한국어 마케팅 카피)

#### 🟡 Phase D — 인프라

- [ ] FastAPI 백엔드 분리
- [ ] 평가 결과를 CI에서 자동 비교 (regression 방지)
- [ ] 데이터 자산을 DVC 또는 외부 스토리지로 이동

---

## 4. 아키텍처

```
사용자 쿼리
    ↓
[parser_node]        ─ LLM이 mode/games/phrases/tags JSON으로 파싱
    ↓
[normalizer_node]    ─ Bigram Jaccard로 게임명 캐노니컬화
    ↓
[route_by_mode]      ─ similar / vibe / hybrid / general 분기
    ├─ similar_node  ─ FAISS 유사 게임 검색
    ├─ vibe_node     ─ 태그 expand + 임베딩 합성 + FAISS
    ├─ hybrid_node   ─ similar + vibe 가중 결합
    └─ general_node  → END
    ↓
[rerank_node]        ─ tag_match × novelty 가중치 (사이드바 슬라이더)
    ↓
[response_generator] ─ LangChain LLM으로 한국어 자연어 응답
    ↓
  END
```

다이어그램: `images/RAG_pipeline.png` (팀 baseline 시점) — agent 평가 인프라 이후 업데이트 예정.

---

## 5. 실행 방법

### 환경 셋업

```powershell
# 가상환경 활성화
.venv\Scripts\Activate.ps1

# 의존성 + 본 프로젝트를 editable로 설치
pip install -e .

# Upstage API 키 (.env 또는 환경변수)
# UPSTAGE_API_KEY=...
```

### 데이터 동기화 (outputs/ → st_app/data/)

```powershell
python scripts/sync_data.py
# dry-run으로 변경사항만 확인하려면
python scripts/sync_data.py --dry-run
```

### 오프라인 파이프라인 (재학습이 필요한 경우)

각 step의 디폴트는 `config/default.yaml`에서, CLI 인자로 override 가능.

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

## 6. 디렉토리 구조

```
Game_recommendation/
├── config/                  # 하이퍼파라미터 (Commit 4)
│   └── default.yaml
├── prompts/                 # LLM 프롬프트 (Commit 5)
│   ├── parser.txt
│   └── response_generator.txt
├── utils/                   # 공유 유틸 (Commit 3, 4, 5, 7)
│   ├── io.py
│   ├── config.py
│   ├── prompts.py
│   └── logging.py
├── scripts/
│   └── sync_data.py         # outputs/ → st_app/data/ 자동 동기화 (Commit 8)
├── Crawling/                # Steam/Metacritic 크롤러
├── EDA/                     # 탐색적 분석 + 시각화
├── FE/                      # 오프라인 임베딩 파이프라인 (step1-9 + faiss)
├── outputs/                 # 파이프라인 산출물
├── st_app/                  # Streamlit + LangGraph 챗봇
│   ├── app.py               # 50줄 진입점 (Commit 6)
│   ├── graph.py             # LangGraph 빌더
│   ├── ui.py                # Streamlit 렌더링
│   ├── data/                # 앱이 읽는 산출물 사본
│   └── rag/
│       ├── retriever.py     # FAISS + 쿼리 벡터 합성
│       └── nodes/           # parser / normalizer / similar / vibe / hybrid / general / response_generator
├── archive/                 # 미채택 실험 (Commit 1)
├── pyproject.toml           # editable install (Commit 3)
└── PROJECT_HISTORY.md       # 팀 baseline 단계 상세 히스토리
```

---

## 7. 알려진 제약사항

- 회귀 R² = 0.3877 (팀 baseline 시점) → 코드가 자동으로 "Poor fit" 판정. 태그 효과는 보조 신호로만 사용되며 주 임베딩 합성은 PPMI+SVD 기반. 이 점은 Phase A 평가 인프라가 갖춰진 뒤 ablation으로 별도 보고할 예정.
- `novelty_score`는 현재 0.5 고정 placeholder. Phase B에서 실제 구현 예정.
- `params_v1.json`의 `sentence_transformer` 필드는 stale (실제론 Solar로 재학습됨). 이번 정리에서 `config/default.yaml`이 single source of truth가 되도록 해결.

---

## 8. 기술 스택

- **Python 3.10+**, scikit-learn (Ridge, TruncatedSVD), scipy (sparse), FAISS-CPU
- **LangGraph** (multi-node agent), **LangChain** (LCEL, prompt templates)
- **Upstage Solar** (chat + embedding API)
- **Streamlit** (UI), **pandas** + **numpy**

---

**원본 팀 프로젝트**: `D:\YBIGTA\신입기수프로젝트\27th-project-game` (동결 보존)
**팀 구성**: YBIGTA 27기 신입기수 프로젝트
