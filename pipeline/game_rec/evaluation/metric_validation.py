"""Phase 0 — validate the metrics BEFORE trusting them to judge the system.

We do not just apply all metrics. Each is first run on control/anchor systems
whose quality is known a priori, so we can tell whether the metric actually
measures quality:

- random        : should score at the FLOOR.
- oracle        : returns the true relevant set -> should score at the CEILING.
- oracle_dropN  : oracle with N relevants replaced by random irrelevants ->
                  score should drop monotonically (perturbation sensitivity).
- popularity    : tests popularity confounding (does a query-blind popular
                  list score high on a "relevance" metric?).
- real variants : tag-cosine / SVD -> tests discriminative power (spread).

Verdicts written to metric_trust_report.md:
  USE        — passes floor/ceiling + sensitive + has discriminative spread
  DEBIAS     — works but popularity-confounded; report with novelty calibration
  DEMOTE     — circular/gameable or no discriminative power (guardrail only)

Convergent validity & reliability (vs LLM judge) are Phase 2 and noted as
DEFERRED here.
"""

from __future__ import annotations

import numpy as np

from pipeline.game_rec.evaluation.metrics import recall_at_k, ndcg_at_k
from pipeline.game_rec.evaluation.stats import bootstrap_ci


class OracleRetriever:
    """Ceiling anchor: returns the seed's true relevant set (optionally noised)."""

    def __init__(self, catalog, labels_by_seed, drop: int = 0, seed: int = 42):
        self.cat = catalog
        self.labels = labels_by_seed
        self.drop = drop
        self.rng = np.random.default_rng(seed)
        self.name = f"oracle_drop{drop}" if drop else "oracle"
        self._all = np.array(list(catalog.appid2row.keys()))

    def similar(self, seed_appid: int, top_k: int = 50) -> list[int]:
        rel = list(self.labels.get(seed_appid, []))
        if self.drop > 0 and rel:
            keep = rel[: max(0, len(rel) - self.drop)]
            relset = set(rel) | {seed_appid}
            noise = [int(a) for a in self.rng.choice(self._all, size=self.drop * 3, replace=False)
                     if int(a) not in relset][: self.drop]
            out = keep + noise
        else:
            out = rel
        return out[:top_k]


def per_seed_eval(retriever, labels: list[dict], ks: list[int], top_k: int) -> dict:
    """Run a retriever over all seed labels.

    Returns {"recall": {k: np.array}, "ndcg": {k: np.array}, "tops": [list...]}
    with one entry per label (aligned order), so paired stats work downstream.
    """
    recall = {k: [] for k in ks}
    ndcg = {k: [] for k in ks}
    tops = []
    for lab in labels:
        seed = lab["seed_appid"]
        rel = set(lab["relevant_appids"])
        top = retriever.similar(seed, top_k)
        tops.append(top)
        for k in ks:
            recall[k].append(recall_at_k(rel, top, k))
            ndcg[k].append(ndcg_at_k(rel, top, k))
    return {
        "recall": {k: np.array(v) for k, v in recall.items()},
        "ndcg": {k: np.array(v) for k, v in ndcg.items()},
        "tops": tops,
    }


def validate(catalog, real_variants: dict, labels: list[dict], ks, top_k, seed=42, B=1000):
    """Run the validation battery. Returns (verdicts: dict, report_md: str)."""
    labels_by_seed = {l["seed_appid"]: l["relevant_appids"] for l in labels}
    headline_k = max(ks)  # at this k oracle should reach ~1.0 (k >= avg |rel|)

    # Anchors
    from pipeline.game_rec.agent.baselines import RandomRetriever, PopularityRetriever
    anchors = {
        "random": RandomRetriever(catalog, seed=seed),
        "popularity": PopularityRetriever(catalog),
        "oracle": OracleRetriever(catalog, labels_by_seed, drop=0, seed=seed),
        "oracle_drop5": OracleRetriever(catalog, labels_by_seed, drop=5, seed=seed),
        "oracle_drop10": OracleRetriever(catalog, labels_by_seed, drop=10, seed=seed),
    }

    systems = {**anchors, **real_variants}
    res = {name: per_seed_eval(r, labels, ks, top_k) for name, r in systems.items()}

    def m(name, metric, k):
        return float(res[name][metric][k].mean())

    # ---- Battery on recall@headline_k (where the ceiling is reachable) ----
    rnd = m("random", "recall", headline_k)
    orc = m("oracle", "recall", headline_k)
    pop = m("popularity", "recall", headline_k)
    d0, d5, d10 = (m("oracle", "recall", headline_k),
                   m("oracle_drop5", "recall", headline_k),
                   m("oracle_drop10", "recall", headline_k))
    real_recalls = [m(n, "recall", headline_k) for n in real_variants]
    spread = (max(real_recalls) - min(real_recalls)) if real_recalls else 0.0

    checks = {
        "floor_ceiling": {
            "random": rnd, "oracle": orc,
            "pass": bool(orc >= 0.9 and rnd <= 0.05),
        },
        "perturbation_monotonic": {
            "oracle": d0, "drop5": d5, "drop10": d10,
            "pass": bool(d0 > d5 > d10),
        },
        "discriminative_power": {
            "real_recall_spread": spread,
            "pass": bool(spread >= 0.02),
        },
        "popularity_confound": {
            "popularity_recall": pop, "random_recall": rnd,
            "ratio_vs_random": (pop / rnd) if rnd > 0 else float("inf"),
            # popularity beating random a lot => co-play recall partly rewards popularity
            "confounded": bool(pop > 0.15 and pop > 3 * max(rnd, 1e-9)),
        },
    }

    # ---- Per-metric verdicts ----
    verdicts = {}
    base_ok = checks["floor_ceiling"]["pass"] and checks["perturbation_monotonic"]["pass"]
    for metric in ("recall", "ndcg"):
        if base_ok and checks["discriminative_power"]["pass"]:
            v = "USE"
            if checks["popularity_confound"]["confounded"]:
                v = "USE+DEBIAS (report novelty-calibration alongside)"
        elif base_ok:
            v = "WEAK (passes floor/ceiling but low discriminative spread)"
        else:
            v = "DEMOTE (failed floor/ceiling or perturbation)"
        verdicts[f"{metric}@{headline_k}"] = v
    verdicts["overlap@k"] = "SCREENING ONLY (distinctiveness, not quality)"
    verdicts["genre_precision"] = "DEMOTE→guardrail (circular for tag systems; tag-cosine inflates it by construction)"
    verdicts["coplay_recall_for_item2vec"] = "INVALID (contaminated — Item2Vec trains on same reviews)"
    verdicts["convergent_validity_vs_judge"] = "DEFERRED to Phase 2"
    verdicts["reliability_judge_repeat"] = "DEFERRED to Phase 2"

    # ---- Report ----
    L = [
        "# Phase 0 — Metric Trust Report",
        "",
        f"Anchors + {len(real_variants)} real variants over **{len(labels)} co-play seeds**. "
        f"Headline k = **{headline_k}** (recall ceiling reachable since k ≥ avg |relevant|).",
        "",
        "## Anchor recall (validation)",
        "",
        "| system | " + " | ".join(f"recall@{k}" for k in ks) + " | " + " | ".join(f"ndcg@{k}" for k in ks) + " |",
        "|---|" + "---|" * (2 * len(ks)),
    ]
    for name in systems:
        row = [name]
        row += [f"{m(name,'recall',k):.3f}" for k in ks]
        row += [f"{m(name,'ndcg',k):.3f}" for k in ks]
        L.append("| " + " | ".join(row) + " |")

    L += [
        "",
        "## Validation checks",
        "",
        f"- **Floor/Ceiling**: random={rnd:.3f}, oracle={orc:.3f} → "
        f"{'PASS' if checks['floor_ceiling']['pass'] else 'FAIL'} "
        f"(oracle must be ≥0.90 and random ≤0.05)",
        f"- **Perturbation monotonic**: oracle={d0:.3f} > drop5={d5:.3f} > drop10={d10:.3f} → "
        f"{'PASS' if checks['perturbation_monotonic']['pass'] else 'FAIL'}",
        f"- **Discriminative power**: real-variant recall spread={spread:.3f} → "
        f"{'PASS' if checks['discriminative_power']['pass'] else 'FAIL'} (need ≥0.02 to separate systems)",
        f"- **Popularity confound**: popularity={pop:.3f} vs random={rnd:.3f} "
        f"(×{checks['popularity_confound']['ratio_vs_random']:.1f}) → "
        f"{'CONFOUNDED' if checks['popularity_confound']['confounded'] else 'OK'}",
        "",
        "## Verdicts (which metric may drive which decision)",
        "",
        "| metric | verdict |",
        "|---|---|",
    ]
    for k_, v_ in verdicts.items():
        L.append(f"| `{k_}` | {v_} |")
    L += [
        "",
        "**Gate:** only metrics marked USE / USE+DEBIAS drive keep/drop decisions in Phase 1. "
        "Non-circular co-play recall/ndcg are the primary; overlap is screening; Genre Precision is a guardrail only.",
    ]
    report = "\n".join(L)
    summary = {"checks": checks, "verdicts": verdicts,
               "anchor_recall": {n: {f"recall@{k}": m(n, "recall", k) for k in ks} for n in systems}}
    return summary, report
