"""Statistical helpers for the experiment driver.

n is small (30 hand queries; a few hundred auto co-play seeds) and the
metric distributions are not normal, so we lean on the bootstrap rather
than t-tests:

- `bootstrap_ci`: 95% CI of a metric's mean over the query set.
- `paired_bootstrap_diff`: CI of the mean per-query difference between two
  variants evaluated on the SAME queries (the correct test for "does B
  beat A"). If the CI excludes 0, the difference is significant.
- `wilcoxon_p`: non-parametric paired significance as a secondary check.

All bootstraps take an explicit seed so a run is reproducible.
"""

from __future__ import annotations

import numpy as np


def bootstrap_ci(
    values, B: int = 1000, seed: int = 42, alpha: float = 0.05
) -> dict[str, float]:
    """Mean + (1-alpha) percentile CI of `values` via resampling."""
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, v.size, size=(B, v.size))
    means = v[idx].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return {"mean": float(v.mean()), "lo": float(lo), "hi": float(hi), "n": int(v.size)}


def paired_bootstrap_diff(
    a, b, B: int = 1000, seed: int = 42, alpha: float = 0.05
) -> dict[str, float]:
    """CI of mean(b - a) over paired per-query values.

    Returns mean_diff, lo, hi and `significant` (CI excludes 0). a, b must
    be aligned arrays (same query order). NaNs in either are dropped pairwise.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    mask = np.isfinite(a) & np.isfinite(b)
    d = b[mask] - a[mask]
    if d.size == 0:
        return {"mean_diff": 0.0, "lo": 0.0, "hi": 0.0, "significant": False, "n": 0}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, d.size, size=(B, d.size))
    means = d[idx].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return {
        "mean_diff": float(d.mean()),
        "lo": float(lo),
        "hi": float(hi),
        "significant": bool(lo > 0 or hi < 0),
        "n": int(d.size),
    }


def wilcoxon_p(a, b) -> float:
    """Two-sided Wilcoxon signed-rank p-value (paired). NaN if undefined."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    mask = np.isfinite(a) & np.isfinite(b)
    d = b[mask] - a[mask]
    if d.size == 0 or np.allclose(d, 0):
        return float("nan")
    try:
        from scipy.stats import wilcoxon
        return float(wilcoxon(d).pvalue)
    except Exception:
        return float("nan")
