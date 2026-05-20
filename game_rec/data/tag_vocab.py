import pandas as pd
import json
import unicodedata
import re
import argparse
from pathlib import Path

# 1. 태그 정규화 함수
def normalize_tag(tag: str) -> str:
    tag = tag.lower()  # 소문자
    tag = unicodedata.normalize("NFKC", tag)  # 유니코드 정규화
    tag = re.sub(r"\s+", " ", tag).strip()  # 다중 공백 제거
    tag = tag.replace("/", "-").replace(" ", "-")  # 하이픈 통일
    return tag

# 2. 별칭 매핑 사전 (원하면 추가)
alias_map = {
    "rogue like": "roguelike",
    "rogue-like": "roguelike",
    "single player": "single-player",
    "multi player": "multiplayer"
}

def apply_alias(tag: str) -> str:
    return alias_map.get(tag, tag)

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 1: Normalize game tags and create vocabulary")
    parser.add_argument(
        "--input", type=str,
        default=str(Path("outputs/steam_games_tags.csv")),
        help="Input CSV path (default: outputs/steam_games_tags.csv)"
    )
    parser.add_argument(
        "--output", type=str,
        default=str(Path("outputs/tag_vocab.json")),
        help="Output JSON path (default: outputs/tag_vocab.json)"
    )
    return parser.parse_args()


def main(input_csv: str, out_json: str):
    print(f"[INFO] 입력 파일 로드: {input_csv}")
    df = pd.read_csv(input_csv)

    all_tags = []
    for tags in df["tags"]:
        if pd.isna(tags):
            continue
        for tag in str(tags).split(","):
            tag = tag.strip()
            if not tag:
                continue
            norm = normalize_tag(tag)
            norm = apply_alias(norm)
            all_tags.append(norm)

    unique_tags = sorted(set(all_tags))

    vocab = {
        "tags": unique_tags,
        "alias_map": alias_map,
        "total_tags": len(all_tags),
        "unique_tags": len(unique_tags)
    }

    # 출력 폴더 생성
    out_path = Path(out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(unique_tags)}개 고유 태그 저장 완료 → {out_json}")
    print(f"   총 태그 수: {len(all_tags):,}개")


if __name__ == "__main__":
    args = _parse_args()
    main(args.input, args.output)
