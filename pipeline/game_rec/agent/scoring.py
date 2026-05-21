"""Pure-numpy scoring helpers for rerank — no LLM or FAISS dependency.

Kept separate from retriever.py so tests can exercise the math without
having to import langchain_google_genai / faiss.
"""

from __future__ import annotations

import math

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


def sigmoid_modifier(slider: float, k: float = 3.0) -> float:
    """Map a 0-10 slider value to a signed modifier in (-1, +1).

    Slider 5 -> 0   (neutral, signal has no effect)
    Slider 10 -> ~+1 (full positive — push niche/diverse/serendipitous up)
    Slider 0  -> ~-1 (full negative — push popular/similar/expected up)

    Sigmoid (not linear) so that small moves near the center barely change
    behavior (4 vs 6 ≈ same) while extreme values are decisive (9 vs 10
    still matters). k controls steepness; k=3 gives a gentle S-curve.

    Used by rerank to interpret novelty/diversity/serendipity sliders.
    `relevance` is NOT signed — it stays as a positive importance weight
    (no one wants "less relevant" results).
    """
    if not math.isfinite(slider):
        return 0.0
    s = (slider - 5.0) / 5.0  # linear -1..+1
    return 2.0 / (1.0 + math.exp(-k * s)) - 1.0
