import pandas as pd
import numpy as np
import argparse
from pathlib import Path
import json
import shutil
from datetime import datetime
import hashlib


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 8: Metadata and versioning management")
    parser.add_argument(
        "--version", type=str,
        default="v1",
        help="Version tag (default: v1)"
    )
    parser.add_argument(
        "--params", type=str,
        default="params.json",
        help="Parameters JSON file path (default: params.json)"
    )
    parser.add_argument(
        "--output-dir", type=str,
        default="outputs",
        help="Output directory (default: outputs)"
    )
    parser.add_argument(
        "--backup", action="store_true",
        help="Create backup of existing files"
    )
    return parser.parse_args()


def collect_file_info(output_dir: Path) -> dict:
    """
    출력 디렉토리의 파일 정보 수집
    
    Args:
        output_dir: 출력 디렉토리 경로
    
    Returns:
        파일 정보 딕셔너리
    """
    file_info = {}
    
    for file_path in output_dir.glob("*"):
        if file_path.is_file():
            # 파일 해시 계산
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            
            # 파일 정보
            stat = file_path.stat()
            file_info[file_path.name] = {
                "size_bytes": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "md5_hash": file_hash
            }
    
    return file_info


def create_versioned_files(output_dir: Path, version: str, backup: bool = False):
    """
    버전이 포함된 파일명으로 복사
    
    Args:
        output_dir: 출력 디렉토리
        version: 버전 태그
        backup: 백업 생성 여부
    """
    # 백업 디렉토리 생성
    if backup:
        backup_dir = output_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(exist_ok=True)
        print(f"[INFO] 백업 디렉토리 생성: {backup_dir}")
    
    # 주요 파일들에 대해 버전 적용
    versioned_files = [
        "tag_vecs.npy",
        "game_vecs.npy", 
        "tag_beta.npy",
        "game_weight.npy",
        "X_game_tag_csr.npz",
        "tag_text_vecs.npy",
        "W_align.npy"
    ]
    
    for filename in versioned_files:
        file_path = output_dir / filename
        if file_path.exists():
            # 버전이 포함된 새 파일명
            name, ext = filename.rsplit('.', 1)
            versioned_name = f"{name}_{version}.{ext}"
            versioned_path = output_dir / versioned_name
            
            # 백업
            if backup:
                backup_path = backup_dir / filename
                shutil.copy2(file_path, backup_path)
                print(f"   - 백업: {filename} → {backup_path}")
            
            # 버전 파일 생성
            shutil.copy2(file_path, versioned_path)
            print(f"   - 버전 파일: {filename} → {versioned_name}")


def create_params_file(output_dir: Path, version: str, params_file: str):
    """
    파라미터 파일 생성
    
    Args:
        output_dir: 출력 디렉토리
        version: 버전 태그
        params_file: 파라미터 파일 경로
    """
    # 기존 파라미터 파일 로드 (있다면)
    params = {}
    if Path(params_file).exists():
        with open(params_file, 'r', encoding='utf-8') as f:
            params = json.load(f)
    
    # 현재 파라미터 업데이트
    current_params = {
        "version": version,
        "created_at": datetime.now().isoformat(),
        "parameters": {
            "embedding_dim": 128,
            "gamma": 0.5,
            "alpha": 0.5,
            "kappa": 1.0,
            "eta": 0.2,
            "lambda_reg": 1e-2
        },
        "model_info": {
            "sentence_transformer": "all-MiniLM-L6-v2",
            "ridge_alpha": 1.0
        }
    }
    
    # 기존 파라미터와 병합
    params.update(current_params)
    
    # 버전이 포함된 파라미터 파일 저장
    versioned_params_file = output_dir / f"params_{version}.json"
    with open(versioned_params_file, 'w', encoding='utf-8') as f:
        json.dump(params, f, ensure_ascii=False, indent=2)
    
    print(f"[INFO] 파라미터 파일 생성: {versioned_params_file}")


def create_metadata_summary(output_dir: Path, version: str):
    """
    메타데이터 요약 파일 생성
    
    Args:
        output_dir: 출력 디렉토리
        version: 버전 태그
    """
    # 파일 정보 수집
    file_info = collect_file_info(output_dir)
    
    # 통계 파일들 로드
    stats_files = list(output_dir.glob("*_stats.json"))
    stats_data = {}
    
    for stats_file in stats_files:
        try:
            with open(stats_file, 'r', encoding='utf-8') as f:
                stats_data[stats_file.name] = json.load(f)
        except Exception as e:
            print(f"[WARNING] {stats_file} 로드 실패: {e}")
    
    # 메타데이터 요약
    metadata = {
        "version": version,
        "created_at": datetime.now().isoformat(),
        "file_info": file_info,
        "statistics": stats_data,
        "summary": {
            "total_files": len(file_info),
            "total_size_mb": sum(info["size_bytes"] for info in file_info.values()) / (1024 * 1024),
            "file_types": {
                ext: len([f for f in file_info.keys() if f.endswith(ext)])
                for ext in ['.npy', '.npz', '.json', '.csv']
            }
        }
    }
    
    # 메타데이터 파일 저장
    metadata_file = output_dir / f"metadata_{version}.json"
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    print(f"[INFO] 메타데이터 요약 생성: {metadata_file}")
    
    # 요약 출력
    print(f"\n[INFO] 버전 {version} 요약:")
    print(f"   - 총 파일 수: {metadata['summary']['total_files']}")
    print(f"   - 총 크기: {metadata['summary']['total_size_mb']:.2f} MB")
    print(f"   - 파일 타입별:")
    for file_type, count in metadata['summary']['file_types'].items():
        if count > 0:
            print(f"     {file_type}: {count}개")


def main(version: str, params_file: str, output_dir: str, backup: bool):
    print(f"[INFO] 메타데이터 및 버전 관리 시작:")
    print(f"   - 버전: {version}")
    print(f"   - 출력 디렉토리: {output_dir}")
    print(f"   - 백업 생성: {backup}")
    
    output_path = Path(output_dir)
    if not output_path.exists():
        print(f"[ERROR] 출력 디렉토리가 존재하지 않습니다: {output_dir}")
        return
    
    # 1. 버전 파일 생성
    print(f"\n[INFO] 1. 버전 파일 생성 중...")
    create_versioned_files(output_path, version, backup)
    
    # 2. 파라미터 파일 생성
    print(f"\n[INFO] 2. 파라미터 파일 생성 중...")
    create_params_file(output_path, version, params_file)
    
    # 3. 메타데이터 요약 생성
    print(f"\n[INFO] 3. 메타데이터 요약 생성 중...")
    create_metadata_summary(output_path, version)
    
    print(f"\n✅ 버전 {version} 메타데이터 관리 완료!")


if __name__ == "__main__":
    args = _parse_args()
    main(args.version, args.params, args.output_dir, args.backup)
