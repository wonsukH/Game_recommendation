"""I/O helpers reused across the offline FE pipeline and the online retriever.

The offline pipeline (FE/step*.py) and the online retriever (st_app/rag/
retriever.py) load the same artifacts — index maps, tag vocabulary,
sparse Game x Tag matrix, dense vectors. Centralising these calls keeps
the conversion conventions (e.g. int keys for JSON-loaded dicts, float32
for vectors) in one place.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix, load_npz


IndexMaps = dict[str, Any]


def load_index_maps(path: str | Path) -> IndexMaps:
    """Load outputs/index_maps.json and coerce numeric keys back to int.

    JSON forces string keys, but downstream code indexes by int row /
    column ids. Returns a dict with keys: tag2idx, idx2tag, appid2row,
    row2appid (plus any extra fields written by step2).
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {
        "tag2idx": raw["tag2idx"],
        "idx2tag": {int(k): v for k, v in raw["idx2tag"].items()},
        "appid2row": {int(k): v for k, v in raw["appid2row"].items()},
        "row2appid": {int(k): v for k, v in raw["row2appid"].items()},
        **{k: v for k, v in raw.items()
           if k not in {"tag2idx", "idx2tag", "appid2row", "row2appid"}},
    }


def load_tag_vocab(path: str | Path) -> list[str]:
    """Return the ordered tag list from outputs/tag_vocab.json."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["tags"]


def load_csr(path: str | Path) -> csr_matrix:
    """Load the Game x Tag sparse matrix as CSR."""
    return load_npz(str(path))


def load_vectors(path: str | Path, dtype: str = "float32") -> np.ndarray:
    """Load a .npy and cast to the given dtype (default float32 for FAISS)."""
    return np.load(str(path)).astype(dtype)


def save_stats(stats: dict, path: str | Path) -> None:
    """Write a stats dict to JSON, creating parent dirs if needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
