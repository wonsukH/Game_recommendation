import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import numpy as np
from collections import Counter
import matplotlib.font_manager as fm
import platform
from tqdm import tqdm

# 한글 폰트 설정 - Windows 환경
def setup_korean_font():
    """한글 폰트 설정"""
    system = platform.system()
    
    if system == "Windows":
        # Windows에서 사용 가능한 한글 폰트 찾기
        korean_fonts = [
            'Malgun Gothic', '맑은 고딕',  # Windows 기본 한글 폰트
            'NanumGothic', '나눔고딕',
            'Batang', '바탕',
            'Dotum', '돋움',
            'Gulim', '굴림',
            'Arial Unicode MS',
            'MS Gothic'
        ]
        
        # 시스템에 설치된 폰트 목록 가져오기
        available_fonts = [f.name for f in fm.fontManager.ttflist]
        
        for font in korean_fonts:
            if font in available_fonts:
                plt.rcParams['font.family'] = font
                plt.rcParams['axes.unicode_minus'] = False
                print(f"✅ 한글 폰트 설정 완료: {font}")
                return True
        
        # 폰트 파일 경로로 직접 찾기
        font_paths = [
            'C:/Windows/Fonts/malgun.ttf',  # 맑은 고딕
            'C:/Windows/Fonts/malgunbd.ttf', # 맑은 고딕 Bold
            'C:/Windows/Fonts/gulim.ttc',   # 굴림
            'C:/Windows/Fonts/batang.ttc',  # 바탕
            'C:/Windows/Fonts/dotum.ttc',   # 돋움
        ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    font_prop = fm.FontProperties(fname=font_path)
                    plt.rcParams['font.family'] = font_prop.get_name()
                    plt.rcParams['axes.unicode_minus'] = False
                    print(f"한글 폰트 설정 완료 (파일 경로): {font_path}")
                    return True
                except Exception:
                    continue
    
    # 한글 폰트를 찾지 못한 경우 기본 설정
    plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams['axes.unicode_minus'] = False
    print("⚠️ 한글 폰트를 찾을 수 없어 기본 폰트를 사용합니다.")
    print("💡 한글이 깨질 수 있습니다. 영어로 표시하거나 폰트를 설치해주세요.")
    return False

# 폰트 설정 실행
setup_korean_font()

class SteamGameAnalyzer:
    def __init__(self):
        self.game_info_df = None
        
    def analyze_games(self, steam_reviews_path, user_game_matrix_path):
        """게임 데이터 분석"""
        print("📊 게임 데이터 분석 시작...")
        
        # 데이터 로드
        print("📁 데이터 파일 로딩 중...")
        steam_reviews_df = pd.read_csv(steam_reviews_path)
        user_game_matrix_df = pd.read_csv(user_game_matrix_path)
        
        print(f"✅ Steam 리뷰 데이터: {len(steam_reviews_df)}개 행")
        print(f"✅ 유저-게임 매트릭스: {len(user_game_matrix_df)}개 행")
        
        # 게임 정보 추출 (Steam API 없이 기존 데이터 사용)
        print("🔍 게임 정보 추출 중...")
        game_info = steam_reviews_df.groupby(['appid', 'game_title']).agg({
            'voted_up': ['count', 'sum'],
            'votes_up': 'sum',
            'votes_funny': 'sum',
            'comment_count': 'sum'
        }).reset_index()
        
        # 컬럼명 정리
        game_info.columns = ['appid', 'game_title', 'total_reviews', 'positive_reviews', 'total_votes_up', 'total_votes_funny', 'total_comments']
        
        # 긍정 리뷰 비율 계산
        game_info['positive_ratio'] = (game_info['positive_reviews'] / game_info['total_reviews'] * 100).round(2)
        
        # 플레이타임 통계 추가
        print("⏱️ 플레이타임 통계 계산 중...")
        playtime_stats = user_game_matrix_df.groupby('appid').agg({
            'playtime_forever': ['mean', 'median', 'std', 'count']
        }).reset_index()
        
        # 컬럼명 정리
        playtime_stats.columns = ['appid', 'avg_playtime', 'median_playtime', 'std_playtime', 'player_count']
        
        # NaN 값 처리
        playtime_stats['avg_playtime'] = playtime_stats['avg_playtime'].fillna(0)
        playtime_stats['median_playtime'] = playtime_stats['median_playtime'].fillna(0)
        playtime_stats['std_playtime'] = playtime_stats['std_playtime'].fillna(0)
        
        # 게임 정보와 플레이타임 통계 병합
        game_info = game_info.merge(playtime_stats, on='appid', how='left')
        
        # 병합 후 NaN 값 처리
        game_info['avg_playtime'] = game_info['avg_playtime'].fillna(0)
        game_info['median_playtime'] = game_info['median_playtime'].fillna(0)
        game_info['std_playtime'] = game_info['std_playtime'].fillna(0)
        game_info['player_count'] = game_info['player_count'].fillna(0)
        
        # 게임 정보 데이터프레임 저장
        self.game_info_df = game_info
        
        # 통계 분석
        self.generate_statistics(game_info, steam_reviews_df, user_game_matrix_df)
        
        # 유저별 게임 취향 분석 추가
        print("\n👥 유저별 게임 취향 분석 시작...")
        self.analyze_user_gaming_patterns(user_game_matrix_df, game_info)
        
        # 시각화
        self.create_visualizations(game_info, steam_reviews_df, user_game_matrix_df)
        
        # 결과 저장
        output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        game_info.to_csv(os.path.join(output_dir, 'outputs', 'game_info_with_names.csv'), index=False)
        print(f"💾 게임 정보 저장 완료: outputs/game_info_with_names.csv")
        
        return game_info

    def generate_statistics(self, game_info_df, steam_reviews_df, user_game_matrix_df):
        """통계 정보 생성"""
        print("\n📈 통계 분석 결과:")
        print("=" * 50)
        
        # 전체 게임 수
        print(f"\n🎮 전체 게임 수: {len(game_info_df)}개")
        
        # 리뷰 수별 게임 통계
        print(f"\n📝 리뷰 수별 게임 통계:")
        print(f"  평균 리뷰 수: {game_info_df['total_reviews'].mean():.1f}")
        print(f"  최대 리뷰 수: {game_info_df['total_reviews'].max()}")
        print(f"  최소 리뷰 수: {game_info_df['total_reviews'].min()}")
        
        # 긍정 리뷰 비율 통계
        print(f"\n👍 긍정 리뷰 비율 통계:")
        print(f"  평균 긍정 비율: {game_info_df['positive_ratio'].mean():.1f}%")
        print(f"  최고 긍정 비율: {game_info_df['positive_ratio'].max():.1f}%")
        print(f"  최저 긍정 비율: {game_info_df['positive_ratio'].min():.1f}%")
        
        # 플레이타임 통계
        print(f"\n⏱️ 플레이타임 통계:")
        valid_playtime = game_info_df[game_info_df['avg_playtime'] > 0]
        if len(valid_playtime) > 0:
            print(f"  평균 플레이타임: {valid_playtime['avg_playtime'].mean():.1f}분")
            print(f"  중앙값 플레이타임: {valid_playtime['median_playtime'].median():.1f}분")
            print(f"  최대 플레이타임: {valid_playtime['avg_playtime'].max():.1f}분")
            print(f"  최소 플레이타임: {valid_playtime['avg_playtime'].min():.1f}분")
        else:
            print(f"  플레이타임 데이터가 없습니다.")
        
        # 상위 게임들 (리뷰 수 기준)
        print(f"\n🏆 리뷰 수 상위 10개 게임:")
        top_games = game_info_df.nlargest(10, 'total_reviews')[['game_title', 'total_reviews', 'positive_ratio', 'avg_playtime']]
        for idx, row in top_games.iterrows():
            playtime_str = f"{row['avg_playtime']:.1f}분" if pd.notna(row['avg_playtime']) and row['avg_playtime'] > 0 else "데이터 없음"
            print(f"  {row['game_title']}: {row['total_reviews']}개 리뷰, {row['positive_ratio']}% 긍정, 평균 {playtime_str}")
        
        # 상위 게임들 (긍정 비율 기준, 최소 10개 리뷰)
        print(f"\n⭐ 긍정 비율 상위 10개 게임 (≥10개 리뷰):")
        top_positive = game_info_df[game_info_df['total_reviews'] >= 10].nlargest(10, 'positive_ratio')[['game_title', 'total_reviews', 'positive_ratio', 'avg_playtime']]
        for idx, row in top_positive.iterrows():
            playtime_str = f"{row['avg_playtime']:.1f}분" if pd.notna(row['avg_playtime']) and row['avg_playtime'] > 0 else "데이터 없음"
            print(f"  {row['game_title']}: {row['positive_ratio']}% 긍정, {row['total_reviews']}개 리뷰, 평균 {playtime_str}")
        
        # 상위 게임들 (평균 플레이타임 기준, 최소 10명 플레이어)
        print(f"\n🎯 평균 플레이타임 상위 10개 게임 (≥10명 플레이어):")
        top_playtime = game_info_df[(game_info_df['player_count'] >= 10) & (game_info_df['avg_playtime'] > 0)].nlargest(10, 'avg_playtime')[['game_title', 'avg_playtime', 'player_count', 'positive_ratio']]
        if len(top_playtime) > 0:
            for idx, row in top_playtime.iterrows():
                print(f"  {row['game_title']}: 평균 {row['avg_playtime']:.1f}분, {row['player_count']}명 플레이어, {row['positive_ratio']}% 긍정")
        else:
            print(f"  조건을 만족하는 게임이 없습니다.")

    def analyze_user_gaming_patterns(self, user_game_matrix_df, game_info_df):
        """유저별 게임 취향 패턴 분석"""
        print("🔍 유저별 게임 취향 패턴 분석 중...")
        
        # 유저별 게임 통계
        user_stats = user_game_matrix_df.groupby('steamid').agg({
            'appid': 'count',  # 플레이한 게임 수
            'playtime_forever': ['sum', 'mean', 'median'],
            'voted_up': 'sum'  # 긍정 리뷰 수
        }).reset_index()
        
        # 컬럼명 정리
        user_stats.columns = ['steamid', 'games_played', 'total_playtime', 'avg_playtime_per_game', 'median_playtime_per_game', 'positive_reviews']
        
        # 유저별 게임 취향 분석
        print(f"\n👤 유저별 게임 통계:")
        print(f"  총 유저 수: {len(user_stats)}명")
        print(f"  평균 플레이 게임 수: {user_stats['games_played'].mean():.1f}개")
        print(f"  평균 총 플레이타임: {user_stats['total_playtime'].mean():.1f}분")
        print(f"  평균 게임당 플레이타임: {user_stats['avg_playtime_per_game'].mean():.1f}분")
        
        # 게임 수별 유저 분포
        print(f"\n🎮 게임 수별 유저 분포:")
        game_count_dist = user_stats['games_played'].value_counts().sort_index()
        for game_count, user_count in game_count_dist.head(10).items():
            print(f"  {game_count}개 게임: {user_count}명 유저")
        
        # 유저별 게임 취향 유사성 분석
        print(f"\n🔗 게임 간 유사도 분석:")
        self.analyze_game_similarity(user_game_matrix_df, game_info_df)
        
        return user_stats

    def analyze_game_similarity(self, user_game_matrix_df, game_info_df):
        """게임 간 유사도 분석"""
        print("  📊 게임 간 유사도 계산 중...")
        
        # 기존 파일이 있는지 확인
        output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        similarity_file_path = os.path.join(output_dir, 'outputs', 'game_similarity_matrix.csv')
        
        if os.path.exists(similarity_file_path):
            print("    📁 기존 게임 유사도 행렬 파일을 불러오는 중...")
            try:
                game_similarity_with_names = pd.read_csv(similarity_file_path, index_col=0)
                print(f"    ✅ 기존 파일 불러오기 완료: {similarity_file_path}")
                
                # 게임 ID로 변환 (파일명에서 숫자 추출)
                game_ids = [int(col) for col in game_similarity_with_names.columns if col.isdigit()]
                if not game_ids:
                    # 컬럼명이 게임 이름인 경우, game_info_df에서 appid 찾기
                    game_ids = []
                    for col in game_similarity_with_names.columns:
                        matching_games = game_info_df[game_info_df['game_title'] == col]
                        if len(matching_games) > 0:
                            game_ids.append(matching_games.iloc[0]['appid'])
                
                # 높은 유사도를 가진 게임 쌍 찾기
                self._find_high_similarity_pairs(game_similarity_with_names, game_info_df)
                
                # 게임별 인기도 분석
                self._analyze_game_popularity(user_game_matrix_df, game_info_df)
                
                return game_similarity_with_names, None
                
            except Exception as e:
                print(f"    ⚠️ 기존 파일 로드 실패: {e}")
                print("    🔄 새로 계산을 시작합니다...")
        
        # 새로 계산
        return self._calculate_game_similarity(user_game_matrix_df, game_info_df)
    
    def _calculate_game_similarity(self, user_game_matrix_df, game_info_df):
        """게임 간 유사도 새로 계산"""
        # 게임별 플레이어 목록 생성 (더 효율적으로)
        print("    🔄 게임별 플레이어 목록 생성 중...")
        game_players = user_game_matrix_df.groupby('appid')['steamid'].apply(set).to_dict()
        
        # 게임 간 유사도 행렬 생성
        game_ids = list(game_players.keys())
        print(f"    🔄 {len(game_ids)}개 게임 간 유사도 계산 중...")
        
        # 더 효율적인 방법: numpy 배열 사용
        game_similarity_matrix = np.zeros((len(game_ids), len(game_ids)), dtype=int)
        
        # 게임 ID를 인덱스로 매핑
        game_id_to_idx = {game_id: idx for idx, game_id in enumerate(game_ids)}
        
        # tqdm으로 진행상황 표시
        total_pairs = len(game_ids) * (len(game_ids) + 1) // 2
        
        with tqdm(total=total_pairs, desc="게임 유사도 계산", unit="쌍") as pbar:
            for i, game1 in enumerate(game_ids):
                for j, game2 in enumerate(game_ids):
                    if i <= j:  # 대각선과 위쪽만 계산
                        # 집합 연산으로 공통 플레이어 수 계산
                        common_players = len(game_players[game1] & game_players[game2])
                        
                        # numpy 배열에 직접 저장
                        idx1, idx2 = game_id_to_idx[game1], game_id_to_idx[game2]
                        game_similarity_matrix[idx1, idx2] = common_players
                        game_similarity_matrix[idx2, idx1] = common_players  # 대칭
                        
                        pbar.update(1)
        
        # numpy 배열을 DataFrame으로 변환
        game_similarity_matrix = pd.DataFrame(
            game_similarity_matrix, 
            index=game_ids, 
            columns=game_ids
        )
        
        # 게임 정보와 병합하여 게임 이름 표시
        game_similarity_with_names = game_similarity_matrix.copy()
        game_similarity_with_names.index = game_similarity_with_names.index.map(
            lambda x: game_info_df[game_info_df['appid'] == x]['game_title'].iloc[0] if len(game_info_df[game_info_df['appid'] == x]) > 0 else f'Game_{x}'
        )
        game_similarity_with_names.columns = game_similarity_with_names.index
        
        # 높은 유사도를 가진 게임 쌍 찾기
        self._find_high_similarity_pairs(game_similarity_with_names, game_info_df)
        
        # 게임별 인기도 분석
        self._analyze_game_popularity(user_game_matrix_df, game_info_df)
        
        # 게임 유사도 행렬 저장
        output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        game_similarity_with_names.to_csv(os.path.join(output_dir, 'outputs', 'game_similarity_matrix.csv'))
        print(f"  💾 게임 유사도 행렬 저장 완료: outputs/game_similarity_matrix.csv")
        
        return game_similarity_matrix, None
    
    def _find_high_similarity_pairs(self, game_similarity_matrix, game_info_df):
        """높은 유사도 게임 쌍 찾기"""
        print("    🔍 높은 유사도 게임 쌍 찾는 중...")
        high_similarity_pairs = []
        
        # 게임 ID 추출 (컬럼명이 숫자인 경우)
        game_ids = []
        for col in game_similarity_matrix.columns:
            if col.isdigit():
                game_ids.append(int(col))
            else:
                # 게임 이름인 경우 appid 찾기
                matching_games = game_info_df[game_info_df['game_title'] == col]
                if len(matching_games) > 0:
                    game_ids.append(matching_games.iloc[0]['appid'])
        
        if not game_ids:
            # 컬럼명이 게임 이름인 경우
            for i in range(len(game_similarity_matrix)):
                for j in range(i+1, len(game_similarity_matrix)):
                    similarity = game_similarity_matrix.iloc[i, j]
                    if similarity >= 10:  # 공통 플레이어 10명 이상
                        game1_name = game_similarity_matrix.columns[i]
                        game2_name = game_similarity_matrix.columns[j]
                        high_similarity_pairs.append((game1_name, game2_name, similarity))
        else:
            # numpy 배열에서 직접 계산 (더 빠름)
            for i in range(len(game_ids)):
                for j in range(i+1, len(game_ids)):
                    similarity = game_similarity_matrix.iloc[i, j]
                    if similarity >= 10:  # 공통 플레이어 10명 이상
                        game1_id = game_ids[i]
                        game2_id = game_ids[j]
                        game1_name = game_info_df[game_info_df['appid'] == game1_id]['game_title'].iloc[0] if len(game_info_df[game_info_df['appid'] == game1_id]) > 0 else f'Game_{game1_id}'
                        game2_name = game_info_df[game_info_df['appid'] == game2_id]['game_title'].iloc[0] if len(game_info_df[game_info_df['appid'] == game2_id]) > 0 else f'Game_{game2_id}'
                        high_similarity_pairs.append((game1_name, game2_name, similarity))
        
        # 유사도 순으로 정렬
        high_similarity_pairs.sort(key=lambda x: x[2], reverse=True)
        
        print(f"  ✅ 높은 유사도를 가진 게임 쌍 (공통 플레이어 ≥10명): {len(high_similarity_pairs)}쌍")
        
        if high_similarity_pairs:
            print(f"  🏆 상위 20개 유사 게임 쌍:")
            for i, (game1, game2, similarity) in enumerate(high_similarity_pairs[:20]):
                print(f"    {i+1:2d}. {game1[:30]:<30} ↔ {game2[:30]:<30} : {similarity:3d}명 공통")
    
    def _analyze_game_popularity(self, user_game_matrix_df, game_info_df):
        """게임별 인기도 분석"""
        print(f"\n🎯 게임별 인기도와 유저 선호도 분석:")
        game_popularity = user_game_matrix_df.groupby('appid').agg({
            'steamid': 'count',  # 플레이한 유저 수
            'playtime_forever': 'mean'  # 평균 플레이타임
        }).reset_index()
        
        game_popularity.columns = ['appid', 'player_count', 'avg_playtime']
        
        # 게임 정보와 병합
        game_popularity = game_popularity.merge(game_info_df[['appid', 'game_title', 'positive_ratio']], on='appid', how='left')
        
        # 인기 게임 (플레이어 수 기준)
        print(f"  🎮 플레이어 수 상위 10개 게임:")
        top_popular = game_popularity.nlargest(10, 'player_count')
        for idx, row in top_popular.iterrows():
            print(f"    {row['game_title']}: {row['player_count']}명 플레이어, 평균 {row['avg_playtime']:.1f}분, {row['positive_ratio']:.1f}% 긍정")
        
        # 숨겨진 보석 게임 (낮은 플레이어 수, 높은 긍정 비율)
        hidden_gems = game_popularity[
            (game_popularity['player_count'] < 100) & 
            (game_popularity['positive_ratio'] > 80) &
            (game_popularity['avg_playtime'] > 100)
        ].nlargest(10, 'positive_ratio')
        
        if len(hidden_gems) > 0:
            print(f"  💎 숨겨진 보석 게임 (적은 플레이어, 높은 평가):")
            for idx, row in hidden_gems.iterrows():
                print(f"    {row['game_title']}: {row['player_count']}명 플레이어, {row['positive_ratio']:.1f}% 긍정, 평균 {row['avg_playtime']:.1f}분")

    def create_visualizations(self, game_info_df, steam_reviews_df, user_game_matrix_df):
        """게임 유사도 기반 감성 지도 시각화 생성"""
        print("\n🎨 게임 유사도 기반 감성 지도 시각화 생성 중...")
        
        # 시각화 저장 폴더 생성
        output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        viz_dir = os.path.join(output_dir, 'EDA', 'game_similarity_visualizations')
        os.makedirs(viz_dir, exist_ok=True)
        
        # 한글 폰트 사용 가능 여부 확인
        try:
            test_font = plt.rcParams['font.family']
            if 'DejaVu' in test_font or 'unknown' in test_font.lower():
                use_korean = False
                print("한글 폰트를 사용할 수 없어 영어로 표시합니다.")
            else:
                use_korean = True
        except Exception:
            use_korean = False
        
        # 1. 게임 유사도 히트맵
        self._create_similarity_heatmap(game_info_df, viz_dir, use_korean)
        
        # 2. 게임 클러스터링 시각화
        self._create_game_clustering(game_info_df, viz_dir, use_korean)
        
        # 3. 게임 네트워크 그래프
        self._create_game_network(game_info_df, viz_dir, use_korean)
        
        # 4. 감정 지도 (Emotional Map)
        self._create_emotional_map(game_info_df, viz_dir, use_korean)
        
        print(f"💾 모든 시각화 저장 완료: {viz_dir}")
    
    def _create_similarity_heatmap(self, game_info_df, viz_dir, use_korean):
        """게임 유사도 히트맵 생성"""
        print("  🔥 유사도 히트맵 생성 중...")
        
        # 게임 유사도 행렬 파일 로드
        output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        similarity_file_path = os.path.join(output_dir, 'outputs', 'game_similarity_matrix.csv')
        
        print("    📁 게임 유사도 행렬 파일을 사용합니다.")
        # 유사도 행렬 로드
        similarity_df = pd.read_csv(similarity_file_path, index_col=0)
        
        # 상위 50개 게임만 선택 (시각화 용이성)
        top_games = game_info_df.nlargest(50, 'player_count')
        
        # 유사도 행렬의 컬럼명과 게임 이름 매칭
        available_games = []
        for _, game in top_games.iterrows():
            game_title = game['game_title']
            # 유사도 행렬에 해당 게임이 있는지 확인
            if game_title in similarity_df.columns:
                available_games.append(game_title)
        
        print(f"    📊 매칭된 게임 수: {len(available_games)}개")
        
        if len(available_games) < 10:
            print("    ⚠️ 히트맵을 그릴 수 있는 게임이 충분하지 않습니다.")
            return
        
        # 유사도 행렬에서 상위 게임만 필터링
        similarity_matrix = similarity_df.loc[available_games, available_games].values
        game_names = available_games
        
        # 🔥 대각선 제거 (자기 자신과의 유사도)
        # float 타입으로 변환하여 NaN 값 처리 가능하게
        similarity_matrix = similarity_matrix.astype(float)
        np.fill_diagonal(similarity_matrix, np.nan)
        
        print(f"    📊 최종 히트맵 크기: {similarity_matrix.shape}")
        print(f"    📊 유사도 값 범위: {np.nanmin(similarity_matrix):.0f} ~ {np.nanmax(similarity_matrix):.0f}")
        
        plt.figure(figsize=(20, 16))
        
        # 게임 이름 라벨 처리 (너무 긴 이름은 줄임)
        def shorten_name(name, max_length=20):
            if len(name) > max_length:
                return name[:max_length-3] + '...'
            return name
        
        x_labels = [shorten_name(name) for name in game_names]
        y_labels = [shorten_name(name) for name in game_names]
        
        # 🔥 색상 맵과 중심점 조정으로 차이 극대화
        sns.heatmap(similarity_matrix, 
                   xticklabels=x_labels,
                   yticklabels=y_labels,
                   cmap='RdYlBu_r',  # 빨간색(높음) ↔ 파란색(낮음)
                   center=np.nanmedian(similarity_matrix),  # 중앙값을 중심으로
                   square=True,
                   cbar_kws={'label': 'Common Players (Similarity Score)'},
                   mask=np.isnan(similarity_matrix),  # NaN 값 마스킹
                   annot=False,  # 숫자 표시 제거로 가독성 향상
                   fmt='.0f')
        
        plt.title('Game Similarity Heatmap (Self-Similarity Excluded)' if not use_korean else '게임 유사도 히트맵 (자기 유사도 제외)', 
                 fontsize=16, pad=20)
        plt.xlabel('Games' if not use_korean else '게임', fontsize=12)
        plt.ylabel('Games' if not use_korean else '게임', fontsize=12)
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)
        plt.tight_layout()
        
        # 저장
        plt.savefig(os.path.join(viz_dir, 'game_similarity_heatmap.png'), 
                   dpi=300, bbox_inches='tight')
        plt.close()
        print(f"    ✅ 히트맵 저장 완료 (대각선 제거)")
    
    def _create_game_clustering(self, game_info_df, viz_dir, use_korean):
        """게임 클러스터링 시각화 (유사도 기반)"""
        print("  🎯 게임 클러스터링 시각화 생성 중...")
        
        # 게임 유사도 행렬 파일 로드
        output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        similarity_file_path = os.path.join(output_dir, 'outputs', 'game_similarity_matrix.csv')
        
        print("    📁 게임 유사도 행렬 파일을 사용합니다.")
        similarity_df = pd.read_csv(similarity_file_path, index_col=0)
        
        # 상위 100개 게임만 선택 (클러스터링 용이성)
        top_games = game_info_df.nlargest(100, 'player_count')
        top_game_names = set(top_games['game_title'].tolist())
        
        # 유사도 행렬에서 상위 게임만 필터링
        available_games = [col for col in similarity_df.columns if col in top_game_names]
        if len(available_games) < 10:
            print("    ⚠️ 클러스터링할 수 있는 게임이 충분하지 않습니다.")
            return
        
        # 유사도 행렬을 특성으로 사용
        similarity_matrix = similarity_df.loc[available_games, available_games]
        
        # 차원 축소 (PCA)로 2D 좌표 생성
        from sklearn.decomposition import PCA
        pca = PCA(n_components=2, random_state=42)
        game_coords = pca.fit_transform(similarity_matrix.values)
        
        # K-means 클러스터링 (유사도 기반)
        from sklearn.cluster import KMeans
        n_clusters = min(6, len(available_games) // 10)  # 게임 수에 따라 클러스터 수 조정
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        clusters = kmeans.fit_predict(similarity_matrix.values)
        
        # 시각화
        plt.figure(figsize=(15, 10))
        
        # 클러스터별 색상
        colors = plt.cm.Set3(np.linspace(0, 1, n_clusters))
        
        for cluster_id in range(n_clusters):
            cluster_mask = clusters == cluster_id
            cluster_coords = game_coords[cluster_mask]
            cluster_games = [available_games[i] for i in range(len(available_games)) if clusters[i] == cluster_id]
            
            # 게임 정보 가져오기
            cluster_info = top_games[top_games['game_title'].isin(cluster_games)]
            
            plt.scatter(cluster_coords[:, 0], 
                       cluster_coords[:, 1],
                       s=cluster_info['player_count'] / 20,  # 버블 크기
                       c=[colors[cluster_id]],
                       alpha=0.7,
                       label=f'Cluster {cluster_id + 1} ({len(cluster_games)}개 게임)')
        
        plt.xlabel('Principal Component 1 (Similarity)', fontsize=12)
        plt.ylabel('Principal Component 2 (Similarity)', fontsize=12)
        plt.title('Game Clustering by Similarity Matrix' if not use_korean else '유사도 행렬 기반 게임 클러스터링', fontsize=14)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # 저장
        plt.savefig(os.path.join(viz_dir, 'game_clustering.png'), 
                   dpi=300, bbox_inches='tight')
        plt.close()
        print(f"    ✅ 클러스터링 시각화 저장 완료")
    
    def _create_game_network(self, game_info_df, viz_dir, use_korean):
        """게임 네트워크 그래프"""
        print("  🌐 게임 네트워크 그래프 생성 중...")
        
        # 상위 30개 게임만 선택 (네트워크 복잡도 제한)
        # 🔥 상위 50개 게임으로 증가 (기존 30개에서 확장)
        top_games = game_info_df.nlargest(50, 'player_count')
        
        # 기존 유사도 행렬 파일 로드
        output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        similarity_file_path = os.path.join(output_dir, 'outputs', 'game_similarity_matrix.csv')
        
        import networkx as nx
        G = nx.Graph()
        
                # 노드 추가
        for _, game in top_games.iterrows():
            G.add_node(game['game_title'], 
                       size=game['player_count'],  # 원본 값 사용
                       positive_ratio=game['positive_ratio'])
        
        # 엣지 추가 (실제 유사도 기반)
        print("    📁 게임 유사도 행렬 파일을 사용합니다.")
        similarity_df = pd.read_csv(similarity_file_path, index_col=0)
        
        # 상위 게임들의 유사도 정보 사용
        top_game_names = set(top_games['game_title'].tolist())
        available_games = [col for col in similarity_df.columns if col in top_game_names]
        
        # 실제 유사도로 엣지 생성
        for i, game1 in enumerate(available_games):
            for j, game2 in enumerate(available_games):
                if i < j:
                    similarity = similarity_df.loc[game1, game2]
                    if similarity >= 3:  # 🔥 공통 플레이어 3명 이상 (기존 5명에서 낮춤)
                        G.add_edge(game1, game2, weight=similarity)
        
        # 시각화
        plt.figure(figsize=(24, 18))  # 🔥 크기 증가
        
        # 레이아웃 (더 넓게)
        pos = nx.spring_layout(G, k=4, iterations=100, scale=2.0)
        
                # 노드 그리기
        node_sizes = [G.nodes[node]['size'] for node in G.nodes()]
        node_colors = [G.nodes[node]['positive_ratio'] for node in G.nodes()]
        
        # 🔥 노드 크기 범위를 극적으로 조정 (최소 100, 최대 8000)
        min_size = 100
        max_size = 8000
        normalized_sizes = []
        
        # 🔥 세제곱근 스케일로 크기 차이를 극대화
        for size in node_sizes:
            # 세제곱근을 사용하여 크기 차이를 극대화
            cube_root_size = np.cbrt(size)
            normalized_size = min_size + (max_size - min_size) * (cube_root_size / np.cbrt(max(node_sizes)))
            normalized_sizes.append(normalized_size)
        
        print(f"    📊 노드 크기 범위: {min(normalized_sizes):.0f} ~ {max(normalized_sizes):.0f}")
        print(f"    📊 원본 플레이어 수 범위: {min(node_sizes):.0f} ~ {max(node_sizes):.0f}")
        print(f"    📊 크기 차이 배율: {max(normalized_sizes) / min(normalized_sizes):.1f}배")
        
        # 노드 색상: positive_ratio (긍정 리뷰 비율)
        # 🔴 빨간색: 낮은 긍정 비율 (게임이 좋지 않음)
        # 🔵 파란색: 높은 긍정 비율 (게임이 좋음)
        nx.draw_networkx_nodes(G, pos, 
                               node_size=normalized_sizes,
                               node_color=node_colors,
                               cmap='RdYlBu',
                               alpha=0.8)
        
                # 🔥 엣지 그리기 (두께를 얇게 조정)
        edge_weights = [G[u][v]['weight'] for u, v in G.edges()]
        
        # 엣지 두께를 더 얇게 조정 (기존 값을 0.3배로 축소)
        thin_edge_weights = [w * 0.3 for w in edge_weights]
        
        nx.draw_networkx_edges(G, pos, 
                               width=thin_edge_weights,
                               alpha=0.4,  # 투명도도 낮춤
                               edge_color='gray')
        
        # 라벨 (더 작게)
        nx.draw_networkx_labels(G, pos, 
                               font_size=7,  # 🔥 폰트 크기 축소
                               font_weight='bold')
        
        plt.title('Game Similarity Network (50 Games)' if not use_korean else '게임 유사도 네트워크 (50개 게임)', fontsize=18)
        
        # 컬러바 생성 (Axes 명시)
        sm = plt.cm.ScalarMappable(cmap='RdYlBu')
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=plt.gca())
        cbar.set_label('Positive Ratio (%)' if not use_korean else '긍정 비율 (%)')
        
        plt.axis('off')
        plt.tight_layout()
        
        # 저장
        plt.savefig(os.path.join(viz_dir, 'game_network.png'), 
                   dpi=300, bbox_inches='tight')
        plt.close()
        print(f"    ✅ 네트워크 그래프 저장 완료 (50개 게임, 극대화된 크기)")
    
    def _create_emotional_map(self, game_info_df, viz_dir, use_korean):
        """감정 지도 (Emotional Map) - 유사도 기반"""
        print("  🗺️ 감정 지도 생성 중...")
        
        # 게임 유사도 행렬 파일 로드
        output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        similarity_file_path = os.path.join(output_dir, 'outputs', 'game_similarity_matrix.csv')
        
        print("    📁 게임 유사도 행렬 파일을 사용합니다.")
        similarity_df = pd.read_csv(similarity_file_path, index_col=0)
        
        # 상위 100개 게임만 선택
        top_games = game_info_df.nlargest(100, 'player_count')
        top_game_names = set(top_games['game_title'].tolist())
        
        # 유사도 행렬에서 상위 게임만 필터링
        available_games = [col for col in similarity_df.columns if col in top_game_names]
        if len(available_games) < 10:
            print("    ⚠️ 감정 지도를 그릴 수 있는 게임이 충분하지 않습니다.")
            return
        
        # 유사도 행렬을 2D 좌표로 변환 (t-SNE 사용)
        from sklearn.manifold import TSNE
        similarity_matrix = similarity_df.loc[available_games, available_games]
        
        print("    🔄 t-SNE로 2D 좌표 변환 중...")
        tsne = TSNE(n_components=2, random_state=42, perplexity=min(30, len(available_games)-1))
        game_coords = tsne.fit_transform(similarity_matrix.values)
        
        # 게임 정보 가져오기
        game_info_filtered = top_games[top_games['game_title'].isin(available_games)]
        
        # 감정 지도 생성
        plt.figure(figsize=(16, 12))
        
        # 버블 크기 (플레이어 수)
        sizes = game_info_filtered['player_count'] / 20
        
        # 색상 (긍정 비율)
        colors = game_info_filtered['positive_ratio']
        
        # 산점도
        scatter = plt.scatter(game_coords[:, 0], 
                             game_coords[:, 1],
                             s=sizes,
                             c=colors,
                             cmap='RdYlBu',
                             alpha=0.7,
                             edgecolors='black',
                             linewidth=0.5)
        
        # 게임 이름 라벨 (상위 30개만)
        top_label_games = game_info_filtered.nlargest(30, 'player_count')
        for _, game in top_label_games.iterrows():
            game_idx = available_games.index(game['game_title'])
            plt.annotate(game['game_title'][:20] + '...' if len(game['game_title']) > 20 else game['game_title'],
                        (game_coords[game_idx, 0], game_coords[game_idx, 1]),
                        xytext=(5, 5), textcoords='offset points',
                        fontsize=8, alpha=0.8,
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))
        
        # 축 설정
        plt.xlabel('t-SNE Dimension 1 (Similarity)', fontsize=14)
        plt.ylabel('t-SNE Dimension 2 (Similarity)', fontsize=14)
        plt.title('Game Emotional Map by Similarity' if not use_korean else '유사도 기반 게임 감정 지도', fontsize=16, pad=20)
        
        # 컬러바
        cbar = plt.colorbar(scatter)
        cbar.set_label('Positive Ratio (%)' if not use_korean else '긍정 비율 (%)', fontsize=12)
        
        # 그리드
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 저장
        plt.savefig(os.path.join(viz_dir, 'emotional_map.png'), 
                   dpi=300, bbox_inches='tight')
        plt.close()
        print(f"    ✅ 감정 지도 저장 완료")

def main():
    """메인 실행 함수"""
    # 경로 설정
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    steam_reviews_path = os.path.join(project_root, 'outputs', 'steam_reviews.csv')
    user_game_matrix_path = os.path.join(project_root, 'outputs', 'user_game_matrix.csv')
    
    # 파일 존재 확인
    if not os.path.exists(steam_reviews_path):
        print(f"❌ 파일을 찾을 수 없습니다: {steam_reviews_path}")
        return
    
    if not os.path.exists(user_game_matrix_path):
        print(f"❌ 파일을 찾을 수 없습니다: {user_game_matrix_path}")
        return
    
    # 분석 실행
    analyzer = SteamGameAnalyzer()
    game_info_df = analyzer.analyze_games(steam_reviews_path, user_game_matrix_path)
    
    print("\n🎉 게임 분석 완료!")

if __name__ == "__main__":
    main()
