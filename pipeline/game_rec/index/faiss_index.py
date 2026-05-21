"""Build a FAISS IndexFlatL2 over game vectors.

Reads game_vecs.npy and writes faiss_index.faiss alongside it. Defaults
point at outputs/ (where the training stages write); sync_data.py later
promotes the index to serving/data. Both paths are overridable via CLI
flags or function arguments.

Windows + non-ASCII path note: faiss-cpu's FileIOWriter uses the narrow
ANSI API and chokes on paths with characters outside the system code
page (e.g. Korean). We write to a tempdir (ASCII under user profile)
and then move the file into place.
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

import faiss

from pipeline.game_rec.io import load_vectors
from pipeline.game_rec.log import get_logger

log = get_logger("game_rec.index.faiss_index")

REPO_ROOT = Path(__file__).resolve().parents[3]
# Training stages write to outputs/. sync_data.py promotes to serving/data
# at the end. Defaulting here to outputs/ keeps faiss_index in lockstep
# with the newly-trained game_vecs.npy in the same dir.
DEFAULT_DATA_DIR = REPO_ROOT / "outputs"


def _safe_write_index(index, target_path: Path) -> None:
    """faiss.write_index that survives non-ASCII paths on Windows."""
    target_str = str(target_path)
    try:
        target_str.encode("ascii")
        faiss.write_index(index, target_str)
        return
    except UnicodeEncodeError:
        pass

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "faiss_index.faiss"
        faiss.write_index(index, str(tmp_path))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            target_path.unlink()
        shutil.move(str(tmp_path), target_str)
        log.info("wrote via tempdir (non-ASCII path workaround)")


def build_index(vectors_path: Path, index_path: Path) -> None:
    if not vectors_path.exists():
        log.error("vectors file not found: %s", vectors_path)
        return

    game_vectors = load_vectors(vectors_path)
    dim = game_vectors.shape[1]
    log.info("loaded %d game vectors of dim %d", game_vectors.shape[0], dim)

    index = faiss.IndexFlatL2(dim)
    index.add(game_vectors)
    log.info("index built with %d vectors, writing to %s", index.ntotal, index_path)

    index_path.parent.mkdir(parents=True, exist_ok=True)
    _safe_write_index(index, index_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build FAISS IndexFlatL2 over game vectors")
    parser.add_argument(
        "--vectors", type=Path,
        default=DEFAULT_DATA_DIR / "game_vecs.npy",
        help="Input game vectors .npy",
    )
    parser.add_argument(
        "--output", type=Path,
        default=DEFAULT_DATA_DIR / "faiss_index.faiss",
        help="Output FAISS index path",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    build_index(args.vectors, args.output)


if __name__ == "__main__":
    main()
