"""릴리스 도구 — 검증된 산출물을 버전으로 굳히고, 비교하고, 승격한다.

지금 파이프라인은 산출물을 스크래치에 만들고 거기서 끝난다. 배포된 앱은 그것을
쳐다보지 않는다. 이 모듈이 그 사이를 잇되, 파일을 서비스 경로에 덮어쓰는 방식은
쓰지 않는다. 덮어쓰면 되돌릴 수가 없기 때문이다.

대신 업계에서 쓰는 모양을 따른다.

  1. stage     검증된 산출물을 버전 디렉터리로 복사하고 매니페스트를 만든다. 덮어쓰지 않는다.
  2. compare   새 버전과 지금 프로덕션 버전을 같은 평가 패널 점수로 비교한다 (champion/challenger).
  3. promote   production.json 의 버전 문자열을 바꾼다. 파일 이동이 아니다.
  4. rollback  이전 버전으로 되돌린다.

승격이 포인터 한 줄이라 롤백도 한 줄이다. 그것이 이 구조의 요점이다.

사용:
    python airflow_lab/release.py stage    --version 2026-08-03T12:00
    python airflow_lab/release.py compare  --version 2026-08-03T12:00
    python airflow_lab/release.py promote  --version 2026-08-03T12:00
    python airflow_lab/release.py rollback
    python airflow_lab/release.py status
"""

from __future__ import annotations

import argparse
import os
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent
REPO = LAB.parent
RELEASES = LAB / "releases"
POINTER = RELEASES / "production.json"

# 파이프라인이 만든 것을 읽어오는 곳. 컨테이너 안에서는 스크래치 오버레이가 겹쳐 있다.
SRC_SERVING = Path(os.environ.get("RELEASE_SRC_SERVING", REPO / "serving" / "data"))
SRC_VALIDATE = Path(os.environ.get("RELEASE_SRC_VALIDATE", REPO / "experiments" / "p6_ood" / "p5_validate.json"))
SRC_EXTRACT = Path(os.environ.get("RELEASE_SRC_EXTRACT", REPO / "outputs" / "p5" / "extract_stats.json"))

# 릴리스에 담는 것. B_topk.npz 는 345MB라 복사하지 않고 해시만 기록한다.
FILES = [
    "catalog.json", "index_maps.json", "game_quality.json",
    "game_popularity.npy", "X_game_tag_csr.npz", "steam_games_tags.csv",
    "ease/items.npy", "ease/avg_pt.npy", "ease/pt_ecdf.npz", "ease/meta.json",
]
HASH_ONLY = ["ease/B_topk.npz"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       cwd=REPO).decode().strip()
    except Exception:
        return "unknown"


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_pointer() -> dict:
    return read_json(POINTER) or {"version": None, "history": []}


def manifest_of(version: str) -> dict | None:
    return read_json(RELEASES / version / "manifest.json")


def cmd_stage(args) -> int:
    version = args.version or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M")
    dest = RELEASES / version
    if dest.exists() and not args.force:
        print(f"이미 있는 버전이다: {version}\n"
              f"릴리스는 덮어쓰지 않는다. 다른 --version 을 쓰거나 --force 를 준다.")
        return 1
    dest.mkdir(parents=True, exist_ok=True)

    files, missing = {}, []
    for rel in FILES:
        src = SRC_SERVING / rel
        if not src.exists():
            missing.append(rel)
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        files[rel] = {"bytes": out.stat().st_size, "sha256": sha256(out)}
    for rel in HASH_ONLY:
        src = SRC_SERVING / rel
        if not src.exists():
            missing.append(rel)
            continue
        files[rel] = {"bytes": src.stat().st_size, "sha256": sha256(src),
                      "copied": False,
                      "note": "크기 때문에 복사하지 않는다. HF 업로드 대상."}
    if missing:
        print("빠진 산출물:", ", ".join(missing))
        if not args.allow_missing:
            shutil.rmtree(dest, ignore_errors=True)
            return 1

    gates = read_json(SRC_VALIDATE)
    manifest = {
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "gates": gates,
        "ease_meta": read_json(SRC_SERVING / "ease" / "meta.json"),
        "extract": read_json(SRC_EXTRACT),
        "files": files,
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"staged {version}")
    print(f"  파일 {len(files)}개, git {manifest['git_sha'][:12]}")
    if gates:
        print(f"  게이트 exact={gates.get('g_a', {}).get('exact')} "
              f"pass={gates.get('g_a', {}).get('pass')}")
    print(f"  경로 {dest}")
    return 0


def _score(m: dict | None) -> dict:
    """매니페스트에서 비교 가능한 값만 뽑는다."""
    if not m:
        return {}
    g = (m.get("gates") or {}).get("g_a") or {}
    e = m.get("ease_meta") or {}
    x = m.get("extract") or {}
    return {
        "exact_ndcg": g.get("exact"),
        "sparse_ndcg": g.get("sparse"),
        "truncation": g.get("diff"),
        "jaccard": g.get("jaccard"),
        "gate_pass": g.get("pass"),
        "graph_users": e.get("n_graph_users"),
        "items": e.get("n_items"),
        "usable_users": x.get("n_users"),
        "pool": x.get("pool_size"),
    }


def cmd_compare(args) -> int:
    """champion(현재 프로덕션) 대 challenger(새 버전)."""
    challenger = args.version
    champion = load_pointer().get("version")
    cm, hm = manifest_of(challenger), manifest_of(champion) if champion else None
    if cm is None:
        print(f"버전을 찾을 수 없다: {challenger}")
        return 1

    c, h = _score(cm), _score(hm)
    print(f"champion   {champion or '(없음 — 첫 릴리스)'}")
    print(f"challenger {challenger}\n")
    print(f"{'지표':<14}{'champion':>14}{'challenger':>14}{'차이':>12}")
    for k in ("exact_ndcg", "sparse_ndcg", "truncation", "jaccard",
              "graph_users", "items", "usable_users", "pool"):
        a, b = h.get(k), c.get(k)
        d = ""
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            d = f"{b - a:+.4f}" if isinstance(b, float) else f"{b - a:+,}"
        print(f"{k:<14}{str(a):>14}{str(b):>14}{d:>12}")

    if not c.get("gate_pass"):
        print("\n판정: 승격 불가. 새 버전이 자체 게이트를 통과하지 못했다.")
        return 1
    if h.get("exact_ndcg") is None:
        print("\n판정: 첫 릴리스라 비교 대상이 없다. 게이트는 통과했다.")
        return 0

    delta = c["exact_ndcg"] - h["exact_ndcg"]
    print(f"\nexact nDCG 차이 {delta:+.4f} (허용 {-args.tolerance:+.4f})")
    print("\n주의: 두 값은 같은 동결 패널로 잰 것이지만 추천 대상 풀이 다르다"
          f" ({h.get('pool')} -> {c.get('pool')}). 문제 난이도가 완전히 같지는 않다.")
    if delta < -args.tolerance:
        print("판정: 회귀. 승격을 권하지 않는다.")
        return 1 if args.fail_on_regression else 0
    print("판정: 승격 가능.")
    return 0


def cmd_promote(args) -> int:
    if manifest_of(args.version) is None:
        print(f"버전을 찾을 수 없다: {args.version}")
        return 1
    ptr = load_pointer()
    prev = ptr.get("version")
    ptr["history"] = ([{"version": prev, "until": datetime.now(timezone.utc)
                        .isoformat(timespec="seconds")}] if prev else []) \
        + ptr.get("history", [])
    ptr["version"] = args.version
    ptr["promoted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    RELEASES.mkdir(parents=True, exist_ok=True)
    POINTER.write_text(json.dumps(ptr, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"프로덕션 {prev or '(없음)'} -> {args.version}")
    print("되돌리려면: python airflow_lab/release.py rollback")
    return 0


def cmd_rollback(args) -> int:
    ptr = load_pointer()
    hist = ptr.get("history") or []
    if not hist:
        print("되돌릴 이전 버전이 없다.")
        return 1
    target = hist[0]["version"]
    ptr["history"] = hist[1:]
    cur = ptr.get("version")
    ptr["version"] = target
    ptr["promoted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ptr["rolled_back_from"] = cur
    POINTER.write_text(json.dumps(ptr, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"롤백 {cur} -> {target}")
    return 0


def cmd_status(args) -> int:
    ptr = load_pointer()
    versions = sorted(p.name for p in RELEASES.glob("*") if (p / "manifest.json").exists())
    print(f"프로덕션 : {ptr.get('version') or '(없음)'}")
    if ptr.get("promoted_at"):
        print(f"승격 시각 : {ptr['promoted_at']}")
    print(f"보유 버전 : {len(versions)}개")
    for v in versions:
        s = _score(manifest_of(v))
        mark = " <- 프로덕션" if v == ptr.get("version") else ""
        print(f"  {v}  exact={s.get('exact_ndcg')} users={s.get('usable_users')}{mark}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("stage", help="검증된 산출물을 버전으로 굳힌다")
    p.add_argument("--version")
    p.add_argument("--force", action="store_true")
    p.add_argument("--allow-missing", action="store_true")
    p.set_defaults(fn=cmd_stage)

    p = sub.add_parser("compare", help="현재 프로덕션과 비교한다")
    p.add_argument("--version", required=True)
    p.add_argument("--tolerance", type=float, default=0.005)
    p.add_argument("--fail-on-regression", action="store_true")
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser("promote", help="포인터를 이 버전으로 바꾼다")
    p.add_argument("--version", required=True)
    p.set_defaults(fn=cmd_promote)

    p = sub.add_parser("rollback", help="이전 버전으로 되돌린다")
    p.set_defaults(fn=cmd_rollback)

    p = sub.add_parser("status", help="현재 프로덕션과 보유 버전")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
