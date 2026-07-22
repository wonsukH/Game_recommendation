# Steam Game Recommendation — Personalized Agent

> **유형**: overview · **상태**: active · **갱신**: 2026-07-22

> 당신의 Steam 라이브러리(플레이한 게임·시간)를 읽고 "다음에 뭐 할까"를 개인화 추천하는 멀티에이전트.
> 그리고 — **이 시스템이 프론티어 LLM을 *어디서* 이기고 *어디서* 지는지**를 사전등록·CI로 정직하게 검증한 기록.

```
"엘든링 같은 거"  ·  "내 라이브러리 기반 추천"  ·  "새 장르 좀 발굴해줘"
        →  LangGraph 에이전트(라우팅 + EASE 개인화 + 콘텐츠 스티어링)  →  게임 5개 + 설명
```

---

## 무엇을 보여주는가 (정직한 포지셔닝)

이 프로젝트는 **두 가지**를 보여준다 — (1) 개인화에서 *입증된(범위 한정) 추천 성능 moat*,
(2) 그 우위를 정직히 한정하는 *자기비판적 평가 역량*. ('성능이 아니라 평가가 자산'이 아니라 **둘 다**.)

**검증된 헤드라인** (사전등록·CI·블라인드 심판 기록에서 산술 유도, 원값 병기 — 정본: [`docs/results.md`](docs/results.md)):

- **블라인드 평가에서, 유저가 실제로 사랑하는 게임과 구별되지 않는 추천** — 심판 High 50.0% vs
  유저 본인 애호작 상한 51.3% (CI 중첩). 제2 심판(Gemini)이 독립적으로 같은 서열 재현(κ 0.49/0.58).
- **추천 10개 중 8개는 유저 취향에 닿음** — High+Medium 82.0% (상한 80.2%).
- **무작위 대비 6.7배, 인기순 대비 +22%p** — 순수 개인화 기여 (High 50.0% / 인기순 28.0% / 무작위 7.5%).
- **한 번도 본 적 없는 미래 행동(위시리스트 추가)을 우연의 49배로 예측** (top-20이 미래 추가의 4.0% 포착, 우연 0.08%).
- 위 결론은 **무편향 랜덤 샘플 1,000명 패널·사전등록 1회 확정**으로 코호트 편향과 지표 순환을 제거하고 얻었다.
- **살아남은 건 가장 단순한 모델** — 선형 EASE가 뉴럴 CF·two-tower·학습 리랭커 등 15+ 도전자에 전승/동률.
  그리고 자체 감사가 내 결론 2개(랭커 순위를 뒤집은 cutoff 버그 등)를 잡아냈다 — 실패·귀무 결과까지 전부 기록.

피벗의 역사도 그대로 공개한다: 익명/태그-유사도(첫 시도)는 프론티어 LLM에 ~96% 패배 → 그 스택은 폐기.
실험으로 *이기는 지점*을 좁혀 **전체 라이브러리 개인화**로 피벗 — 개인화 CF가 "LLM에 내 라이브러리 주고
추천받기"를 유의하게 이김(recall@20 0.293 vs 0.173). 익명/vibe 프레이밍은 여전히 LLM 우세(정직한 한정).

---

## 어떻게 동작하나

### 1) 개인화 랭커 — EASE × 플레이타임 백분위 (`pipeline/game_rec/agent/ease_recommender.py`)
2만+ 무편향 수집 유저의 **행동(co-play) 데이터**로 학습한 EASE(닫힌형 선형 모델). 선호 신호는 원시
플레이시간이 아닌 **게임별 플레이타임 백분위** — 온라인게임의 시간 인플레(예: 844h)를 흡수한다.
LLM이 in-context로 재현하지 못하는 long-tail 공동플레이 통계가 해자(moat).

### 2) LangGraph 에이전트 (`serving/agent_graph.py`)
요청을 라우팅해 *필요한 곳에만* 에이전트성을 씀(검증된 조건부 정당화):

| 라우트 | 예시 | 처리 |
|---|---|---|
| **library** | "내 라이브러리 기반 추천" | 전체 라이브러리 → EASE 개인화 |
| **seed** | "엘든링 같은 거" | co-play 유사작 + **태그-유사도 게이트**(대중 시드의 인기차트 퇴화 방지), 프랜차이즈 자동 제외 |
| **multi_entity** | "나랑 친구 같이 할 거" | 다중 라이브러리 interleave 융합 |
| **explore** | "새 장르 발굴해줘" | EASE base를 콘텐츠 태그로 재가중(인접 노벨티 스티어링) |
| **anonymous** | "차분한 인디" (라이브러리 없음) | LLM-direct (LLM 우세 영역) |

제약 필터(협동/한국어/가격/출시일)·품질 게이트·played 제외·**가용성 필터**(스토어 구매 불가
게임 2,391종을 전 라우트에서 차단)는 도구층(`tools.py`).

### 3) Streamlit (`serving/main_agent.py`)
steamid(GetOwnedGames)/데모 라이브러리 입력 + 채팅 + 라우트/스티어 표시. **동의받은 실계정 5개 라이브
데모** 완료 — 실사용 피드백이 오프라인 지표가 못 보는 결함 2건(태그 게이트·가용성 필터)을 이틀 새
잡아내 당일 반영됨. 기록: [`docs/portfolio-headlines.md`](docs/portfolio-headlines.md).

---

## 데이터 층 — 행동 SQLite 스토어 (재구축 완료)

리뷰-CSV 파이프라인을 **행동 SQLite 스토어(`data_collection/steam.db`)**로 재구축 완료. 서빙 산출물은
전부 steam.db-native(런타임 CSV 0):

- `data_collection/db.py` — 무손실 정규화 스키마(owned·playtime·wishlist·friends·badges + 게임 차원).
- `data_collection/crawl_unified.py` — **무편향 랜덤 SteamID64 샘플링**(스노볼 없음), 일일 ≤90k 콜
  하드캡(reserve-before-call), AIMD+서킷브레이커, 재개형.
- 규모(스냅샷): 사용 가능 유저 2.3만(그중 무편향 랜덤 2.0만) · play 상호작용 124만 · 풀 41k 게임 —
  라이브 수치는 [`docs/status.md`](docs/status.md).
- 공식 Steam Web API + 공개 프로필만. 수집 데이터는 **로컬 전용(gitignored), 재배포 안 함** (Steam ToU).

---

## 실행

```powershell
# 1. 환경
python -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -r requirements.txt ; pip install -e .

# 2. .env (gitignored, 절대 commit 금지)
#    GEMINI_API_KEY=...        (에이전트 LLM, https://aistudio.google.com/apikey)
#    STEAM_API_KEY=...         (크롤링/실계정 조회 시만, https://steamcommunity.com/dev/registerkey)

# 3. 데모 (serving/data/ 산출물 사용; 라이브 라이브러리는 공개 프로필 필요, 없으면 데모 proxy)
streamlit run serving/main_agent.py

# 4. (선택) 행동 데이터 크롤 — 백그라운드, 재개형, 일일 ≤90k
scripts\daily_crawl.bat
```

---

## 평가 (방법론·재현)

만 개 게임 ground-truth는 비현실적 → **co-play hold-out** + **목표-독립 위시리스트 축** + **CI/paired
bootstrap** + **사전등록 결정규칙(BH-FDR)** + **귀무/음성 결과 그대로 보고**. 지표 자체의 적절성부터
검증한다(순환성·floor/ceiling·섭동) — 실제로 in-cohort NDCG는 선호 점수와 ρ≈0.958로 순환이라
위시리스트 축을 독립 판정축으로 세웠다.

- 방법론: [`docs/evaluation.md`](docs/evaluation.md) · 헤드라인 수치 정본: [`docs/results.md`](docs/results.md)
- 실험 카탈로그(전 비교·로그 위치): `experiments/INDEX.md` · 드라이버: `pipeline/orchestration/`

---

## 구조

```
Game_recommendation/
├── data_collection/      # 행동 SQLite 스토어 + 무편향 크롤러 (db.py, crawl_unified.py)
├── pipeline/game_rec/
│   ├── agent/            # ease_recommender · content · hybrid · tools · steam_library · build_quality
│   ├── data/             # 산출물 빌더 — steam.db-native (런타임 CSV 0)
│   └── evaluation/       # metrics · stats(CI) · coplay_labels · run_logger
├── pipeline/orchestration/  # 실험 드라이버 (P6 확정 · P8 e2e · 벤치마크 · ...)
├── serving/              # agent_graph.py(LangGraph) · main_agent.py(Streamlit) · data/(서빙 산출물)
├── experiments/          # 연구 증거(append-only): p4_sweep · p6_ood · 01~05(구스택) · DELIBERATION_LOG.md
├── docs/                 # 영어 티어드 위키 — README.md(시작점) · results · status · roadmap · ...
├── scripts/daily_crawl.bat
└── tests/                # pytest + co-play eval set
```

## 더 보기
- **정본 진입점(위키 인덱스)**: [`docs/README.md`](docs/README.md) ← 새로 보는 사람은 여기부터
- **현재 상태 / 로드맵**: [`docs/status.md`](docs/status.md) · [`docs/roadmap.md`](docs/roadmap.md)
- **모든 고민·결정의 서사**: `experiments/DELIBERATION_LOG.md`

## 보안 / 약관
`.env`(키)·`data_collection/steam.db`·`data_collection/export/`·크롤 유저데이터는 **전부 gitignored,
절대 commit 금지**. 공개 프로필 + 공식 API + 비상업 연구 용도, 일일 콜 상한 준수. 라이브 데모의
라이브러리 공개는 **명시적 동의 계정만**(SteamID 비공개).
