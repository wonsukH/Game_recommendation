# Steam 게임 추천 에이전트

> type: overview · status: active · updated: 2026-07-22

Steam 라이브러리를 읽고 다음에 할 게임을 골라주는 개인화 추천 에이전트입니다.
Steam 프로필 주소를 넣으면 플레이 기록 기반으로, 없으면 채팅만으로 추천을 받습니다.

**[라이브 데모 바로가기](https://game-rec-agent.streamlit.app/)**
(무료 서버라 잠들어 있으면 첫 접속에 1~2분 걸립니다)

## 무엇을 할 수 있나

- "내 라이브러리 기반으로 추천해줘": 플레이 기록 전체를 보고 개인화 추천
- "스타듀 밸리 같은 거": 특정 게임과 비슷한 게임 찾기
- "친구랑 같이 할 건데": 여러 계정의 취향을 합쳐서 추천
- "새 장르 좀 발굴해줘": 평소 취향에서 한 발 벗어난 게임 제안
- 라이브러리 없이 채팅만으로도 추천 가능

## 어떻게 동작하나

**추천 모델.** 2만여 명의 실제 플레이 데이터(누가 어떤 게임을 얼마나 했는지)로 학습한
협업 필터링(EASE)입니다. 선호도는 플레이 시간을 그대로 쓰지 않고 게임별 백분위로 환산합니다.
온라인 게임처럼 플레이 시간이 부풀려지는 장르의 왜곡을 줄이기 위해서입니다.

**에이전트.** LangGraph가 요청을 분류해 알맞은 경로로 보냅니다.

| 요청 유형 | 처리 |
|---|---|
| 라이브러리 기반 | 전체 라이브러리를 EASE에 넣어 개인화 추천 |
| 특정 게임과 비슷한 것 | 함께 플레이된 게임 + 태그 유사도 필터 |
| 여러 명이 같이 | 라이브러리 여러 개를 합쳐 추천 |
| 새 장르 탐색 | 개인화 결과를 콘텐츠 태그로 재가중 |
| 라이브러리 없음 | LLM이 직접 추천 |

모든 경로에 공통으로 조건 필터(협동, 가격, 출시일 등), 품질 필터, 이미 플레이한 게임 제외,
스토어에서 구매할 수 없는 게임 제외가 적용됩니다.

**화면.** Streamlit 웹 앱입니다. Steam 프로필 주소를 입력하거나 데모 라이브러리를 고른 뒤
채팅으로 추천을 받습니다.

## 직접 실행

```powershell
# 1. 환경
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .

# 2. .env 파일 작성
#    GEMINI_API_KEY=...   (필수, https://aistudio.google.com/apikey)
#    STEAM_API_KEY=...    (실계정 라이브러리 조회 시에만 필요)

# 3. 실행
streamlit run serving/main_agent.py
```

## 프로젝트 구조

```
data_collection/   Steam 행동 데이터 수집 (크롤러 + SQLite)
pipeline/          추천 모델, 산출물 빌드, 평가
serving/           에이전트 그래프(LangGraph) + 웹 앱(Streamlit)
experiments/       실험 기록
docs/              상세 문서 (설계, 평가 방법, 결과 수치)
```

## 더 보기

- 문서 시작점: [docs/README.md](docs/README.md)
- 평가 방법: [docs/evaluation.md](docs/evaluation.md)
- 결과 수치: [docs/results.md](docs/results.md)
