import asyncio
import aiohttp
import pandas as pd
from datetime import timedelta
import time

STEAM_API_URL = (
    "https://store.steampowered.com/appreviews/{appid}"
    "?json=1&filter=all&language=english"
    "&day_range=9223372036854775807&start_offset=0"
    "&num_per_page=100&review_type=all&purchase_type=all"
)

# ---- 리뷰 가져오기 ----
async def fetch_reviews(session, appid, steamid):
    url = f"{STEAM_API_URL.format(appid=appid)}&user={steamid}"
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data.get("reviews", [])
    except Exception as e:
        print(f"[예외] appid {appid}, steamid {steamid}: {e}")
        return []

# ---- 메인 ----
async def main_async(input_csv="../outputs/steam_reviews.csv",
                     out_csv="../outputs/user_game_matrix.csv",
                     test=False):

    df = pd.read_csv(input_csv)

    # 유저 ID 컬럼 통일
    if "author_steamid" in df.columns:
        df = df.rename(columns={"author_steamid": "steamid"})
    
    if "steamid" not in df.columns or "appid" not in df.columns:
        raise ValueError("⚠️ 입력 CSV에 'steamid'와 'appid' 컬럼이 필요합니다!")

    unique_pairs = df[["appid", "steamid"]].drop_duplicates().values.tolist()

    # ---- test 모드 ----
    if test:
        unique_pairs = unique_pairs[:100]  # 100개만 실행
        print("🧪 테스트 모드 실행 (100개만 처리)")
    
    total = len(unique_pairs)
    print(f"요청 대상: {total} (appid+steamid 조합)")

    tasks = []
    results = []

    start_time = time.time()
    connector = aiohttp.TCPConnector(limit=50)
    async with aiohttp.ClientSession(connector=connector) as session:
        for i, (appid, steamid) in enumerate(unique_pairs, 1):
            tasks.append(fetch_reviews(session, appid, steamid))

            if len(tasks) >= 100:  # 100개씩 실행
                responses = await asyncio.gather(*tasks)
                tasks = []

                for res in responses:
                    for r in res:
                        author = r.get("author", {})
                        #print("author dict:", author)  
                        #print("steamid:", author.get("steamid"))
                        results.append({
                            "appid": appid,
                            "steamid": str(author.get("steamid", steamid)),
                            "voted_up": r.get("voted_up"),
                            "playtime_forever": author.get("playtime_forever", 0),
                        })

                # ---- 진행률 출력 ----
                if i % 500 == 0 or i == total:
                    elapsed = time.time() - start_time
                    per_item = elapsed / i
                    remaining = (total - i) * per_item
                    percent = (i / total) * 100
                    print(f"🌸 {i}/{total} ({percent:.2f}%) 완료")
                    print(f"⏱ 경과: {timedelta(seconds=int(elapsed))} | "
                          f"예상 남은: {timedelta(seconds=int(remaining))}")

        # 남은 task 처리
        if tasks:
            responses = await asyncio.gather(*tasks)
            for res in responses:
                for r in res:
                    author = r.get("author", {})
                    results.append({
                        "appid": appid,
                        "steamid": str(author.get("steamid", steamid)),
                        "voted_up": r.get("voted_up"),
                        "playtime_forever": author.get("playtime_forever", 0),
                    })

    out_df = pd.DataFrame(results)

    # 리뷰 1개뿐인 유저 제거 (협업 필터링 위해) - 주석 처리됨
    # if "steamid" in out_df.columns:
    #     filtered = out_df.groupby("steamid").filter(lambda x: len(x) > 1)
    # else:
    #     print("⚠️ steamid 컬럼 없음! 원본 그대로 저장")
    #     filtered = out_df

    # 모든 데이터 유지 (필터링 제거)
    filtered = out_df

    filtered.to_csv(out_csv, index=False)
    print(f"✅ 저장 완료: {out_csv} (최종 {len(filtered)}개 리뷰)")

# ---- 실행부 ----
def main():
    asyncio.run(main_async(test=False))   # True면 100개만, False면 전체 실행

if __name__ == "__main__":
    main()
