"""Sync FE pipeline artifacts from outputs/ to st_app/data/.

The Streamlit app reads from st_app/data/, which is a separate copy of
the artifacts produced by the FE pipeline in outputs/. This script
brings the app's copy up to date with the latest pipeline output.

Whitelist-based: only the files the app actually needs are synced.
Versioned files (`*_v1.npy`, `metadata_v1.json` etc.) are skipped — they
are captured snapshots, not live artifacts.

Usage:
    python scripts/sync_data.py
    python scripts/sync_data.py --source outputs --target st_app/data
    python scripts/sync_data.py --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from utils.logging import get_logger  # noqa: E402

log = get_logger("scripts.sync_data")


# Files the live Streamlit app needs at runtime. Versioned siblings
# (*_v1.*) and one-off stats are intentionally excluded.
WHITELIST: tuple[str, ...] = (
    "tag_vocab.json",
    "index_maps.json",
    "steam_games_tags.csv",
    "tag_vecs.npy",
    "game_vecs.npy",
    "tag_text_vecs.npy",
    "W_align.npy",
    "X_game_tag_csr.npz",
    "faiss_index.faiss",
)


def _needs_copy(src: Path, dst: Path) -> bool:
    if not dst.exists():
        return True
    src_stat = src.stat()
    dst_stat = dst.stat()
    if src_stat.st_size != dst_stat.st_size:
        return True
    # mtime tolerance of 1s to avoid FS-precision false positives
    return src_stat.st_mtime - dst_stat.st_mtime > 1.0


def sync(source: Path, target: Path, dry_run: bool = False) -> int:
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    missing: list[str] = []

    for name in WHITELIST:
        src = source / name
        if not src.exists():
            missing.append(name)
            continue
        dst = target / name
        if _needs_copy(src, dst):
            if dry_run:
                log.info("[dry-run] would copy %s -> %s", src, dst)
            else:
                shutil.copy2(src, dst)
                log.info("copied %s (%.1f KB)", name, src.stat().st_size / 1024)
            copied += 1
        else:
            log.debug("up-to-date: %s", name)

    if missing:
        log.warning("missing from source (run the FE pipeline?): %s", ", ".join(missing))

    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=REPO_ROOT / "outputs",
        help="FE pipeline output directory (default: <repo>/outputs)",
    )
    parser.add_argument(
        "--target", type=Path, default=REPO_ROOT / "st_app" / "data",
        help="Streamlit app data directory (default: <repo>/st_app/data)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be copied without touching files.",
    )
    args = parser.parse_args()

    log.info("sync source=%s -> target=%s", args.source, args.target)
    copied = sync(args.source, args.target, dry_run=args.dry_run)
    log.info("done. %d file(s) %s.", copied, "would be copied" if args.dry_run else "copied")


if __name__ == "__main__":
    main()
