"""P6 FDR — BH over the PRE-REGISTERED headline family (P6_PREREG.md v3 A7,
m=8, frozen-graph run). Everything else in the run is descriptive and must not
enter this family. Reuses the audit_fdr machinery shape (Wilcoxon signed-rank
per pair, Benjamini-Hochberg across the family) + paired-bootstrap CIs.

Usage: python -m pipeline.orchestration.p6_fdr --run confirm_frozen
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.evaluation.stats import paired_bootstrap_diff  # noqa: E402
from pipeline.orchestration.p6_common import P6_DIR  # noqa: E402

# (label, slot_a, slot_b, metric, hypothesis) — delta = a - b
FAMILY = [
    ("H1: S5b(ease100) vs S1(userknn) [NDCG]", "S5b", "S1", "ndcg", "H1"),
    ("H1: S5b(ease100) vs S4(condcos) [NDCG]", "S5b", "S4", "ndcg", "H1"),
    ("H2: S1(pvalue) vs S2(pctl) [NDCG]", "S1", "S2", "ndcg", "H2"),
    ("H2: S1(pvalue) vs S2(pctl) [wl]", "S1", "S2", "wl_recall", "H2"),
    ("H3: S0b(knnpd03) vs S1 [wl]", "S0b", "S1", "wl_recall", "H3"),
    ("H3: S0a(knnpd02) vs S1 [wl]", "S0a", "S1", "wl_recall", "H3"),
    ("harm: S0b(knnpd03) vs S1 [NDCG]", "S0b", "S1", "ndcg", "harm"),
    ("B-axis: S5b(ease100) vs S1 [wl]", "S5b", "S1", "wl_recall", "B"),
]


def cell(run_dir: Path, slot: str, metric: str) -> pd.Series:
    return (pd.read_csv(run_dir / f"per_user_{slot}.csv")
            .set_index("steamid")[metric])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="run dir name under experiments/p6_ood")
    args = ap.parse_args()
    run_dir = P6_DIR / args.run
    if not run_dir.exists():
        print(f"no such run dir: {run_dir}")
        return 1

    fam = []
    for label, a, b, metric, hyp in FAMILY:
        A, B = cell(run_dir, a, metric), cell(run_dir, b, metric)
        j = pd.concat([A, B], axis=1, join="inner").dropna()
        diff = j.iloc[:, 0].values - j.iloc[:, 1].values
        if len(j) < 8 or np.allclose(diff, 0):
            fam.append({"label": label, "hyp": hyp, "delta": float(np.mean(diff))
                        if len(j) else np.nan, "n": len(j), "p": np.nan})
            continue
        boot = paired_bootstrap_diff(j.iloc[:, 1].values, j.iloc[:, 0].values)
        fam.append({"label": label, "hyp": hyp, "delta": boot["mean_diff"],
                    "ci_lo": boot["lo"], "ci_hi": boot["hi"], "n": len(j),
                    "p": float(wilcoxon(diff).pvalue)})

    tested = sorted([f for f in fam if np.isfinite(f.get("p", np.nan))],
                    key=lambda x: x["p"])
    m = len(tested)
    for i, f in enumerate(tested, 1):
        f["q"] = min(1.0, f["p"] * m / i)
    qmin = 1.0
    for f in reversed(tested):
        qmin = min(qmin, f["q"])
        f["q"] = qmin

    print(f"P6 pre-registered family (A7) — run={args.run}, m={m}\n")
    print(f"{'comparison':44s} {'delta':>9s} {'95% CI':>19s} {'n':>5s} "
          f"{'p':>8s} {'q(BH)':>8s}  verdict")
    for f in fam:
        if not np.isfinite(f.get("p", np.nan)):
            print(f"{f['label']:44s} {'-':>9s} {'-':>19s} {f['n']:5d} "
                  f"{'-':>8s} {'-':>8s}  UNTESTABLE")
            continue
        v = "SIG" if f["q"] < 0.05 else ("borderline" if f["q"] < 0.10 else "ns")
        ci = f"[{f['ci_lo']:+.4f},{f['ci_hi']:+.4f}]"
        print(f"{f['label']:44s} {f['delta']:+9.4f} {ci:>19s} {f['n']:5d} "
              f"{f['p']:8.4f} {f['q']:8.4f}  {v}")

    pd.DataFrame(fam).to_csv(run_dir / "fdr.csv", index=False)
    print(f"\nsaved -> {run_dir / 'fdr.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
