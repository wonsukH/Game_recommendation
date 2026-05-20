import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional
import re


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 15: LLM Explanation Generation")
    parser.add_argument(
        "--diverse-recommendations", type=str,
        default="outputs/diverse_recommendations.json",
        help="Input diverse recommendations JSON file (default: outputs/diverse_recommendations.json)"
    )
    parser.add_argument(
        "--intent", type=str,
        default="outputs/parsed_intent.json",
        help="Input parsed intent JSON file (default: outputs/parsed_intent.json)"
    )
    parser.add_argument(
        "--output", type=str,
        default="outputs/final_recommendations.json",
        help="Output final recommendations JSON file (default: outputs/final_recommendations.json)"
    )
    parser.add_argument(
        "--explanation-style", type=str,
        default="concise",
        choices=["concise", "detailed", "casual"],
        help="Explanation style (default: concise)"
    )
    return parser.parse_args()


def extract_matching_tags(game_tags: List[str], target_tags: List[str]) -> List[str]:
    """
    게임의 태그 중 사용자가 원하는 태그와 매칭되는 것들 추출
    
    Args:
        game_tags: 게임의 태그 리스트
        target_tags: 사용자가 원하는 태그 리스트
    
    Returns:
        매칭되는 태그 리스트
    """
    matching_tags = []
    for tag in game_tags:
        if tag in target_tags:
            matching_tags.append(tag)
    return matching_tags


def generate_explanation(recommendation: Dict, user_intent: Dict, 
                        explanation_style: str = "concise") -> str:
    """
    추천 게임에 대한 설명 생성
    
    Args:
        recommendation: 추천 게임 정보
        user_intent: 사용자 의도 정보
        explanation_style: 설명 스타일
    
    Returns:
        생성된 설명
    """
    game_id = recommendation['game_id']
    scores = recommendation['scores']
    
    # 점수 기반 설명 요소들
    tag_match_score = scores['tag_match']
    novelty_score = scores['novelty']
    recency_score = scores['recency']
    popularity_score = scores['popularity']
    final_score = scores['final']
    
    # 사용자 의도 정보
    mode = user_intent['mode']
    target_tags = user_intent['target_tags']
    phrases = user_intent['phrases']
    
    # 설명 템플릿 선택
    if explanation_style == "concise":
        return generate_concise_explanation(
            game_id, tag_match_score, novelty_score, mode, target_tags
        )
    elif explanation_style == "detailed":
        return generate_detailed_explanation(
            game_id, scores, mode, target_tags, phrases
        )
    else:  # casual
        return generate_casual_explanation(
            game_id, tag_match_score, novelty_score, mode, target_tags
        )


def generate_concise_explanation(game_id: str, tag_match: float, novelty: float,
                               mode: str, target_tags: List[str]) -> str:
    """간결한 설명 생성"""
    
    if mode == "similar":
        if tag_match > 0.7:
            return f"게임 {game_id}는 요청하신 게임과 매우 유사한 특성을 가지고 있습니다."
        elif tag_match > 0.4:
            return f"게임 {game_id}는 요청하신 게임과 유사한 요소들을 포함하고 있습니다."
        else:
            return f"게임 {game_id}는 요청하신 게임과 부분적으로 유사합니다."
    
    elif mode == "vibe":
        if novelty > 0.6:
            return f"게임 {game_id}는 독특한 분위기를 가진 게임입니다."
        else:
            return f"게임 {game_id}는 요청하신 분위기와 잘 맞습니다."
    
    else:  # hybrid
        if tag_match > 0.6 and novelty > 0.5:
            return f"게임 {game_id}는 유사성과 신선도를 모두 갖춘 게임입니다."
        elif tag_match > 0.6:
            return f"게임 {game_id}는 요청하신 게임과 유사하면서도 새로운 경험을 제공합니다."
        else:
            return f"게임 {game_id}는 요청하신 조건에 적합한 게임입니다."


def generate_detailed_explanation(game_id: str, scores: Dict, mode: str,
                                target_tags: List[str], phrases: List[str]) -> str:
    """상세한 설명 생성"""
    
    tag_match = scores['tag_match']
    novelty = scores['novelty']
    recency = scores['recency']
    popularity = scores['popularity']
    
    explanation_parts = []
    
    # 기본 정보
    explanation_parts.append(f"게임 {game_id}를 추천합니다.")
    
    # 모드별 설명
    if mode == "similar":
        if tag_match > 0.7:
            explanation_parts.append("이 게임은 요청하신 게임과 매우 높은 유사성을 보입니다.")
        elif tag_match > 0.4:
            explanation_parts.append("이 게임은 요청하신 게임과 상당한 유사성을 가지고 있습니다.")
        else:
            explanation_parts.append("이 게임은 요청하신 게임과 부분적인 유사성을 보입니다.")
    
    elif mode == "vibe":
        if phrases:
            explanation_parts.append(f"'{', '.join(phrases[:2])}'와 같은 분위기를 잘 반영합니다.")
        if novelty > 0.6:
            explanation_parts.append("독특하고 신선한 게임 경험을 제공합니다.")
    
    else:  # hybrid
        explanation_parts.append("유사성과 신선도를 모두 고려하여 선택되었습니다.")
    
    # 점수 기반 설명
    if tag_match > 0.5:
        explanation_parts.append("요청하신 태그와 잘 매칭됩니다.")
    
    if novelty > 0.6:
        explanation_parts.append("새롭고 독특한 게임입니다.")
    
    if recency > 0.7:
        explanation_parts.append("최신 게임으로 높은 품질을 보장합니다.")
    
    if popularity > 0.6:
        explanation_parts.append("인기 있는 게임으로 많은 플레이어들이 즐기고 있습니다.")
    
    return " ".join(explanation_parts)


def generate_casual_explanation(game_id: str, tag_match: float, novelty: float,
                              mode: str, target_tags: List[str]) -> str:
    """친근한 설명 생성"""
    
    if mode == "similar":
        if tag_match > 0.7:
            return f"게임 {game_id}는 정말 비슷한 느낌이에요! 꼭 한번 해보세요."
        elif tag_match > 0.4:
            return f"게임 {game_id}도 비슷한 재미를 느낄 수 있을 것 같아요."
        else:
            return f"게임 {game_id}도 나쁘지 않을 것 같아요."
    
    elif mode == "vibe":
        if novelty > 0.6:
            return f"게임 {game_id}는 정말 특별한 분위기예요! 새로운 경험을 해보세요."
        else:
            return f"게임 {game_id}는 원하시는 분위기와 잘 맞을 것 같아요."
    
    else:  # hybrid
        if tag_match > 0.6 and novelty > 0.5:
            return f"게임 {game_id}는 비슷하면서도 새로운 느낌이에요! 추천합니다."
        else:
            return f"게임 {game_id}도 좋은 선택일 것 같아요."


def add_explanations_to_recommendations(recommendations: List[Dict], 
                                      user_intent: Dict,
                                      explanation_style: str) -> List[Dict]:
    """
    추천 리스트에 설명 추가
    
    Args:
        recommendations: 추천 리스트
        user_intent: 사용자 의도
        explanation_style: 설명 스타일
    
    Returns:
        설명이 추가된 추천 리스트
    """
    print(f"[INFO] 설명 생성 중 (스타일: {explanation_style})...")
    
    for i, recommendation in enumerate(recommendations):
        # 설명 생성
        explanation = generate_explanation(
            recommendation, user_intent, explanation_style
        )
        
        # 추천 정보에 설명 추가
        recommendation['explanation'] = {
            'text': explanation,
            'style': explanation_style,
            'generation_method': 'rule_based',
            'confidence': recommendation['scores']['final']
        }
        
        # 간단한 태그 매칭 정보 추가 (실제로는 게임 메타데이터 필요)
        if user_intent['target_tags']:
            recommendation['explanation']['matching_tags'] = user_intent['target_tags'][:3]  # 상위 3개
    
    print(f"   - 설명 생성 완료: {len(recommendations)}개")
    
    return recommendations


def validate_explanations(recommendations: List[Dict]) -> Dict:
    """
    생성된 설명들의 품질 검증
    
    Args:
        recommendations: 추천 리스트
    
    Returns:
        검증 결과
    """
    print("[INFO] 설명 품질 검증 중...")
    
    validation_results = {
        'total_recommendations': len(recommendations),
        'explanations_generated': 0,
        'avg_explanation_length': 0,
        'explanation_confidence': []
    }
    
    total_length = 0
    
    for rec in recommendations:
        if 'explanation' in rec and 'text' in rec['explanation']:
            validation_results['explanations_generated'] += 1
            explanation_text = rec['explanation']['text']
            total_length += len(explanation_text)
            
            if 'confidence' in rec['explanation']:
                validation_results['explanation_confidence'].append(
                    rec['explanation']['confidence']
                )
    
    if validation_results['explanations_generated'] > 0:
        validation_results['avg_explanation_length'] = total_length / validation_results['explanations_generated']
        validation_results['avg_confidence'] = sum(validation_results['explanation_confidence']) / len(validation_results['explanation_confidence'])
    else:
        validation_results['avg_confidence'] = 0.0
    
    print(f"   - 설명 생성률: {validation_results['explanations_generated']}/{validation_results['total_recommendations']}")
    print(f"   - 평균 설명 길이: {validation_results['avg_explanation_length']:.1f}자")
    print(f"   - 평균 신뢰도: {validation_results['avg_confidence']:.4f}")
    
    return validation_results


def main(diverse_recommendations_path: str, intent_path: str, output_path: str,
         explanation_style: str):
    print(f"[INFO] LLM 설명 생성 시작:")
    print(f"   - 다양성 추천: {diverse_recommendations_path}")
    print(f"   - 사용자 의도: {intent_path}")
    print(f"   - 설명 스타일: {explanation_style}")
    
    # 파일 존재 확인
    required_files = [diverse_recommendations_path, intent_path]
    for file_path in required_files:
        if not Path(file_path).exists():
            print(f"[ERROR] 파일이 없습니다: {file_path}")
            return
    
    # 데이터 로드
    with open(diverse_recommendations_path, 'r', encoding='utf-8') as f:
        diverse_data = json.load(f)
    
    with open(intent_path, 'r', encoding='utf-8') as f:
        intent_data = json.load(f)
    
    print(f"[INFO] 데이터 크기:")
    print(f"   - 추천 수: {len(diverse_data['recommendations'])}")
    print(f"   - 사용자 모드: {intent_data['mode']}")
    
    # 설명 생성
    recommendations_with_explanations = add_explanations_to_recommendations(
        diverse_data['recommendations'], intent_data, explanation_style
    )
    
    # 설명 품질 검증
    validation_results = validate_explanations(recommendations_with_explanations)
    
    # 최종 결과 구성
    result = {
        'recommendation_info': {
            'total_recommendations': len(recommendations_with_explanations),
            'user_mode': intent_data['mode'],
            'explanation_style': explanation_style,
            'generation_timestamp': diverse_data.get('mmr_info', {}).get('lambda', 0.5)
        },
        'user_intent_summary': {
            'mode': intent_data['mode'],
            'target_tags_count': len(intent_data['target_tags']),
            'avoid_tags_count': len(intent_data['avoid_tags']),
            'constraints_count': len(intent_data['constraints'])
        },
        'recommendations': recommendations_with_explanations,
        'explanation_validation': validation_results,
        'diversity_metrics': diverse_data.get('diversity_metrics', {}),
        'mmr_info': diverse_data.get('mmr_info', {})
    }
    
    # 출력 폴더 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 결과 저장
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ LLM 설명 생성 완료!")
    print(f"   - 저장: {output_path}")
    print(f"   - 최종 추천 수: {len(recommendations_with_explanations)}")
    
    # 샘플 설명 출력
    print(f"\n[INFO] 샘플 설명 ({explanation_style} 스타일):")
    for i, rec in enumerate(recommendations_with_explanations[:3]):
        explanation = rec['explanation']['text']
        print(f"   {i+1}. 게임 {rec['game_id']}: {explanation}")
    
    # 검증 결과 요약
    print(f"\n[INFO] 설명 품질 요약:")
    print(f"   - 설명 생성률: {validation_results['explanations_generated']}/{validation_results['total_recommendations']}")
    print(f"   - 평균 설명 길이: {validation_results['avg_explanation_length']:.1f}자")
    print(f"   - 평균 신뢰도: {validation_results['avg_confidence']:.4f}")


if __name__ == "__main__":
    args = _parse_args()
    main(args.diverse_recommendations, args.intent, args.output, args.explanation_style)
