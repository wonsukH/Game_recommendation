# 1. 데이터 수집 (Crawling)

> **유형**: design-spec · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [README_PIPELINE.md](../README_PIPELINE.md)


`data_collection/crawlers/` 안의 모듈들. 두 경로:
- **Legacy** (옛 베이스라인): Metacritic → Steam Reviews → User Reviews. 1031 게임 풀.
- **새 경로**: SteamSpy API + Steam Store appdetails. 10K 게임 풀.

## 1.1. Metacritic PC 타이틀 (`metacritic.ipynb`) — Legacy

- **방법**: Selenium WebDriver로 `metacritic.com/browse/games/...` 페이지 1~75 순회
- **데이터**: 게임 이름, userscore (green ≥ 7.5만 채택)
- **출력**: `outputs/metacritic_pc_userscore_green.csv` — 약 1800 titles
- **rate limit**: 페이지당 1-2초 sleep + browser session reuse

## 1.2. Steam 리뷰 (`steam_reviews.py`) — Legacy

- **입력**: Metacritic CSV
- **단계 1**: 타이틀 → appid 매핑. `https://store.steampowered.com/api/storesearch/?term={title}&l=english&cc=US` 호출
- **단계 2**: 각 appid에 대해 `https://store.steampowered.com/appreviews/{appid}?json=1&filter=recent&language=english&num_per_page=100` 호출. 최대 200개 리뷰/게임
- **데이터 schema**: `appid, steamid, voted_up, playtime_forever, review, timestamp_created, ...`
- **출력**: `outputs/steam_reviews.csv` — 약 348K rows
- **rate limit**: 0.5-2초 jitter, 10 appid마다 checkpoint CSV write

## 1.3. 유저별 전체 리뷰 (`user_reviews.py`) — Legacy

- **입력**: `steam_reviews.csv`의 unique steamid (~40K)
- **방법**: `steamcommunity.com/profiles/{steamid}/recommended/` HTML을 `aiohttp` + `BeautifulSoup`로 비동기 fetch. 각 유저의 리뷰 history (game name, voted_up, playtime_forever) 파싱
- **출력**: `outputs/user_all_reviews.csv` — 약 1.19M rows
- **rate limit**: 동시 connection 5, sleep 0.3-1초, 100명마다 checkpoint
- **현재 한계**: 첫 페이지(10건)만 받음 → 유저당 max 10 리뷰. Item2Vec sentence가 짧아 학습 약함.

## 1.4. SteamSpy — 태그 + 인기도 (`steamspy.py`) — 새 경로 (M1)

SteamSpy는 Steam 비공식 통계 API. user-tag vote count + owners range 무료 제공.

- **2-단계 호출**:
  1. **Pagination**: `https://steamspy.com/api.php?request=all&page={N}` (N=0..9) → 페이지당 1000 게임의 기본 정보
  2. **Per-game detail**: `https://steamspy.com/api.php?request=appdetails&appid={appid}` → 상세 (tags dict, owners range, average/median playtime, ...)
- **데이터 schema** (`steamspy_games.csv`):
  ```
  appid, name, developer, publisher, owners, average_forever, average_2weeks,
  median_forever, median_2weeks, ccu, price, initialprice, discount,
  languages, genre, tags_json
  ```
  - `owners`: 문자열 range. 예 `"100,000,000 .. 200,000,000"`
  - `tags_json`: JSON-encoded dict. 예 `{"Souls-like": 50000, "Difficult": 40000, ...}`. vote count가 value
- **출력**: `outputs/steamspy_games.csv` — 약 10K rows
- **rate limit**: appdetails는 1 req/sec. 10K = 약 3시간

## 1.5. Steam Store 메타데이터 (`steam_appdetails.py`) — 새 경로 (M1)

- **입력**: `steamspy_games.csv`의 appid
- **호출**: `https://store.steampowered.com/api/appdetails?appids={appid}&cc=US&l=english`
- **데이터**: description, short_description, genres, categories, languages, release_date, developers, publishers, price (initial + discount), platforms
- **출력**: `outputs/steam_appdetails.csv`
- **rate limit**: 1.5초/req, 429 발생 시 exponential backoff (60s → 120s → 240s). 50개마다 checkpoint. `--retry-missing` 모드로 누락된 appid만 재시도 가능

## 1.6. SteamSpy → retriever용 normalized CSV (`scripts/build_games_tags_csv.py`)

새 SteamSpy raw (`tags_json` dict 형태) → 옛 normalized schema (`steam_games_tags.csv`) 변환.

알고리즘:
1. `steamspy_games.csv` load → `tags_json` 파싱
2. `index_maps.json`의 `row2appid` 순서로 정렬 (retriever의 `idx_to_appid`와 일관성)
3. 각 태그에 `normalize_tag` 적용 (다음 섹션 참조)
4. 출력: `outputs/steam_games_tags.csv` (`appid, game_title, tags, tag_count`)

`tags` 컬럼은 콤마 구분 normalized 태그 리스트.

---
