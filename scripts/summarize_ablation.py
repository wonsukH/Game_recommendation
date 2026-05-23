"""Summarize llm_vs_system ablation runs.

Reads outputs/llm_vs_system_<label>.csv for each variant, aggregates
metrics (overall + vibe-category-only), writes CSV + Markdown summary.

Usage:
    python scripts/summarize_ablation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = REPO_ROOT / "outputs"

# Order matters for the table: baseline first, then variants
VARIANTS = [
    ("pre_m9a", "옛 W_align (M9.A 전), α=0.7, η=0.2 — 비교 baseline"),
    ("a07",     "M9.A 새 W_align, α=0.7, η=0.2 — M9.A baseline"),
    ("a05",     "M9.A W_align, α=0.5 (Item2Vec 비중 ↑)"),
    ("a09",     "M9.A W_align, α=0.9 (PPMI 비중 ↑)"),
    ("a10",     "M9.A W_align, α=1.0 (PPMI only, Item2Vec OFF)"),
    ("eta0",    "M9.A W_align, η=0 (β-축 OFF) — M9.D 후보"),
    ("final",   "4-axis: M9.A revert, α=1.0, η=0 (Item2Vec/β-축 OFF) — 옛 system"),
    ("final3",  "★ 3-axis (M11): Serendipity slider 제거. nov=1 (입문자 보정)"),
]

METRICS = [
    "overlap@5",
    "llm_existence_rate",
    "our_avg_pop",
    "llm_avg_pop",
    "our_ild",
    "llm_ild",
]


def aggregate(csv_path: Path) -> dict | None:
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    row: dict = {"n_queries": len(df)}
    for m in METRICS:
        row[m] = float(df[m].mean()) if m in df.columns else float("nan")

    # Vibe category only (M9.A's main target)
    if "category" in df.columns:
        vibe = df[df["category"].astype(str).str.startswith("vibe")]
        row["vibe_n"] = len(vibe)
        if len(vibe) > 0:
            row["vibe_overlap@5"] = float(vibe["overlap@5"].mean())
            row["vibe_our_avg_pop"] = float(vibe["our_avg_pop"].mean())
            row["vibe_our_ild"] = float(vibe["our_ild"].mean())
        else:
            row["vibe_overlap@5"] = row["vibe_our_avg_pop"] = row["vibe_our_ild"] = float("nan")
    return row


def main() -> int:
    rows = []
    for label, desc in VARIANTS:
        csv_path = OUTPUTS / f"llm_vs_system_{label}.csv"
        agg = aggregate(csv_path)
        if agg is None:
            print(f"[SKIP] missing: {csv_path}")
            continue
        rows.append({"label": label, "description": desc, **agg})

    if not rows:
        print("[ERROR] no ablation CSVs found")
        return 1

    summary = pd.DataFrame(rows)
    cols_order = (
        ["label", "description", "n_queries"]
        + METRICS
        + ["vibe_n", "vibe_overlap@5", "vibe_our_avg_pop", "vibe_our_ild"]
    )
    summary = summary[[c for c in cols_order if c in summary.columns]]

    out_csv = OUTPUTS / "ablation_summary.csv"
    out_md = OUTPUTS / "ablation_summary.md"
    summary.to_csv(out_csv, index=False)

    # Markdown
    md_lines = [
        "# Ablation Summary",
        "",
        "M9.A (description-augmented W_align) + M9.C (`ensemble_alpha`) + M9.D (`eta`) ablation.",
        "30 query 평가 (input 프리셋), `pipeline/orchestration/llm_vs_system.py`.",
        "",
        "## Overall metrics (전체 30 query 평균)",
        "",
        summary[
            ["label", "description"] + ["n_queries"] + METRICS
        ].to_markdown(index=False, floatfmt=",.4f"),
        "",
        "## Vibe category only (M9.A의 직접 target)",
        "",
        summary[
            ["label", "description"]
            + ["vibe_n", "vibe_overlap@5", "vibe_our_avg_pop", "vibe_our_ild"]
        ].to_markdown(index=False, floatfmt=",.4f"),
        "",
        "## 해석 가이드",
        "",
        "- `pre_m9a` vs `a07`: M9.A (W_align 보강)의 단독 효과. vibe 카테고리의 `vibe_our_avg_pop` 상승하면 mainstream 추천 강화.",
        "- `a07` vs `a05/a09/a10`: ensemble_alpha 효과 (PPMI 비중). similar/hybrid 모드 영향 큼.",
        "- `a10`이 best면 → Item2Vec 자체가 noise. 비활성화 권장.",
        "- `eta0` vs `a07`: β-축 (`tag_effects` Ridge) 가치 검증. 비슷하면 `eta=0` 채택.",
    ]
    out_md.write_text("\n".join(md_lines), encoding="utf-8")

    print(summary.to_string(index=False))
    print(f"\nSaved: {out_csv}")
    print(f"Saved: {out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
