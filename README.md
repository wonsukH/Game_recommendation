# Steam Game Recommendation — Personalized Agent

> **유형**: overview · **상태**: active · **갱신**: 2026-06-29

> 당신의 Steam 라이브러리(플레이한 게임·시간)를 읽고 "다음에 뭐 할까"를 개인화 추천하는 멀티에이전트.
> 그리고 — **이 시스템이 프론티어 LLM을 *어디서* 이기고 *어디서* 지는지**를 사전등록·CI로 정직하게 검증한 기록.

```
"엘든링 같은 거"  ·  "내 라이브러리 기반 추천"  ·  "새 장르 좀 발굴해줘"
        →  LangGraph 에이전트(라우팅 + CF + 콘텐츠 스티어링)  →  게임 5개 + 설명
```

---

## 무엇을 보여주는가 (정직한 포지셔닝)

이 프로젝트는 **두 가지**를 보여준다 — (1) 개인화에서 *입증된(범위 한정) 추천 성능 moat*, (2) 그 우위를 정직히 한정하는 *자기비판적 평가 역량*. ('성능이 아니라 평가가 자산'이 아니라 **둘 다**.)

- 익명/태그-유사도(첫 시도)는 프론티어 LLM에 ~96% 패배 → 그 스택은 폐기. **단 이는 익명/vibe 프레이밍 한정**이지 프로젝트 전체 판정이 아님.
- 실험으로 *이기는 지점*을 좁혀 **전체 라이브러리 개인화(CF)** 로 피벗:
  - **개인화 CF가 "LLM에 내 라이브러리 주고 추천받기"를 이김** — recall@20 **0.293 vs 0.173** (Δ+0.120 [+0.049, +0.192], 유의).
  - **CF ≈ EASE 동률**(전통 recsys 기준선과 통계적 차이 없음) → 단순 CF 채택이 정당, popularity는 압승.
  - **방향성 스티어링**으로 CF 필터버블을 깨고 신장르 발굴 — blinded judge win-rate 1.0.
- 모든 결정이 사전등록·CI·귀무/음성보고로 기록됨: `experiments/DELIBERATION_LOG.md`, `experiments/registry.jsonl`.

---

## 어떻게 동작하나

### 1) 개인화 CF moat (`pipeline/game_rec/agent/cf_recommender.py`)
12만 유저의 **공동플레이(co-play) 통계**로 "X를 좋아한 사람들이 같이 좋아한 게임"을 계산. 플레이타임 가중 item-item conditional-cosine. LLM이 in-context로 재현 못 하는 long-tail 행동 신호가 해자(moat).

### 2) LangGraph 에이전트 (`serving/agent_graph.py`)
요청을 라우팅해 *필요한 곳에만* 에이전트성을 씀(검증된 조건부 정당화):

| 라우트 | 예시 | 처리 |
|---|---|---|
| **library** | "내 라이브러리 기반 추천" | 전체 라이브러리 → CF 개인화 |
| **seed** | "엘든링 같은 거" | seed 게임(+시리즈) → co-play 유사작, 프랜차이즈 자동 제외 |
| **multi_entity** | "나랑 친구 같이 할 거" | 다중 라이브러리 interleave 융합 |
| **explore** | "새 장르 발굴해줘" | CF base를 콘텐츠 태그로 재가중(인접 노벨티 스티어링) |
| **anonymous** | "차분한 인디" (라이브러리 없음) | LLM-direct (LLM 우세 영역) |

제약 필터(협동/한국어/가격/출시일)·품질 게이트·played 제외는 도구층(`tools.py`).

### 3) Streamlit (`serving/main_agent.py`)
steamid(GetOwnedGames)/데모 라이브러리 입력 + 채팅 + 라우트/스티어 표시.

---

## 데이터 층 (재구축 중)

추천은 행동 데이터로 학습된다. 데이터 파이프라인을 **리뷰-CSV → 행동 SQLite 스토어로 재구축** 중:

- `data_collection/db.py` — 무손실 정규화 SQLite 스키마(owned·playtime·업적·wishlist·friends·badges + 게임 차원). steamid INTEGER, 업적 인터닝.
- `data_collection/crawl_unified.py` — 2-phase(유저 facts + 게임 dimension) 크롤러, 월-클록 페이싱, **일일 ≤90k 콜 하드캡**(reserve-before-call), AIMD+서킷브레이커, 재개형.
- 공식 Steam Web API + 공개 프로필만. 수집 데이터는 **로컬 전용(gitignored)**, 재배포 안 함 (Steam ToU).

> 진행 상황·다음 단계(P4~P9)·"무엇이 어디 있나"는 **[`docs/ROADMAP.md`](ROADMAP.md)** 참조.

---

## 실행

```powershell
# 1. 환경
python -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -r requirements.txt ; pip install -e .

# 2. .env (gitignored, 절대 commit 금지)
#    GEMINI_API_KEY=...        (에이전트 LLM, https://aistudio.google.com/apikey)
#    STEAM_API_KEY=...         (크롤링 시만, https://steamcommunity.com/dev/registerkey)

# 3. 데모 (serving/data/ 산출물 사용; 라이브 라이브러리는 공개 프로필 필요, 없으면 데모 proxy)
streamlit run serving/main_agent.py

# 4. (선택) 행동 데이터 크롤 — 백그라운드, 재개형, 일일 ≤90k
scripts\daily_crawl.bat
```

---

## 평가 (재현)

```powershell
# 랭커 벤치: CF vs EASE vs ALS vs popularity (co-play hold-out)
python -m pipeline.orchestration.ranker_benchmark
# 개인화: CF vs LLM-with-library vs popularity
python -m pipeline.orchestration.personalization_experiment
```

평가 철학: 만 개 게임 ground-truth는 비현실적 → **co-play hold-out(비순환)** + **CI/paired** + **사전등록 결정규칙** + **귀무/음성 결과도 그대로 보고**(예: 저-support shrinkage 미채택, D4 풍부도 레버 채택). 지표 자체의 적절성부터 검증(floor/ceiling·순환·섭동).

---

## 구조

```
Game_recommendation/
├── data_collection/      # 행동 SQLite 스토어 + 크롤러 (db.py, crawl_unified.py)
├── pipeline/game_rec/
│   ├── agent/            # cf_recommender · content · hybrid · tools · build_quality · steam_library
│   ├── data/             # 빌더(스코어·태그·인기) — P5에서 steam.db로 재배선 예정
│   └── evaluation/       # metrics · stats(CI) · coplay_labels · run_logger
├── pipeline/orchestration/  # ranker_benchmark · personalization_experiment · steering_eval · ...
├── serving/              # agent_graph.py(LangGraph) · main_agent.py(Streamlit) · data/(산출물)
├── experiments/          # DELIBERATION_LOG.md(추론 여정) · registry.jsonl · INDEX.md
├── docs/                 # ROADMAP.md(시작점) · INTENT · ISSUES · README_PIPELINE · technical_reference.html
├── scripts/daily_crawl.bat
└── tests/                # pytest (metrics · popularity · tag_vocab) + co-play eval set
```

## 더 보기
- **현재 상태 + 로드맵 + 핸드오프**: [`docs/ROADMAP.md`](ROADMAP.md) ← 리셋 후 여기부터
- **모든 고민·결정의 서사**: `experiments/DELIBERATION_LOG.md`
- **개발 의도/이슈**: [`docs/INTENT.md`](INTENT.md) · [`docs/ISSUES.md`](ISSUES.md)

## 보안 / 약관
`.env`(키)·`data_collection/steam.db`·`data_collection/export/`·크롤 유저데이터는 **전부 gitignored, 절대 commit 금지**. 공개 프로필 + 공식 API + 비상업 연구 용도, 일일 콜 상한 준수.
