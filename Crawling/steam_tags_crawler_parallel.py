import pandas as pd
import time
import random
import csv
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
from tqdm import tqdm
import threading
from queue import Queue
import concurrent.futures

def sleep_jitter(min_s=1.0, max_s=2.0):
    """요청 사이에 랜덤 지연"""
    time.sleep(random.uniform(min_s, max_s))

def setup_driver(headless=True):
    """Selenium 웹드라이버 설정"""
    options = Options()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-images')  # 이미지 로딩 비활성화 (속도 향상)
    options.add_argument('--disable-plugins')  # 플러그인 비활성화 (속도 향상)
    options.add_argument('--disable-extensions')  # 확장 프로그램 비활성화 (속도 향상)
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        print(f"⚠️ Chrome 드라이버 설정 실패: {e}")
        print("Chrome 브라우저와 ChromeDriver가 설치되어 있는지 확인하세요.")
        return None

def get_game_tags(driver, appid):
    """특정 appid의 Steam 게임 페이지에서 태그 추출"""
    url = f"https://store.steampowered.com/app/{appid}/"
    
    try:
        driver.get(url)
        
        # 연령 제한 페이지 체크 및 처리
        try:
            # 연령 제한 페이지인지 확인 (연도 선택 드롭다운이 있는지 체크)
            age_dropdown = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.ID, "ageYear"))
            )
            print(f"    🔞 연령 제한 페이지 감지됨, 처리 중...")
            
            # 연도 드롭다운 클릭
            age_dropdown.click()
            time.sleep(1)
            
            # 2000년 선택 (성인 연령)
            year_2000 = driver.find_element(By.XPATH, "//option[@value='2000']")
            year_2000.click()
            time.sleep(1)
            
            # "페이지 보기" 버튼 클릭
            view_page_btn = driver.find_element(By.ID, "view_product_page_btn")
            view_page_btn.click()
            time.sleep(2)
            
            print(f"    ✅ 연령 제한 통과")
            
        except TimeoutException:
            # 연령 제한 페이지가 아니면 정상 진행
            pass
        
        # 게임 페이지 로딩 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "apphub_AppName"))
        )
        
        # 게임 제목 추출
        try:
            game_title = driver.find_element(By.CLASS_NAME, "apphub_AppName").text
        except:
            game_title = "Unknown"
        
        # 태그 영역 찾기
        tags = []
        
        # 태그 추출 (먼저 "+ 더보기" 버튼 클릭 후 모든 태그 가져오기)
        try:
            # 1단계: "+ 더보기" 버튼 찾기 및 클릭
            show_more_clicked = False
            show_more_selectors = [
                ".app_tag_add_button",
                ".app_tag.add_button", 
                "[data-tooltip-text*='더']",
                "[data-tooltip-text*='more']",
                ".glance_tags .app_tag:last-child"
            ]
            
            for selector in show_more_selectors:
                try:
                    show_more_btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if show_more_btn and show_more_btn.is_displayed():
                        driver.execute_script("arguments[0].click();", show_more_btn)
                        time.sleep(1)  # 태그 로딩 대기
                        show_more_clicked = True
                        break
                except:
                    continue
            
            if not show_more_clicked:
                print(f"    ⚠️ '+ 더보기' 버튼을 찾을 수 없음")
            
            # 2단계: 모든 태그 가져오기 (클릭 후)
            tag_elements = driver.find_elements(By.CSS_SELECTOR, ".app_tag")
            
            for tag_elem in tag_elements:
                tag_text = tag_elem.text.strip()
                
                # 태그가 유효한지 확인
                if (tag_text and 
                    tag_text != '+' and 
                    len(tag_text) > 0 and 
                    len(tag_text) < 100):  # 너무 긴 텍스트는 제외
                    tags.append(tag_text)
                    
        except Exception as e:
            print(f"    태그 추출 오류: {e}")
        
        # 중복 제거 및 정리
        tags = list(dict.fromkeys(tags))  # 순서 유지하면서 중복 제거
        tags = [tag for tag in tags if tag and len(tag.strip()) > 0]
        
        return {
            "appid": appid,
            "game_title": game_title,
            "tags": ", ".join(tags),  # 태그를 쉼표로 구분된 문자열로 변환
            "tag_count": len(tags)
        }
        
    except TimeoutException:
        print(f"  ⚠️ 페이지 로딩 타임아웃 (appid: {appid})")
        return None
    except Exception as e:
        print(f"  ⚠️ 오류 발생 (appid: {appid}): {e}")
        return None

def load_unique_appids(csv_path):
    """CSV 파일에서 고유한 appid 목록 추출"""
    try:
        df = pd.read_csv(csv_path)
        unique_appids = df['appid'].unique().tolist()
        print(f"📊 총 {len(unique_appids)}개의 고유한 게임 발견")
        return unique_appids
    except Exception as e:
        print(f"⚠️ CSV 파일 읽기 실패: {e}")
        return []

def load_existing_results(output_path):
    """기존 크롤링 결과 로드"""
    csv_path = output_path
    try:
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            existing_appids = set(df['appid'].unique())
            print(f"📂 기존 크롤링 결과 발견: {len(existing_appids)}개 게임")
            return existing_appids, df.to_dict('records')
        else:
            print("📂 기존 크롤링 결과 없음 - 처음부터 시작")
            return set(), []
    except Exception as e:
        print(f"⚠️ 기존 결과 로드 실패: {e}")
        return set(), []

def filter_remaining_appids(all_appids, completed_appids):
    """완료되지 않은 appid만 필터링"""
    remaining = [appid for appid in all_appids if appid not in completed_appids]
    if len(remaining) < len(all_appids):
        print(f"🔄 재시작 모드: {len(all_appids) - len(remaining)}개 완료됨, {len(remaining)}개 남음")
    return remaining

def save_tags_data(tags_data, output_path):
    """태그 데이터를 CSV 파일로 저장"""
    if not tags_data:
        print("⚠️ 저장할 데이터가 없습니다.")
        return
    
    # CSV 저장
    csv_path = output_path
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        fieldnames = ['appid', 'game_title', 'tags', 'tag_count']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in tags_data:
            writer.writerow({
                'appid': item['appid'],
                'game_title': item['game_title'],
                'tags': item['tags'],
                'tag_count': item['tag_count']
            })
    
    print(f"✅ 태그 데이터 저장 완료: {csv_path}")

def process_appid_batch(appid_batch, driver, results_queue, failed_queue, driver_id):
    """한 배치의 appid들을 처리하는 함수 (병렬 처리용)"""
    batch_results = []
    batch_failed = []
    total_count = len(appid_batch)
    
    print(f"  🚀 드라이버 {driver_id} 시작: {total_count}개 게임 처리")
    
    for idx, appid in enumerate(appid_batch, 1):
        try:
            result = get_game_tags(driver, appid)
            if result:
                batch_results.append(result)
                print(f"    ✅ 드라이버 {driver_id} [{idx}/{total_count}] AppID {appid}: '{result['game_title']}' - {result['tag_count']}개 태그")
            else:
                batch_failed.append(appid)
                print(f"    ❌ 드라이버 {driver_id} [{idx}/{total_count}] AppID {appid} 처리 실패")
            
            # 요청 간 지연 (속도 향상)
            sleep_jitter(0.5, 1.0)
            
        except Exception as e:
            print(f"    ⚠️ 드라이버 {driver_id} [{idx}/{total_count}] AppID {appid} 처리 중 오류: {e}")
            batch_failed.append(appid)
    
    # 결과를 큐에 추가
    results_queue.put(batch_results)
    failed_queue.put(batch_failed)
    print(f"  🎯 드라이버 {driver_id} 완료: {len(batch_results)}개 성공, {len(batch_failed)}개 실패")

def main():
    # 출력 디렉토리 생성
    os.makedirs("outputs", exist_ok=True)
    
    # 설정 - game_info_with_names.csv에서 appid 추출
    input_csv = "outputs/game_info_with_names.csv"
    output_csv = "outputs/steam_games_tags.csv"
    
    # 고유한 appid 목록 로드
    print("📂 고유한 게임 ID 추출 중...")
    all_appids = load_unique_appids(input_csv)
    
    if not all_appids:
        print("❌ 처리할 게임이 없습니다.")
        return
    
    # 기존 크롤링 결과 확인
    completed_appids, existing_data = load_existing_results(output_csv)
    
    # 아직 크롤링되지 않은 게임들만 필터링
    appids = filter_remaining_appids(all_appids, completed_appids)
    
    if not appids:
        print("✅ 모든 게임이 이미 크롤링 완료되었습니다!")
        return
    
    # 병렬 처리를 위한 웹드라이버 설정
    print("🚀 병렬 웹드라이버 설정 중...")
    num_drivers = 5  # 동시 실행할 브라우저 수
    drivers = []
    
    for i in range(num_drivers):
        driver = setup_driver(headless=True)
        if driver:
            drivers.append(driver)
            print(f"  ✅ 드라이버 {i+1} 설정 완료")
        else:
            print(f"  ❌ 드라이버 {i+1} 설정 실패")
    
    if not drivers:
        print("❌ 모든 웹드라이버 설정에 실패했습니다.")
        return
    
    print(f"🎯 총 {len(drivers)}개의 드라이버로 병렬 처리 시작")
    
    # 태그 수집
    print(f"🏷️ {len(appids)}개 게임의 태그 수집 시작...")
    all_tags_data = existing_data.copy()  # 기존 데이터부터 시작
    new_tags_data = []  # 새로 크롤링한 데이터
    failed_appids = []
    
    try:
        # appid를 배치로 나누기
        batch_size = max(1, len(appids) // len(drivers))
        appid_batches = [appids[i:i + batch_size] for i in range(0, len(appids), batch_size)]
        
        print(f"📦 {len(appid_batches)}개 배치로 나누어 병렬 처리")
        
        # 병렬 처리 실행
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(drivers)) as executor:
            futures = []
            results_queue = Queue()
            failed_queue = Queue()
            
            # 각 드라이버에 배치 할당 (모든 배치 처리)
            for i, batch in enumerate(appid_batches):
                driver_idx = i % len(drivers)  # 0, 1, 2, 0, 1, 2... 순환
                driver = drivers[driver_idx]  # 0, 1, 2, 0, 1, 2... 순환
                driver_id = driver_idx + 1  # 1, 2, 3, 1, 2, 3... 순환
                future = executor.submit(process_appid_batch, batch, driver, results_queue, failed_queue, driver_id)
                futures.append(future)
                print(f"  🚀 배치 {i+1} ({len(batch)}개 게임) - 드라이버 {driver_id}에 할당")
            
            # 결과 수집
            for future in concurrent.futures.as_completed(futures):
                try:
                    # 결과 큐에서 데이터 가져오기
                    while not results_queue.empty():
                        batch_results = results_queue.get()
                        new_tags_data.extend(batch_results)
                        all_tags_data.extend(batch_results)
                    
                    # 실패한 appid 큐에서 데이터 가져오기
                    while not failed_queue.empty():
                        batch_failed = failed_queue.get()
                        failed_appids.extend(batch_failed)
                        
                except Exception as e:
                    print(f"⚠️ 배치 처리 중 오류: {e}")
    
    except KeyboardInterrupt:
        print("\n⚠️ 사용자에 의해 중단되었습니다.")
        print("💾 중단 시에도 현재까지 수집된 데이터를 저장합니다...")
        
        # 중단 시에도 저장
        if all_tags_data:
            save_tags_data(all_tags_data, output_csv)
            print(f"✅ 중단 시 저장 완료: {len(all_tags_data)}개 게임")
    
    except Exception as e:
        print(f"⚠️ 예상치 못한 오류: {e}")
        
        # 오류 발생 시에도 저장
        if all_tags_data:
            save_tags_data(all_tags_data, output_csv)
            print(f"✅ 오류 발생 시 저장 완료: {len(all_tags_data)}개 게임")
    
    finally:
        # 웹드라이버 종료
        for i, driver in enumerate(drivers):
            driver.quit()
            print(f"🛑 드라이버 {i+1} 종료")
    
    # 최종 결과 저장 (정상 완료 시)
    if all_tags_data and not KeyboardInterrupt:
        save_tags_data(all_tags_data, output_csv)
    
    # 태그 문자열 정리 (',,' 제거)
    print("\n🧹 태그 문자열 정리 중...")
    
    for item in tqdm(all_tags_data):
        if 'tags' in item and item['tags']:
            original_tags = item['tags']
            # ',,'가 존재할 경우에만 ', '를 ''로 변경
            if ',,' in original_tags:
                cleaned_tags = original_tags.replace(', ', '')
                item['tags'] = cleaned_tags

    
    # 결과 요약
    print("\n" + "="*50)
    print("📊 크롤링 결과 요약")
    print("="*50)
    print(f"총 처리 대상: {len(appids)}개 게임")
    print(f"성공: {len(all_tags_data)}개 게임")
    print(f"실패: {len(failed_appids)}개 게임")
    
    if failed_appids:
        print(f"\n❌ 실패한 AppID들: {failed_appids[:10]}{'...' if len(failed_appids) > 10 else ''}")
    
    if all_tags_data:
        avg_tags = sum(item['tag_count'] for item in all_tags_data) / len(all_tags_data)
        print(f"평균 태그 수: {avg_tags:.1f}개")
    
    print(f"\n💾 최종 결과 파일: {output_csv}")

if __name__ == "__main__":
    main()
