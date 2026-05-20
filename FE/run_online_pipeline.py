#!/usr/bin/env python3
"""
온라인 서빙 파이프라인 실행 스크립트
Step 10-15를 순차적으로 실행합니다.
"""

import subprocess
import sys
import argparse
from pathlib import Path


def run_command(command, step_name):
    """명령어 실행 및 에러 처리"""
    print(f"\n{'='*50}")
    print(f"🚀 {step_name} 실행 중...")
    print(f"명령어: {command}")
    print(f"{'='*50}")
    
    try:
        result = subprocess.run(command, shell=True, check=True, 
                              capture_output=True, text=True, encoding='utf-8')
        print("✅ 성공!")
        if result.stdout:
            print("출력:")
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 실패: {e}")
        if e.stdout:
            print("표준 출력:")
            print(e.stdout)
        if e.stderr:
            print("오류 출력:")
            print(e.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="온라인 서빙 파이프라인 실행")
    parser.add_argument("--input", type=str, default="user_intent.json",
                       help="사용자 의도 파일 (기본값: user_intent.json)")
    parser.add_argument("--explanation-style", type=str, default="concise",
                       choices=["concise", "detailed", "casual"],
                       help="설명 스타일 (기본값: concise)")
    parser.add_argument("--top-n", type=int, default=500,
                       help="ANN 검색 후보 수 (기본값: 500)")
    parser.add_argument("--k", type=int, default=10,
                       help="최종 추천 수 (기본값: 10)")
    parser.add_argument("--lambda", type=float, default=0.5,
                       help="MMR 람다 파라미터 (기본값: 0.5)")
    
    args = parser.parse_args()
    
    # 입력 파일 확인
    if not Path(args.input).exists():
        print(f"❌ 입력 파일이 없습니다: {args.input}")
        print("사용 가능한 파일들:")
        for file in ["user_intent.json", "user_intent_vibe.json", "user_intent_hybrid.json"]:
            if Path(file).exists():
                print(f"  - {file}")
        return 1
    
    print("🎮 온라인 서빙 파이프라인 시작!")
    print(f"📁 입력 파일: {args.input}")
    print(f"💬 설명 스타일: {args.explanation_style}")
    print(f"🔍 검색 후보 수: {args.top_n}")
    print(f"🎯 최종 추천 수: {args.k}")
    print(f"⚖️ MMR 람다: {args.lambda}")
    
    # Step 10: LLM 의도 파싱
    if not run_command(f"python step10.py --input {args.input}", "Step 10: LLM 의도 파싱"):
        return 1
    
    # Step 11: 쿼리 벡터 생성
    if not run_command("python step11.py", "Step 11: 쿼리 벡터 생성"):
        return 1
    
    # Step 12: 후보 검색
    if not run_command(f"python step12.py --top-n {args.top_n}", "Step 12: 후보 검색"):
        return 1
    
    # Step 13: 필터 & 스코어링
    if not run_command("python step13.py", "Step 13: 필터 & 스코어링"):
        return 1
    
    # Step 14: 다양성 선택
    if not run_command(f"python step14.py --k {args.k} --lambda {args.lambda}", "Step 14: 다양성 선택"):
        return 1
    
    # Step 15: LLM 설명 생성
    if not run_command(f"python step15.py --explanation-style {args.explanation_style}", "Step 15: LLM 설명 생성"):
        return 1
    
    print(f"\n{'='*50}")
    print("🎉 온라인 서빙 파이프라인 완료!")
    print(f"{'='*50}")
    print("📊 결과 파일:")
    print("  - outputs/final_recommendations.json (최종 추천 결과)")
    print("  - outputs/diverse_recommendations.json (다양성 선택 결과)")
    print("  - outputs/scored_candidates.json (스코어링 결과)")
    print("  - outputs/candidates.json (후보 검색 결과)")
    print("  - outputs/query_vector.npy (쿼리 벡터)")
    print("  - outputs/parsed_intent.json (파싱된 의도)")
    
    # 최종 결과 확인
    final_result_path = Path("outputs/final_recommendations.json")
    if final_result_path.exists():
        print(f"\n✅ 최종 추천 결과가 생성되었습니다: {final_result_path}")
        print("📖 README_ONLINE_SERVING.md 파일을 참고하여 결과를 확인하세요.")
    else:
        print("❌ 최종 결과 파일이 생성되지 않았습니다.")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
