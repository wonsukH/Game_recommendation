"""Phase 1 experiment driver — does the structure/embedding earn its keep?

Question (similar mode = "ask by game"): on NON-CIRCULAR co-play ground
truth, does PPMI+SVD beat a plain vote-weighted tag-cosine baseline? And
does anything beat popularity?

Pipeline:
  1. Phase 0: validate the metrics on anchor systems -> metric_trust_report.md
  2. Phase 1: run the variant ladder over the co-play seeds, evaluate the RAW
     retrieval ranking (rerank is UX reordering, evaluated separately) with
     recall@k / ndcg@k, plus distinctiveness (overlap) and coverage/gini.
  3. Paired bootstrap between adjacent rungs -> KEEP / SIMPLIFY / DROP, with
     null/negative results reported honestly.

Everything is written under experiments/<run_id>/ (append-only); no
production artifact is touched. Runs on numpy/scipy/pandas only (no faiss /
Gemini) — the SVD retriever is an exact pure-numpy stand-in for the FAISS
IndexFlatL2-over-unit-vectors search.

Usage:
    python -m pipeline.orchestration.experiment
    python -m pipeline.orchestration.experiment --limit 50 --run-id smoke
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.agent.baselines import (  # noqa: E402
    Catalog, RandomRetriever, PopularityRetriever, TagSetRetriever,
    TagCosineRetriever, VecSimilarRetriever,
)
from pipeline.game_rec.evaluation import metric_validation as mv  # noqa: E402
from pipeline.game_rec.evaluation.metrics import (  # noqa: E402
    overlap_at_k, catalog_coverage, gini_coefficient,
    recall_at_k, popularity_percentile,
)
from pipeline.game_rec.evaluation.stats import bootstrap_ci, paired_bootstrap_diff, wilcoxon_p
from pipeline.game_rec.evaluation.run_logger import RunLogger, fingerprint  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.experiment")


def decision(rec_diff: dict, ndcg_diff: dict) -> str:
    """KEEP/SIMPLIFY/DROP from paired bootstrap on recall + ndcg."""
    r_sig, n_sig = rec_diff["significant"], ndcg_diff["significant"]
    r_pos, n_pos = rec_diff["mean_diff"] > 0, ndcg_diff["mean_diff"] > 0
    if r_sig and n_sig and r_pos and n_pos:
        return "KEEP (significant gain on both)"
    if (r_sig and r_pos) or (n_sig and n_pos):
        return "KEEP (significant on one of recall/ndcg)"
    if (r_sig and not r_pos) or (n_sig and not n_pos):
        return "DROP (significantly worse)"
    return "SIMPLIFY/INCONCLUSIVE (CI includes 0 — no detectable gain)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", type=Path, default=REPO_ROOT / "tests" / "coplay_eval_set.json")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--weighted-x", type=Path, default=REPO_ROOT / "outputs" / "X_game_tag_weighted.npz")
    ap.add_argument("--binary-x", type=Path, default=REPO_ROOT / "serving" / "data" / "X_game_tag_csr.npz")
    ap.add_argument("--ppmi-vecs", type=Path, default=REPO_ROOT / "outputs" / "game_vecs_ppmi.npy")
    ap.add_argument("--ensemble-vecs", type=Path, default=REPO_ROOT / "serving" / "data" / "game_vecs.npy")
    ap.add_argument("--ks", type=int, nargs="+", default=[10, 20, 50])
    ap.add_argument("--top-k", type=int, default=50, help="retrieval depth")
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--run-id", type=str, default=None)
    args = ap.parse_args()

    ks = sorted(args.ks)
    headline_k = ks[-1]
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = REPO_ROOT / "experiments"

    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    if args.limit > 0:
        labels = labels[: args.limit]
    log.info("loaded %d co-play seed labels", len(labels))

    cat = Catalog(args.data_dir)

    # Variant ladder (similar mode). Vd' (W_align) and agentic are Phase 2/3.
    variants = {
        "tagset_jaccard": TagSetRetriever(cat, args.binary_x),
        "Vb_tagcosine": TagCosineRetriever(cat, args.weighted_x),
        "Vc_ppmi_svd": VecSimilarRetriever(cat, args.ppmi_vecs, "Vc_ppmi_svd"),
        "Vd_ensemble": VecSimilarRetriever(cat, args.ensemble_vecs, "Vd_ensemble"),
    }
    # Anchors for the ladder floor (also used by Phase 0)
    ladder_anchors = {
        "V0_random": RandomRetriever(cat, seed=args.seed),
        "V1_popularity": PopularityRetriever(cat),
    }

    # ---- Phase 0: validate metrics on anchors ----
    log.info("Phase 0: validating metrics on anchor systems")
    mv_summary, mv_report = mv.validate(cat, variants, labels, ks, args.top_k, seed=args.seed, B=args.bootstrap)

    # ---- Phase 1: evaluate the full ladder ----
    log.info("Phase 1: evaluating ladder over %d seeds", len(labels))
    all_systems = {**ladder_anchors, **variants}
    res = {name: mv.per_seed_eval(r, labels, ks, args.top_k) for name, r in all_systems.items()}

    # Aggregate with bootstrap CIs
    agg = {}
    for name, r in res.items():
        agg[name] = {}
        for k in ks:
            agg[name][f"recall@{k}"] = bootstrap_ci(r["recall"][k], B=args.bootstrap, seed=args.seed)
            agg[name][f"ndcg@{k}"] = bootstrap_ci(r["ndcg"][k], B=args.bootstrap, seed=args.seed)
        # coverage / gini at k=10 (top-of-list concentration)
        tops10 = [t[:10] for t in r["tops"]]
        counts = {}
        for t in tops10:
            for a in t:
                counts[a] = counts.get(a, 0) + 1
        agg[name]["coverage@10"] = catalog_coverage(tops10, cat.n)
        agg[name]["gini@10"] = gini_coefficient(list(counts.values())) if counts else 0.0

    # Distinctiveness: overlap between adjacent rungs
    def overlap_series(a, b, k):
        return np.array([overlap_at_k(res[a]["tops"][i], res[b]["tops"][i], k)
                         for i in range(len(labels))])
    distinct = {
        "Vc_vs_Vb@10": float(overlap_series("Vc_ppmi_svd", "Vb_tagcosine", 10).mean()),
        "Vd_vs_Vc@10": float(overlap_series("Vd_ensemble", "Vc_ppmi_svd", 10).mean()),
        "Vb_vs_V1@10": float(overlap_series("Vb_tagcosine", "V1_popularity", 10).mean()),
    }

    # Paired comparisons (the decisions)
    def paired(a, b, k):
        rec = paired_bootstrap_diff(res[a]["recall"][k], res[b]["recall"][k], B=args.bootstrap, seed=args.seed)
        ndc = paired_bootstrap_diff(res[a]["ndcg"][k], res[b]["ndcg"][k], B=args.bootstrap, seed=args.seed)
        return {"recall": rec, "ndcg": ndc, "wilcoxon_recall_p": wilcoxon_p(res[a]["recall"][k], res[b]["recall"][k]),
                "decision": decision(rec, ndc)}
    comparisons = {
        f"Vb_tagcosine vs V1_popularity @{headline_k}": paired("V1_popularity", "Vb_tagcosine", headline_k),
        f"Vc_ppmi_svd vs Vb_tagcosine @{headline_k}": paired("Vb_tagcosine", "Vc_ppmi_svd", headline_k),
        f"Vd_ensemble vs Vc_ppmi_svd @{headline_k}": paired("Vc_ppmi_svd", "Vd_ensemble", headline_k),
    }

    # ---- Popularity-debiased sensitivity (Phase 0 flagged USE+DEBIAS) ----
    # Drop globally-popular games (top 5% popularity percentile) from each
    # relevant set so the metric rewards finding NON-obvious co-play neighbors,
    # not just popular ones. The confound inflates the popularity baseline; the
    # Vc-vs-Vb comparison is immune (both content systems, identical labels)
    # but we log this to make the conclusion bulletproof.
    pctile = popularity_percentile(cat.popularity)
    ap_pct = {cat.row2appid[i]: float(pctile[i]) for i in range(cat.n)}
    DEBIAS_THR = 0.95
    deb = {name: [] for name in all_systems}
    for i, lab in enumerate(labels):
        rel = {a for a in lab["relevant_appids"] if ap_pct.get(a, 0.0) < DEBIAS_THR}
        if not rel:
            continue
        for name, r in res.items():
            deb[name].append(recall_at_k(rel, r["tops"][i], headline_k))
    deb = {n: np.array(v) for n, v in deb.items()}
    deb_ci = {n: bootstrap_ci(v, B=args.bootstrap, seed=args.seed) for n, v in deb.items()}
    deb_cmp = {
        "Vc_ppmi_svd vs Vb_tagcosine (debiased)":
            paired_bootstrap_diff(deb["Vb_tagcosine"], deb["Vc_ppmi_svd"], B=args.bootstrap, seed=args.seed),
        "Vb_tagcosine vs V1_popularity (debiased)":
            paired_bootstrap_diff(deb["V1_popularity"], deb["Vb_tagcosine"], B=args.bootstrap, seed=args.seed),
    }

    # ---- Write everything ----
    logger = RunLogger(run_id, out_root)
    logger.write_text("metric_trust_report.md", mv_report)

    # per-query wide CSV
    pq_rows = []
    for i, lab in enumerate(labels):
        row = {"seed_appid": lab["seed_appid"], "seed_title": lab["seed_title"],
               "n_relevant": lab["n_relevant"], "seed_support": lab["seed_support"]}
        for name, r in res.items():
            for k in ks:
                row[f"{name}_recall@{k}"] = r["recall"][k][i]
                row[f"{name}_ndcg@{k}"] = r["ndcg"][k][i]
        pq_rows.append(row)
    logger.write_per_query(pd.DataFrame(pq_rows))

    manifest = {
        "run_id": run_id,
        "phase": "1-similar-coplay",
        "n_labels": len(labels),
        "ks": ks, "top_k": args.top_k, "bootstrap_B": args.bootstrap, "seed": args.seed,
        "artifacts": {
            "labels": fingerprint(args.labels),
            "weighted_x": fingerprint(args.weighted_x),
            "binary_x": fingerprint(args.binary_x),
            "ppmi_vecs": fingerprint(args.ppmi_vecs),
            "ensemble_vecs": fingerprint(args.ensemble_vecs),
            "index_maps": fingerprint(args.data_dir / "index_maps.json"),
            "popularity": fingerprint(args.data_dir / "game_popularity.npy"),
        },
        "variants": list(all_systems.keys()),
    }
    logger.write_aggregate({"aggregate": agg, "distinctiveness": distinct,
                            "comparisons": comparisons, "metric_validation": mv_summary,
                            "debiased": {"recall_ci": deb_ci, "comparisons": deb_cmp,
                                         "threshold_pct": DEBIAS_THR}})
    logger.write_manifest(manifest)

    # ---- report.md ----
    def ci(name, metric, k):
        c = agg[name][f"{metric}@{k}"]
        return f"{c['mean']:.3f} [{c['lo']:.3f},{c['hi']:.3f}]"

    L = [
        f"# Phase 1 — Similar mode: does SVD/structure beat tag-cosine? (run `{run_id}`)",
        "",
        f"Non-circular **co-play** ground truth, **{len(labels)}** seeds (support≥30). "
        f"Evaluating RAW retrieval ranking (no rerank). 95% bootstrap CI (B={args.bootstrap}).",
        "",
        "> Note: avg |relevant| ≈ 25, so recall@10 is capped near 10/25; the cap is identical "
        "across variants so comparisons stay valid. Headline k = "
        f"**{headline_k}** (ceiling reachable).",
        "",
        "## Ladder (recall / ndcg with 95% CI, coverage, gini)",
        "",
        "| variant | " + " | ".join(f"recall@{k}" for k in ks) + f" | ndcg@{headline_k} | coverage@10 | gini@10 |",
        "|---|" + "---|" * (len(ks) + 3),
    ]
    order = ["V0_random", "V1_popularity", "tagset_jaccard", "Vb_tagcosine", "Vc_ppmi_svd", "Vd_ensemble"]
    for name in order:
        row = [name] + [ci(name, "recall", k) for k in ks]
        row += [ci(name, "ndcg", headline_k), f"{agg[name]['coverage@10']:.3f}", f"{agg[name]['gini@10']:.3f}"]
        L.append("| " + " | ".join(row) + " |")

    L += ["", "## Distinctiveness (overlap@10 — do variants even differ?)", ""]
    for k_, v_ in distinct.items():
        L.append(f"- `{k_}` = {v_:.3f}  (1.0 = identical outputs, 0.0 = fully different)")

    L += ["", f"## Paired comparisons @{headline_k} (the decisions)", "",
          "| comparison | Δrecall [CI] | Δndcg [CI] | Wilcoxon p | decision |",
          "|---|---|---|---|---|"]
    for name, c in comparisons.items():
        r, n = c["recall"], c["ndcg"]
        L.append(f"| {name} | {r['mean_diff']:+.3f} [{r['lo']:+.3f},{r['hi']:+.3f}] | "
                 f"{n['mean_diff']:+.3f} [{n['lo']:+.3f},{n['hi']:+.3f}] | "
                 f"{c['wilcoxon_recall_p']:.1e} | **{c['decision']}** |")

    L += ["", f"## Popularity-debiased @{headline_k} (drop relevant in top-5% popularity)", "",
          "Phase 0 flagged the metric as popularity-confounded; this removes the 'easy' popular hits "
          "so the metric rewards finding non-obvious co-play neighbors.", "",
          "| variant | recall@%d (debiased) [CI] |" % headline_k, "|---|---|"]
    for name in order:
        c = deb_ci[name]
        L.append(f"| {name} | {c['mean']:.3f} [{c['lo']:.3f},{c['hi']:.3f}] |")
    L += ["", "| comparison (debiased) | Δrecall [CI] | significant |", "|---|---|---|"]
    for name, c in deb_cmp.items():
        L.append(f"| {name} | {c['mean_diff']:+.3f} [{c['lo']:+.3f},{c['hi']:+.3f}] | {c['significant']} |")

    L += [
        "", "## Honest caveats", "",
        "- Co-play labels are head/mid-skewed (reviews capped ~10/user); seeds restricted to support≥30. "
        "Conclusions apply to the sufficiently-reviewed catalog, not the deep long tail.",
        "- `Vd_ensemble` == `Vc_ppmi_svd` is expected (ensemble_alpha=1.0 ⇒ Item2Vec OFF). Reported to confirm, "
        "not to claim a gain. Evaluating an actual Item2Vec variant on co-play would be CONTAMINATED.",
        "- This measures retrieval relevance only; diversity/novelty rerank is evaluated separately.",
        "- See `metric_trust_report.md` (this run dir) for Phase 0 metric validation.",
    ]
    logger.write_report("\n".join(L))

    # registry line
    logger.append_registry({
        "run_id": run_id, "phase": "1-similar-coplay", "n_labels": len(labels),
        "headline_k": headline_k,
        "recall": {n: agg[n][f"recall@{headline_k}"]["mean"] for n in order},
        "key_decision_Vc_vs_Vb": comparisons[f"Vc_ppmi_svd vs Vb_tagcosine @{headline_k}"]["decision"],
        "artifacts_sha": {k: v.get("sha256") for k, v in manifest["artifacts"].items()},
    })

    log.info("wrote results to %s", logger.dir)
    print("\n".join(L))
    print("\n=== Phase 0 verdicts ===")
    for k_, v_ in mv_summary["verdicts"].items():
        print(f"  {k_}: {v_}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
