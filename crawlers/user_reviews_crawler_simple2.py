import asyncio
import aiohttp
from aiohttp import ClientSession
from bs4 import BeautifulSoup
import pandas as pd
import time
from datetime import timedelta
import os # 중간저장 기능을 위한 추가
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---- 유저 리뷰 크롤링 ----
async def fetch_user_reviews(session: ClientSession, steamid: str):
    """특정 유저의 모든 리뷰 크롤링"""
    url = f"https://steamcommunity.com/profiles/{steamid}/reviews/"
    reviews = []

    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                print(f"[WARN] steamid {steamid} 응답 오류 {resp.status}")
                return []

            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            # 각 리뷰 블록 찾기
            review_blocks = soup.select(".review_box")
            for block in review_blocks:
                try:
                    app_link = block.select_one("a[href*='/app/']")
                    if not app_link:
                        continue

                    appid = app_link["href"].split("/app/")[1].split("/")[0]
                    
                    # (debug logs removed)

                    # voted_up 파싱 로직 개선
                    voted_up = 0  # 기본값은 0 (Not Recommended)
                    
                    # title 요소에서 voted_up 확인
                    title_elem = block.select_one(".title")
                    if title_elem:
                        title_text = title_elem.text.strip()
                        
                        # 정확한 문자열 비교
                        if title_text == "Recommended":
                            voted_up = 1
                        elif title_text == "Not Recommended":
                            voted_up = 0

                    playtime_el = block.select_one(".hours")
                    playtime = 0
                    if playtime_el:
                        txt = playtime_el.text.replace(",", "").strip()
                        if "hrs" in txt:
                            playtime = float(txt.split()[0]) * 60  # 시간을 분으로 변환

                    reviews.append({
                        "steamid": steamid,
                        "appid": appid,
                        "voted_up": voted_up,
                        "playtime_forever": playtime
                    })
                except Exception as e:
                    print(f"[WARN] steamid {steamid} 리뷰 파싱 중 오류: {e}")
                    continue

    except Exception as e:
        print(f"[EXCEPTION] steamid {steamid} 요청 실패: {e}")
        return []

    return reviews


# ---- 메인 ----
async def main_async(input_csv="./outputs/steam_reviews.csv",
                     out_csv="./outputs/user_all_reviews.csv",
                     test=False,
                     checkpoint_interval=100):  # 중간저장 간격

    df = pd.read_csv(input_csv)

    # 유저 ID 컬럼 통일
    if "author_steamid" in df.columns:
        df = df.rename(columns={"author_steamid": "steamid"})
    if "steamid" not in df.columns:
        raise ValueError("입력 CSV에 'steamid' 컬럼이 필요합니다!")

    unique_users = df["steamid"].drop_duplicates().tolist()

    if test:
        unique_users = unique_users[:50]
        print("[TEST] 테스트 모드 (50명만 실행)")

    total = len(unique_users)
    print(f"요청 대상 유저 수: {total}")

    # 중간저장 파일 경로
    checkpoint_file = out_csv.replace('.csv', '_checkpoint.csv')
    
    # 기존 중간저장 파일이 있으면 로드
    all_results = []
    start_index = 0
    if os.path.exists(checkpoint_file):
        try:
            checkpoint_df = pd.read_csv(checkpoint_file)
            all_results = checkpoint_df.to_dict('records')
            # 중간저장 파일의 리뷰 수가 아닌, 처리된 유저 수를 계산
            unique_steamids = set()
            for review in all_results:
                unique_steamids.add(review['steamid'])
            start_index = len(unique_steamids)
            print(f"[INFO] 중간저장 파일 로드됨: {checkpoint_file}")
            print(f"[INFO] 이미 처리된 유저 수: {start_index}")
            print(f"[INFO] 이미 처리된 리뷰 수: {len(all_results)}")
            print(f"[INFO] {start_index}번째 유저부터 이어서 작업합니다.")
        except Exception as e:
            print(f"[WARN] 중간저장 파일 로드 실패: {e}")
            print("처음부터 시작합니다.")
            start_index = 0
            all_results = []
    
    start_time = time.time()

    connector = aiohttp.TCPConnector(limit=10)  # 동시 요청 줄임
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        processed_count = 0  # 실제 처리된 유저 수를 추적
        
        for steamid in unique_users[start_index:]:
            tasks.append(fetch_user_reviews(session, steamid))
            processed_count += 1
            current_index = start_index + processed_count

            if len(tasks) >= 10:
                try:
                    responses = await asyncio.gather(*tasks, return_exceptions=True)
                    tasks = []
                    for res in responses:
                        if isinstance(res, Exception):
                            print(f"[WARN] 태스크 실행 중 오류: {res}")
                            continue
                        all_results.extend(res)
                except Exception as e:
                    print(f"[WARN] 태스크 실행 중 예외 발생: {e}")
                    # 실패한 태스크는 건너뛰고 계속 진행
                    tasks = []
                    continue

                # 중간저장 (checkpoint_interval마다)
                if current_index % checkpoint_interval == 0:
                    checkpoint_df = pd.DataFrame(all_results)
                    checkpoint_df.to_csv(checkpoint_file, index=False)
                    print(f"[INFO] 중간저장 완료: {checkpoint_file} ({len(all_results)}개 리뷰)")

                # 진행 상황 표시 (100명마다 또는 마지막)
                if current_index % 100 == 0 or current_index == total:
                    elapsed = time.time() - start_time
                    if processed_count > 0:
                        per_item = elapsed / processed_count
                        remaining = (total - current_index) * per_item
                    else:
                        per_item = 0
                        remaining = 0
                    
                    percent = (current_index / total) * 100
                    print(f"[PROGRESS] {current_index}/{total} ({percent:.2f}%) | 경과 {timedelta(seconds=int(elapsed))} | 남은 {timedelta(seconds=int(remaining))}")

        # 남은 태스크 처리
        if tasks:
            try:
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                for res in responses:
                    if isinstance(res, Exception):
                        print(f"[WARN] 마지막 태스크 실행 중 오류: {res}")
                        continue
                    all_results.extend(res)
            except Exception as e:
                print(f"[WARN] 마지막 태스크 실행 중 예외 발생: {e}")
                # 에러가 발생해도 수집된 결과는 저장

    # 최종 결과 저장
    out_df = pd.DataFrame(all_results)
    # 혹시라도 game_title이 존재하면 제거
    if "game_title" in out_df.columns:
        out_df = out_df.drop(columns=["game_title"]) 
    print("[INFO] 최종 appid 고유 개수:", out_df["appid"].nunique())
    print("[INFO] 최종 리뷰 개수:", len(out_df))

    out_df.to_csv(out_csv, index=False)
    print(f"[INFO] 최종 저장 완료: {out_csv}")
    
    # 중간저장 파일 삭제 (작업 완료 후)
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
        print(f"[INFO] 중간저장 파일 삭제됨: {checkpoint_file}")


def main():
    # 중간저장 간격 설정 (100명마다 저장)
    checkpoint_interval = 100
    
    print("[INFO] Steam 유저 리뷰 크롤러 시작")
    print(f"[INFO] 중간저장 간격: {checkpoint_interval}명마다")
    print("=" * 50)
    
    asyncio.run(main_async(
        test=False,  # 전체 실행
        checkpoint_interval=checkpoint_interval
    ))

if __name__ == "__main__":
    main()
