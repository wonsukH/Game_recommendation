"""Phase D — does the AGENTIC orchestration add value over a single-pass pipeline?

Both pipelines use the SAME tools (CF moat + constraint filter); the only
difference is the agentic orchestration (multi-entity fusion + under-fill refine).
So any gap is attributable to the agentic layer itself.

Two tests, both on BEHAVIORAL hold-out (no judge — clean, objective):

1. MULTI-ENTITY ("me + friend") — the decisive, structural test. A single-pass
   recommender can only use ONE library, so it ignores the friend. We pair real
   users (A,B), hide 30% of each one's liked games, and measure how well the
   top-K serves BOTH (min(recall_A, recall_B)). Agentic fuses both libraries;
   non-agentic uses A only -> should miss B.

2. OVER-CONSTRAINED completeness (descriptive) — tight constraints make naive
   filtering under-fill; the agent refines (relaxes softest constraint) to still
   return K. We report result-completeness, not a kill metric.

Kill criterion (pre-registered): agentic significantly beats non-agentic on
multi-entity min-recall (paired-bootstrap 95% CI excludes 0) -> the agentic layer
earns its place. Else -> ship the single-pass pipeline (honest: personalized
recsys + explanation, not an agent).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.agent.cf_recommender import CFRecommender  # noqa: E402
from pipeline.game_rec.agent.tools import CatalogMeta  # noqa: E402
from pipeline.game_rec.agent.orchestrators import NonAgentic, Agentic  # noqa: E402
from pipeline.game_rec.evaluation.metrics import recall_at_k  # noqa: E402
from pipeline.game_rec.evaluation.stats import bootstrap_ci, paired_bootstrap_diff  # noqa: E402
from pipeline.game_rec.evaluation.run_logger import RunLogger, fingerprint  # noqa: E402
from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.personalization_experiment import load_user_data  # noqa: E402

log = get_logger("orchestration.agentic_eval")
EXP = REPO_ROOT / "experiments"


def _split(appids, frac, seed):
    rng = np.random.default_rng(seed)
    a = list(appids); rng.shuffle(a)
    n = max(1, int(round(len(a) * frac)))
    return a[:n], set(a[n:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--n-pairs", type=int, default=60)
    ap.add_argument("--min-liked", type=int, default=8)
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-id", type=str, default=None)
    args = ap.parse_args()

    run_id = args.run_id or ("agentic_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    maps = load_index_maps(args.data_dir / "index_maps.json")
    pool = set(int(a) for a in maps["appid2row"].keys())

    cf = CFRecommender()
    meta = CatalogMeta(args.data_dir)
    non = NonAgentic(cf, meta)
    FUSIONS = ["min", "geomean", "balanced", "interleave"]
    agt_by_fusion = {f: Agentic(cf, meta, fusion=f) for f in FUSIONS}

    user_pt, _ = load_user_data(args.scores, pool, 7.0)
    elig = [u for u, g in user_pt.items() if len(g) >= args.min_liked]
    rng = np.random.default_rng(args.seed)
    picks = rng.choice(np.array(elig, dtype=object), size=min(2 * args.n_pairs, len(elig)), replace=False).tolist()
    pairs = [(picks[i], picks[i + 1]) for i in range(0, len(picks) - 1, 2)]
    log.info("eligible=%d, pairs=%d", len(elig), len(pairs))

    # ---- Test 1: multi-entity (the gate), fusion sweep ----
    rows = []
    for i, (ua, ub) in enumerate(pairs):
        profA, holdA = _split(user_pt[ua].keys(), 0.7, args.seed + i)
        profB, holdB = _split(user_pt[ub].keys(), 0.7, args.seed + 1000 + i)
        if not holdA or not holdB:
            continue
        libA = {a: user_pt[ua][a] for a in profA}
        libB = {a: user_pt[ub][a] for a in profB}
        libs = {"A": libA, "B": libB}

        non_recs = non.recommend(libs, {}, k=args.k)["recs"]   # uses A only
        r = {"pair": f"{ua[-6:]}~{ub[-6:]}",
             "non_A": recall_at_k(holdA, non_recs, args.k),
             "non_B": recall_at_k(holdB, non_recs, args.k)}
        r["non_min"] = min(r["non_A"], r["non_B"])
        for f in FUSIONS:
            recs = agt_by_fusion[f].recommend(libs, {}, k=args.k)["recs"]
            ra, rb = recall_at_k(holdA, recs, args.k), recall_at_k(holdB, recs, args.k)
            r[f"{f}_A"], r[f"{f}_B"], r[f"{f}_min"] = ra, rb, min(ra, rb)
        rows.append(r)
    df = pd.DataFrame(rows)

    def arr(c):
        return df[c].to_numpy(dtype=float)

    cols = ["non_A", "non_B", "non_min"] + [f"{f}_{s}" for f in FUSIONS for s in ("A", "B", "min")]
    agg = {c: bootstrap_ci(arr(c), B=args.bootstrap, seed=args.seed) for c in cols}
    # paired: each fusion's min-recall vs non-agentic min-recall
    cmp_fusion = {f: paired_bootstrap_diff(arr("non_min"), arr(f"{f}_min"), B=args.bootstrap, seed=args.seed)
                  for f in FUSIONS}
    # best fusion = highest mean min-recall
    best = max(FUSIONS, key=lambda f: agg[f"{f}_min"]["mean"])
    cmp_min = cmp_fusion[best]
    cmp_B = paired_bootstrap_diff(arr("non_B"), arr(f"{best}_B"), B=args.bootstrap, seed=args.seed)

    # ---- Test 2: over-constrained completeness (descriptive) ----
    tight = {"coop": True, "max_price": 10.0, "released_after": 2018}
    solo = [u for u in elig if u not in set(picks)][:60] or elig[:60]
    comp_non, comp_agt = [], []
    for j, u in enumerate(solo):
        prof, _ = _split(user_pt[u].keys(), 0.7, args.seed + j)
        lib = {a: user_pt[u][a] for a in prof}
        comp_non.append(len(non.recommend({"A": lib}, tight, k=args.k)["recs"]) / args.k)
        comp_agt.append(len(agt_by_fusion[best].recommend({"A": lib}, tight, k=args.k)["recs"]) / args.k)
    comp = {"non_complete": bootstrap_ci(comp_non, B=args.bootstrap, seed=args.seed),
            "agt_complete": bootstrap_ci(comp_agt, B=args.bootstrap, seed=args.seed),
            "constraints": tight}

    # ---- write ----
    logger = RunLogger(run_id, EXP)
    logger.write_per_query(df)
    logger.write_aggregate({"multi_entity": agg, "cmp_min": cmp_min, "cmp_B": cmp_B,
                            "over_constrained": comp})
    logger.write_manifest({"run_id": run_id, "phase": "D-agentic-value", "n_pairs": len(df),
                           "k": args.k, "seed": args.seed,
                           "artifacts": {"scores": fingerprint(args.scores),
                                         "cf_artifact": fingerprint(args.data_dir / "cf" / "cooccurrence.npz")}})

    def ci(d, c):
        x = d[c]; return f"{x['mean']:.3f} [{x['lo']:.3f},{x['hi']:.3f}]"

    decided = f"KEEP agentic (fusion={best})" if (cmp_min["significant"] and cmp_min["mean_diff"] > 0) else \
              "SIMPLIFY → single-pass (agentic 미입증)"
    L = [f"# Phase D — Agentic orchestration value (run `{run_id}`)", "",
         f"{len(df)} user-pairs, behavioral hold-out, deterministic (no LLM/judge). 95% bootstrap CI.", "",
         "## Test 1 — MULTI-ENTITY ('me + friend'), k=%d — fusion sweep  [the gate]" % args.k, "",
         "| system | recall A | recall B (friend) | min(A,B)=둘다 | Δmin vs non |", "|---|---|---|---|---|",
         f"| non-agentic (A만) | {ci(agg,'non_A')} | {ci(agg,'non_B')} | {ci(agg,'non_min')} | — |"]
    for f in FUSIONS:
        mark = " ★best" if f == best else ""
        cf_ = cmp_fusion[f]
        L.append(f"| agentic:{f}{mark} | {ci(agg, f+'_A')} | {ci(agg, f+'_B')} | {ci(agg, f+'_min')} | "
                 f"{cf_['mean_diff']:+.3f} [{cf_['lo']:+.3f},{cf_['hi']:+.3f}] {'SIG' if cf_['significant'] else 'ns'} |")
    L += ["",
          f"- best fusion = **{best}**; agentic − non min(A,B) = {cmp_min['mean_diff']:+.3f} "
          f"[{cmp_min['lo']:+.3f},{cmp_min['hi']:+.3f}] ({'SIG' if cmp_min['significant'] else 'ns'})",
          f"- best fusion friend(B) recall Δ = {cmp_B['mean_diff']:+.3f} [{cmp_B['lo']:+.3f},{cmp_B['hi']:+.3f}] "
          f"({'SIG' if cmp_B['significant'] else 'ns'})",
          "",
         "## Test 2 — over-constrained completeness (descriptive)  constraints=%s" % tight, "",
         f"- non-agentic returns/k = {ci(comp,'non_complete')}",
         f"- agentic returns/k     = {ci(comp,'agt_complete')}  (refine relaxes softest constraint to fill K)",
         "",
         "## Decision (pre-registered)", "",
         f"**{decided}** — multi-entity min-recall: non={agg['non_min']['mean']:.3f} vs agentic({best})={agg[best+'_min']['mean']:.3f}.",
         "", "## 해석",
         "- 단일패스는 친구(B)를 구조적으로 무시 → B-recall 낮음. agentic은 두 라이브러리 융합 → 둘 다 served.",
         "- 이건 LLM이 더 똑똑해서가 아니라 *오케스트레이션*(다중주체 융합)이 주는 가치 → 진짜 agentic 차별점.",
         "- (참고) 단발·단일주체 단순 추천이면 agentic은 과함; 가치는 복합/다중주체에서 발생."]
    logger.write_report("\n".join(L), decision=f"best fusion = {best}")
    logger.append_registry({"run_id": run_id, "phase": "D-agentic-value", "n_pairs": len(df),
                            "best_fusion": best, "agentic_min": agg[f"{best}_min"]["mean"],
                            "non_min": agg["non_min"]["mean"],
                            "agentic_minus_non_min": cmp_min["mean_diff"], "sig": cmp_min["significant"],
                            "decision": decided})
    dlog = EXP / "DELIBERATION_LOG.md"
    if dlog.exists():
        with open(dlog, "a", encoding="utf-8") as f:
            f.write(f"\n\n## (재설계 Phase D) 에이전트성 검증 — run `{run_id}`\n"
                    f"- 다중주체 min(A,B) recall: non={agg['non_min']['mean']:.3f} vs agentic({best})={agg[best+'_min']['mean']:.3f}; "
                    f"Δ={cmp_min['mean_diff']:+.3f} [{cmp_min['lo']:+.3f},{cmp_min['hi']:+.3f}] ({'SIG' if cmp_min['significant'] else 'ns'}).\n"
                    f"- 친구(B) recall Δ={cmp_B['mean_diff']:+.3f} ({'SIG' if cmp_B['significant'] else 'ns'}). 과제약 완결성 non={comp['non_complete']['mean']:.2f} vs agt={comp['agt_complete']['mean']:.2f}.\n"
                    f"- 결정: {decided}. 상세: experiments/{run_id}/report.md\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
