import pandas as pd
import requests
import time
import random
import urllib.parse
import csv
import os

# HTTP 요청 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

def sleep_jitter(min_s=1.0, max_s=2.0):
    """요청 사이에 랜덤 지연"""
    time.sleep(random.uniform(min_s, max_s))

def get_appid(game_name):
    """Steam에서 게임명으로 AppID 검색"""
    q = urllib.parse.quote(game_name)
    url = f"https://store.steampowered.com/api/storesearch/?term={q}&cc=US&l=en&v=1"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
    except:
        return None
    
    items = data.get("items", [])
    if not items:
        return None

    # 정확 일치 먼저 확인
    low = game_name.lower()
    exact = [it for it in items if it.get("name", "").lower() == low]
    cands = exact or items
    appid = cands[0].get("id")
    return int(appid) if appid else None

def get_reviews(appid, max_reviews=200, lang="english"):
    """Steam 리뷰 API에서 리뷰 수집"""
    url = f"https://store.steampowered.com/appreviews/{appid}?json=1&purchase_type=all&language={lang}&review_type=all&num_per_page=100&filter=recent"
    out = []
    cursor = "*"
    while len(out) < max_reviews:
        try:
            r = requests.get(url + f"&cursor={urllib.parse.quote(cursor)}", headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break
            data = r.json()
        except:
            break

        reviews = data.get("reviews", [])
        if not reviews:
            break

        for rv in reviews:
            out.append({
                "appid": appid,
                "recommendationid": rv.get("recommendationid"),
                "author_steamid": rv.get("author", {}).get("steamid"),
                "review": rv.get("review", "").replace("\n", " ").strip(),
                "voted_up": rv.get("voted_up"),
                "votes_up": rv.get("votes_up"),
                "votes_funny": rv.get("votes_funny"),
                "weighted_vote_score": rv.get("weighted_vote_score"),
                "comment_count": rv.get("comment_count"),
                "steam_purchase": rv.get("steam_purchase"),
                "received_for_free": rv.get("received_for_free"),
                "written_during_early_access": rv.get("written_during_early_access")
            })
            if len(out) >= max_reviews:
                break

        cursor = data.get("cursor")
        if not cursor:
            break
        sleep_jitter(0.5, 1.0)
    return out

def main():
    os.makedirs("../outputs", exist_ok=True)
    meta_csv = "../outputs/metacritic_pc_userscore_green.csv"  # 네 CSV 경로
    out_csv = "../outputs/steam_reviews.csv"
    
    df = pd.read_csv(meta_csv)
    all_reviews = []

    for idx, row in df.iterrows():
        title = str(row["title"])
        print(f"[{idx+1}/{len(df)}] {title} → AppID 검색 중...")
        appid = get_appid(title)
        print(f"  AppID: {appid}")
        if not appid:
            sleep_jitter()
            continue

        reviews = get_reviews(appid, max_reviews=200)
        for r in reviews:
            r["game_title"] = title
        all_reviews.extend(reviews)

        # 중간 저장
        if idx % 10 == 0 or idx == len(df)-1:
            with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=all_reviews[0].keys())
                writer.writeheader()
                writer.writerows(all_reviews)
            print(f"  🔄 {len(all_reviews)}개 리뷰 중간 저장 완료")

        sleep_jitter()

    print(f"✅ 리뷰 수집 완료: {out_csv} (총 {len(all_reviews)}개 리뷰)")

if __name__ == "__main__":
    main()
