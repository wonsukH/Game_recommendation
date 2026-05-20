"""Build a FAISS IndexFlatL2 over game vectors.

Reads game_vecs.npy and writes faiss_index.faiss alongside it. Defaults
point at st_app/data/ (the live app data dir) but both paths are
overridable via CLI flags or function arguments.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import faiss

from game_rec.io import load_vectors
from game_rec.log import get_logger

log = get_logger("game_rec.index.faiss_index")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "st_app" / "data"


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
    faiss.write_index(index, str(index_path))


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
