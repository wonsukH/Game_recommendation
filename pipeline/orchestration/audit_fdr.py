"""BH-FDR across the reconstructable headline paired comparisons (audit concern:
~197 cells, no multiple-comparison correction). Same-run dirs share panel+split,
so cells are pairable by steamid. Wilcoxon signed-rank per comparison, then
Benjamini-Hochberg across the family. Read-only."""
from __future__ import annotations
import glob
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

REPO = Path(__file__).resolve().parents[2]
P4 = REPO / "experiments" / "p4_sweep"


def cell(d, name, metric="ndcg"):
    f = P4 / d / f"per_user_{name}.csv"
    if not f.exists():
        return None
    return pd.read_csv(f).set_index("steamid")[metric]


def cmp(d, a, b, metric="ndcg", label=None):
    A, B = cell(d, a, metric), cell(d, b, metric)
    if A is None or B is None:
        return None
    j = pd.concat([A, B], axis=1, join="inner").dropna()
    if len(j) < 8:
        return None
    diff = j.iloc[:, 0].values - j.iloc[:, 1].values
    if np.allclose(diff, 0):
        return None
    try:
        p = wilcoxon(diff).pvalue
    except ValueError:
        return None
    return {"label": label or f"{d}:{a}-{b}[{metric}]", "delta": float(diff.mean()),
            "n": len(j), "p": float(p)}


def main() -> int:
    fam = []
    # ranker-swap rationale (Stage B, pref=cap_a03_blend04, NDCG)
    for b in ["condcos", "rp3b", "ease_l50", "jaccard", "ppmi"]:
        fam.append(cmp("stageB", "cap_a03_blend04__userknn25", f"cap_a03_blend04__{b}", label=f"userknn25 vs {b} (Bcap, NDCG)"))
    # pref main effects across shared rankers (combo_expansion, NDCG)
    for rk in ["userknn25", "knnpd03"]:
        fam.append(cmp("combo_expansion", f"pvalue_eb__{rk}", f"pctl_game__{rk}", label=f"pvalue vs pctl @{rk} (NDCG)"))
        fam.append(cmp("combo_expansion", f"pvalue_eb__{rk}", f"dblq__{rk}", label=f"pvalue vs dblq @{rk} (NDCG)"))
    # S0 knob: knnpd03 vs userknn25 on pvalue (combo_expansion) — NDCG, recall, snips
    for mt in ["ndcg", "recall", "snips"]:
        fam.append(cmp("combo_expansion", "pvalue_eb__knnpd03", "pvalue_eb__userknn25", metric=mt, label=f"S0 vs S1 @pvalue ({mt})"))
    # R5 combos (should be ns): pvalue_comp_blend vs pvalue_eb
    fam.append(cmp("r5_combos", "pvalue_comp_blend__userknn25", "pvalue_eb__userknn25", label="R5 comp-blend vs pvalue (NDCG)"))

    fam = [f for f in fam if f]
    fam.sort(key=lambda x: x["p"])
    m = len(fam)
    # Benjamini-Hochberg
    for i, f in enumerate(fam, 1):
        f["q"] = min(1.0, f["p"] * m / i)
    # enforce monotonicity of q
    qmin = 1.0
    for f in reversed(fam):
        qmin = min(qmin, f["q"])
        f["q"] = qmin
    print(f"BH-FDR family size m={m}\n")
    print(f"{'comparison':44s} {'delta':>9s} {'n':>4s} {'p':>9s} {'q(BH)':>9s}  verdict")
    for f in fam:
        v = "SIG" if f["q"] < 0.05 else ("borderline" if f["q"] < 0.10 else "ns")
        print(f"{f['label']:44s} {f['delta']:+9.4f} {f['n']:4d} {f['p']:9.4f} {f['q']:9.4f}  {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
