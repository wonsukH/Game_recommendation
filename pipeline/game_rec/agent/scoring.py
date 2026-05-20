"""Pure-numpy scoring helpers for rerank — no LLM or FAISS dependency.

Kept separate from retriever.py so tests can exercise the math without
having to import langchain_upstage / faiss.
"""

from __future__ import annotations

import numpy as np


def minmax(arr: np.ndarray) -> np.ndarray:
    """Map array to [0, 1]. Returns mid-value vector if range is degenerate.

    A safe replacement for sklearn MinMaxScaler when the input has zero
    range (all-equal); we want 0.5 there rather than NaN.
    """
    arr = np.asarray(arr, dtype=np.float32)
    lo, hi = float(arr.min()), float(arr.max())
    if hi <= lo:
        return np.full_like(arr, 0.5, dtype=np.float32)
    return (arr - lo) / (hi - lo)
