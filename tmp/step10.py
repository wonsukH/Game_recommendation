import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Union
from dataclasses import dataclass


@dataclass
class UserIntent:
    """사용자 의도 데이터 클래스"""
    mode: str  # 'similar', 'vibe', 'hybrid'
    games: List[int]  # 시드 게임 ID 리스트
    phrases: List[str]  # 자연어 표현 리스트
    target_tags: List[str]  # 원하는 태그 리스트
    avoid_tags: List[str]  # 피하고 싶은 태그 리스트
    constraints: Dict[str, Union[str, int, float, bool]]  # 제약조건
    weights: Optional[Dict[str, float]] = None  # 가중치 (hybrid 모드용)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 10: LLM Intent Parsing")
    parser.add_argument(
        "--input", type=str,
        default="user_intent.json",
        help="Input user intent JSON file (default: user_intent.json)"
    )
    parser.add_argument(
        "--output", type=str,
        default="outputs/parsed_intent.json",
        help="Output parsed intent JSON file (default: outputs/parsed_intent.json)"
    )
    parser.add_argument(
        "--tag-vocab", type=str,
        default="outputs/tag_vocab.json",
        help="Tag vocabulary JSON file (default: outputs/tag_vocab.json)"
    )
    return parser.parse_args()


def validate_mode(mode: str) -> str:
    """모드 검증 및 정규화"""
    valid_modes = ['similar', 'vibe', 'hybrid']
    mode = mode.lower().strip()
    
    if mode not in valid_modes:
        raise ValueError(f"Invalid mode: {mode}. Must be one of {valid_modes}")
    
    return mode


def validate_games(games: List[int], index_maps: Dict) -> List[int]:
    """게임 ID 검증"""
    valid_game_ids = set(int(k) for k in index_maps.get('row2appid', {}).keys())
    
    validated_games = []
    for game_id in games:
        if game_id in valid_game_ids:
            validated_games.append(game_id)
        else:
            print(f"[WARNING] Invalid game ID: {game_id}")
    
    if not validated_games:
        raise ValueError("No valid game IDs found")
    
    return validated_games


def validate_tags(tags: List[str], tag_vocab: Dict) -> List[str]:
    """태그 검증 및 정규화"""
    valid_tags = set(tag_vocab.get('tag2idx', {}).keys())
    alias_map = tag_vocab.get('aliases', {})
    
    validated_tags = []
    for tag in tags:
        tag = tag.lower().strip()
        
        # 직접 매칭
        if tag in valid_tags:
            validated_tags.append(tag)
            continue
        
        # 별칭 매칭
        if tag in alias_map:
            canonical_tag = alias_map[tag]
            if canonical_tag in valid_tags:
                validated_tags.append(canonical_tag)
                continue
        
        # 부분 매칭
        for valid_tag in valid_tags:
            if tag in valid_tag or valid_tag in tag:
                validated_tags.append(valid_tag)
                break
        else:
            print(f"[WARNING] Unknown tag: {tag}")
    
    return list(set(validated_tags))  # 중복 제거


def validate_constraints(constraints: Dict) -> Dict:
    """제약조건 검증 및 정규화"""
    valid_constraints = {
        'price_max': float,
        'price_min': float,
        'platform': str,  # 'windows', 'mac', 'linux'
        'language': str,  # 'english', 'korean', etc.
        'age_rating': int,  # 0, 3, 7, 12, 16, 18
        'multiplayer': bool,
        'singleplayer': bool,
        'controller_support': bool,
        'achievements': bool,
        'cloud_saves': bool
    }
    
    validated_constraints = {}
    
    for key, value in constraints.items():
        if key in valid_constraints:
            expected_type = valid_constraints[key]
            try:
                if expected_type == bool:
                    validated_constraints[key] = bool(value)
                elif expected_type == int:
                    validated_constraints[key] = int(value)
                elif expected_type == float:
                    validated_constraints[key] = float(value)
                else:
                    validated_constraints[key] = str(value).lower()
            except (ValueError, TypeError):
                print(f"[WARNING] Invalid constraint value for {key}: {value}")
        else:
            print(f"[WARNING] Unknown constraint: {key}")
    
    return validated_constraints


def parse_user_intent(intent_json: Dict, tag_vocab: Dict, index_maps: Dict) -> UserIntent:
    """사용자 의도 파싱 및 검증"""
    print("[INFO] 사용자 의도 파싱 중...")
    
    # 필수 필드 검증
    required_fields = ['mode']
    for field in required_fields:
        if field not in intent_json:
            raise ValueError(f"Missing required field: {field}")
    
    # 모드 검증
    mode = validate_mode(intent_json['mode'])
    
    # 게임 ID 검증
    games = validate_games(intent_json.get('games', []), index_maps)
    
    # 태그 검증
    target_tags = validate_tags(intent_json.get('target_tags', []), tag_vocab)
    avoid_tags = validate_tags(intent_json.get('avoid_tags', []), tag_vocab)
    
    # 제약조건 검증
    constraints = validate_constraints(intent_json.get('constraints', {}))
    
    # 자연어 표현
    phrases = [str(p).strip() for p in intent_json.get('phrases', []) if str(p).strip()]
    
    # 가중치 (hybrid 모드용)
    weights = intent_json.get('weights', {})
    if mode == 'hybrid' and not weights:
        weights = {'similar': 0.5, 'vibe': 0.5}
    
    # 검증 결과 출력
    print(f"   - 모드: {mode}")
    print(f"   - 시드 게임: {len(games)}개")
    print(f"   - 자연어 표현: {len(phrases)}개")
    print(f"   - 원하는 태그: {len(target_tags)}개")
    print(f"   - 피할 태그: {len(avoid_tags)}개")
    print(f"   - 제약조건: {len(constraints)}개")
    
    return UserIntent(
        mode=mode,
        games=games,
        phrases=phrases,
        target_tags=target_tags,
        avoid_tags=avoid_tags,
        constraints=constraints,
        weights=weights
    )


def main(input_path: str, output_path: str, tag_vocab_path: str):
    print(f"[INFO] LLM 의도 파싱 시작:")
    print(f"   - 입력: {input_path}")
    print(f"   - 출력: {output_path}")
    print(f"   - 태그 사전: {tag_vocab_path}")
    
    # 입력 파일 확인
    if not Path(input_path).exists():
        print(f"[ERROR] 입력 파일이 없습니다: {input_path}")
        return
    
    # 태그 사전 로드
    if not Path(tag_vocab_path).exists():
        print(f"[ERROR] 태그 사전 파일이 없습니다: {tag_vocab_path}")
        return
    
    with open(tag_vocab_path, 'r', encoding='utf-8') as f:
        tag_vocab = json.load(f)
    
    # 인덱스 맵 로드
    index_maps_path = Path("outputs/index_maps.json")
    if not index_maps_path.exists():
        print(f"[ERROR] 인덱스 맵 파일이 없습니다: {index_maps_path}")
        return
    
    with open(index_maps_path, 'r', encoding='utf-8') as f:
        index_maps = json.load(f)
    
    # 사용자 의도 로드
    with open(input_path, 'r', encoding='utf-8') as f:
        intent_json = json.load(f)
    
    # 의도 파싱
    try:
        user_intent = parse_user_intent(intent_json, tag_vocab, index_maps)
    except Exception as e:
        print(f"[ERROR] 의도 파싱 실패: {e}")
        return
    
    # 결과를 딕셔너리로 변환
    result = {
        'mode': user_intent.mode,
        'games': user_intent.games,
        'phrases': user_intent.phrases,
        'target_tags': user_intent.target_tags,
        'avoid_tags': user_intent.avoid_tags,
        'constraints': user_intent.constraints,
        'weights': user_intent.weights,
        'validation_info': {
            'total_games': len(user_intent.games),
            'total_phrases': len(user_intent.phrases),
            'total_target_tags': len(user_intent.target_tags),
            'total_avoid_tags': len(user_intent.avoid_tags),
            'total_constraints': len(user_intent.constraints)
        }
    }
    
    # 출력 폴더 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 결과 저장
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 의도 파싱 완료!")
    print(f"   - 저장: {output_path}")
    
    # 샘플 출력
    print(f"\n[INFO] 파싱된 의도 샘플:")
    print(f"   - 모드: {user_intent.mode}")
    if user_intent.games:
        print(f"   - 시드 게임: {user_intent.games[:3]}...")
    if user_intent.phrases:
        print(f"   - 표현: {user_intent.phrases[:2]}...")
    if user_intent.target_tags:
        print(f"   - 원하는 태그: {user_intent.target_tags[:3]}...")
    if user_intent.constraints:
        print(f"   - 제약조건: {list(user_intent.constraints.keys())}")


if __name__ == "__main__":
    args = _parse_args()
    main(args.input, args.output, args.tag_vocab)
