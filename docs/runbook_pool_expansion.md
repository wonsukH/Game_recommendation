# Runbook: 게임 풀 1031 → 10K 확장

원본 데이터셋은 메타크리틱 PC userscore 상위 1800개 타이틀에서 출발해 Steam appid 매핑 후 1031 게임으로 좁혀졌다. 이 풀은 메이저 인기작 편향이 강해 niche/long-tail 추천이 어렵다. SteamSpy + Steam Store appdetails API로 10K 게임 풀로 확장한다.

## 사전 조건

- `.venv` 활성화
- `pip install -e .` 완료 (또는 `pip install aiohttp pandas` 최소)
- `outputs/` 디렉토리 존재 (gitignored)

## 수집 단계

### 1. (선택) Sample dry-run 확인

코드가 잘 돌고 CSV 형식이 맞는지 1분 안에 확인.

```powershell
python -m data_collection.crawlers.steamspy --target-count 100 --dry-run
python -c "import pandas as pd; df = pd.read_csv('outputs/steamspy_games.csv'); print(df.shape, df.columns.tolist())"
```

`/all` 페이지만 받고 per-game `/appdetails` 태그 enrichment는 skip된 상태. 컬럼이 정상이면 본격 시작.

### 2. SteamSpy 본격 (약 3시간, target=10000 기준)

```powershell
python -m data_collection.crawlers.steamspy --target-count 10000
```

내부 동작:
1. `/all&page=0..N` 페이지네이션으로 popularity 상위 10K appid 수집 (수십 초)
2. 각 appid에 대해 `/appdetails`로 태그 dict + vote 수 받기 (1.1 req/sec → 약 3시간)

100건마다 진행 로그 stderr로 (`progress 100/10000 (0.9/s, eta 10800s)`).

출력: `outputs/steamspy_games.csv`. 컬럼:
- appid, name, developer, publisher
- owners, average_forever, median_forever, average_2weeks, median_2weeks, ccu
- price, initialprice, discount, languages, genre
- tags_json (JSON-encoded `{tag_name: vote_count}` dict)

### 3. Steam Store appdetails (약 3시간)

SteamSpy에 없는 메타데이터(설명, 공식 장르, 출시일, 가격 등)를 채운다.

```powershell
python -m data_collection.crawlers.steam_appdetails --input outputs/steamspy_games.csv
```

50건마다 체크포인트 자동 저장. 중간에 멈춰도 부분 결과 살아있음. 출력: `outputs/steam_appdetails.csv`.

### 4. 결과 검증

```powershell
python -c "
import pandas as pd
spy = pd.read_csv('outputs/steamspy_games.csv')
det = pd.read_csv('outputs/steam_appdetails.csv')
print('steamspy rows:', len(spy))
print('appdetails rows:', len(det))
print('appdetails available:', det['available'].sum())
print('games with non-empty tags_json:',
      spy['tags_json'].apply(lambda x: len(x) > 2).sum())
"
```

기대치:
- SteamSpy rows ≈ target-count (요청한 수)
- appdetails rows = SteamSpy rows
- appdetails `available` = SteamSpy 행의 80-95% (Store에서 dropped된 게임은 false)
- tags_json 비어있지 않은 게임 비율 ≥ 95% (SteamSpy가 거의 모든 게임에 태그 제공)

## 직렬 실행 (자기 전에)

PowerShell `;` 로 두 단계 연속:

```powershell
python -m data_collection.crawlers.steamspy --target-count 10000 ; `
python -m data_collection.crawlers.steam_appdetails --input outputs/steamspy_games.csv
```

총 5-6시간. 자고 일어나면 끝.

## 작은 풀로 시작하고 싶다면

작업 시간을 줄이려면 target을 낮춰 시작:

```powershell
# 5000 게임 (약 1.5시간 + 1.5시간)
python -m data_collection.crawlers.steamspy --target-count 5000

# 3000 게임 (약 50분 + 50분)
python -m data_collection.crawlers.steamspy --target-count 3000
```

이후 같은 명령에 target만 올려서 더 받으면 처음부터 다시 받는다. SteamSpy CSV는 누적이 아니라 덮어쓰기. 더 모으고 싶으면 큰 target 한 번에 받는 게 효율적.

## 트러블슈팅

| 증상 | 원인 | 대응 |
|---|---|---|
| `HTTP 429` 가끔 나옴 | rate limit 일시적 | 코드의 retry가 처리. 무시 가능 |
| 한참 멈춰있음 | SteamSpy 응답 느림 | 30초 timeout 후 다음으로. 그 게임만 skip |
| Steam Store HTTP 403/404 | 그 appid 비공개/dropped | row의 `available=false`로 들어감. 정상 |
| `aiohttp.ClientConnectorError` | 네트워크 끊김 | 재시작. SteamSpy는 처음부터, appdetails는 checkpoint부터 |

## 다음 단계

본 단계 끝나면 메인 파이프라인에 통합:

```powershell
python -m pipeline.orchestration.build_offline
```

새 풀로 임베딩 재학습. 자세한 통합 로직은 `pipeline/game_rec/data/`의 모듈들이 SteamSpy/appdetails CSV를 인식하도록 확장됨 (M3 commit 시리즈).
