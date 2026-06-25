"""F validation (behavioral) — does NOVELTY steering recover the user's own
branch-out behavior better than plain CF?

Non-circular test: define a held-out game as NEW-GENRE for a user if most of its
tags are ones the user's PROFILE games don't carry (genre the user hasn't
concentrated in). This is defined purely from the user's own data, independent of
any recommender. Then measure, on the SAME hold-out:
  - new-genre recall@k: of the user's new-genre held-out games, how many in top-k.
  - overall recall@k: the quality/tradeoff guard (steering must not tank it).

Compare plain CF (β=0) vs adjacent-novelty steering (content-novelty, several β).
Leave-user-out CF, paired bootstrap. PRE-REGISTERED: adopt a β if it raises
new-genre recall with a 95% CI excluding 0; report the overall-recall tradeoff
honestly (do not hide a quality loss).

Aspect steering is validated separately (mechanical aspect-match lift + blinded
judge) since there's no per-user aspect ground truth.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.evaluation.coplay_labels import build_cooccurrence  # noqa: E402
from pipeline.game_rec.evaluation.metrics import recall_at_k  # noqa: E402
from pipeline.game_rec.evaluation.stats import bootstrap_ci, paired_bootstrap_diff  # noqa: E402
from pipeline.game_rec.evaluation.run_logger import RunLogger  # noqa: E402
from pipeline.game_rec.agent.cf_recommender import pt_weight  # noqa: E402
from pipeline.game_rec.agent.content import ContentLayer  # noqa: E402
from pipeline.game_rec.agent.tools import CatalogMeta  # noqa: E402
from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402
from pipeline.orchestration.personalization_experiment import load_user_data, cf_scores  # noqa: E402

log = get_logger("orchestration.steering_eval")
EXP = REPO_ROOT / "experiments"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--n-users", type=int, default=400)
    ap.add_argument("--min-games", type=int, default=6)
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--min-cooc", type=int, default=3)
    ap.add_argument("--newgenre-tau", type=float, default=0.34,
                    help="held-out game is new-genre if <tau of its tags are in profile tags")
    ap.add_argument("--betas", type=float, nargs="+", default=[1.0, 2.0, 3.0])
    ap.add_argument("--min-quality-pct", type=float, default=0.30)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-id", type=str, default=None)
    args = ap.parse_args()

    run_id = args.run_id or ("steering_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    maps = load_index_maps(args.data_dir / "index_maps.json")
    pool = set(int(a) for a in maps["appid2row"].keys())
    user_pt, game_avg = load_user_data(args.scores, pool, 7.0)
    content = ContentLayer(args.data_dir)
    meta = CatalogMeta(args.data_dir)

    elig = [u for u, g in user_pt.items() if len(g) >= args.min_games]
    rng = np.random.default_rng(args.seed)
    test = rng.choice(np.array(elig, dtype=object), size=min(args.n_users, len(elig)), replace=False).tolist()
    train = {u: set(user_pt[u].keys()) for u in user_pt if u not in set(test)}
    C, deg, col = build_cooccurrence(train)
    inv = {j: a for a, j in col.items()}

    def cf_warm(prof_pt):
        acc = cf_scores([(a, pt_weight(prof_pt[a], game_avg.get(a, 0.0))) for a in prof_pt],
                        C, deg, col, args.min_cooc)
        order = np.argsort(-acc)
        out, excl = [], set(prof_pt)
        for j in order:
            if acc[j] <= 0:
                break
            a = inv.get(int(j))
            if a is not None and a not in excl:
                out.append((a, float(acc[j])))
            if len(out) >= 600:
                break
        return out

    def steer(warm, prof_pt, beta):
        if beta <= 0 or not warm:
            return [a for a, _ in warm][:args.k]
        appids = [a for a, _ in warm]
        rows = np.array([content.appid2row[a] for a in appids])
        cf_s = np.array([s for _, s in warm]); cf_s = cf_s / (cf_s.max() + 1e-12)
        sim = content.content_scores(prof_pt, game_avg)[rows]
        fam = (sim - sim.min()) / (sim.max() - sim.min() + 1e-12)
        nv = np.clip(1.0 - fam, 1e-6, 1.0)
        score = cf_s * np.power(nv, beta)
        keep = set(meta.quality_gate(appids, min_metacritic=None, min_quality_pct=args.min_quality_pct))
        score = np.array([score[i] if appids[i] in keep else -np.inf for i in range(len(appids))])
        order = np.argsort(-score)
        return [appids[i] for i in order if np.isfinite(score[i])][:args.k]

    configs = ["cf"] + [f"nov_b{b:g}" for b in args.betas]
    newgenre = {c: [] for c in configs}
    overall = {c: [] for c in configs}
    n_newgenre_users = 0
    for i, u in enumerate(sorted(test)):
        ap_ = list(user_pt[u].keys())
        r = np.random.default_rng(args.seed + i); r.shuffle(ap_)
        nprof = max(1, int(round(len(ap_) * 0.7)))
        if len(ap_) - nprof < 1:
            continue
        prof_ids = ap_[:nprof]; hold = set(ap_[nprof:])
        prof_pt = {a: user_pt[u][a] for a in prof_ids}
        # profile tags & new-genre holdout subset
        prof_rows = [content.appid2row[a] for a in prof_ids if a in content.appid2row]
        prof_tags = set(np.asarray(content.B[prof_rows].sum(axis=0)).ravel().nonzero()[0].tolist())
        ng = set()
        for h in hold:
            rh = content.appid2row.get(h)
            if rh is None:
                continue
            htags = set(content.B.getrow(rh).indices.tolist())
            if htags and len(htags & prof_tags) / len(htags) < args.newgenre_tau:
                ng.add(h)
        warm = cf_warm(prof_pt)
        for c, beta in zip(configs, [0.0] + list(args.betas)):
            recs = steer(warm, prof_pt, beta)
            overall[c].append(recall_at_k(hold, recs, args.k))
            if ng:
                newgenre[c].append(recall_at_k(ng, recs, args.k))
        if ng:
            n_newgenre_users += 1

    res = {"n_test": len(overall["cf"]), "n_newgenre_users": n_newgenre_users,
           "overall": {}, "newgenre": {}, "diff_vs_cf": {}}
    base_ng = np.array(newgenre["cf"]); base_ov = np.array(overall["cf"])
    for c in configs:
        ov = np.array(overall[c]); ng = np.array(newgenre[c])
        res["overall"][c] = bootstrap_ci(ov, B=args.bootstrap, seed=args.seed)
        res["newgenre"][c] = bootstrap_ci(ng, B=args.bootstrap, seed=args.seed) if len(ng) else None
        if c != "cf":
            res["diff_vs_cf"][c] = {
                "newgenre": paired_bootstrap_diff(base_ng, ng, B=args.bootstrap, seed=args.seed) if len(ng) else None,
                "overall": paired_bootstrap_diff(base_ov, ov, B=args.bootstrap, seed=args.seed)}
    # pick best beta on new-genre recall with CI>0; honest tradeoff note
    best = None
    for c in configs:
        if c == "cf":
            continue
        d = res["diff_vs_cf"][c]["newgenre"]
        if d and d["significant"] and d["mean_diff"] > 0:
            if best is None or d["mean_diff"] > res["diff_vs_cf"][best]["newgenre"]["mean_diff"]:
                best = c
    res["best_config"] = best

    logger = RunLogger(run_id, EXP)
    logger.write_aggregate(res)
    L = [f"# F novelty-steering validation — run `{run_id}`", "",
         f"{res['n_test']} users; {n_newgenre_users} have >=1 NEW-genre held-out game "
         f"(<{args.newgenre_tau} of its tags in profile). recall@{args.k}, leave-user-out.", "",
         "| config | new-genre recall [CI] | overall recall [CI] |", "|---|---|---|"]
    for c in configs:
        ng = res["newgenre"][c]; ov = res["overall"][c]
        ngs = f"{ng['mean']:.4f} [{ng['lo']:.4f},{ng['hi']:.4f}]" if ng else "-"
        L.append(f"| {c} | {ngs} | {ov['mean']:.4f} [{ov['lo']:.4f},{ov['hi']:.4f}] |")
    L += ["", "Δ vs plain CF (paired):", ""]
    for c in configs:
        if c == "cf":
            continue
        dn = res["diff_vs_cf"][c]["newgenre"]; do = res["diff_vs_cf"][c]["overall"]
        dns = (f"new-genre {dn['mean_diff']:+.4f} [{dn['lo']:+.4f},{dn['hi']:+.4f}] {'SIG' if dn['significant'] else 'ns'}"
               if dn else "new-genre n/a")
        L.append(f"- {c}: {dns}; overall {do['mean_diff']:+.4f} [{do['lo']:+.4f},{do['hi']:+.4f}] "
                 f"{'SIG' if do['significant'] else 'ns'}")
    L += ["", f"- **best config (new-genre recall, CI>0): {best}**",
          "", "## 해석",
          "- best가 있으면: 인접노벨티 스티어링이 유저 본인의 *신장르 분기 행동*을 plain-CF보다 잘 회복(비순환 입증).",
          "- overall recall 트레이드오프 정직 보고: 신장르↑가 전체↓를 동반하면 그 폭을 명시(스티어링은 의도적 탐색 모드).",
          "- 측면 스티어링은 별도(기계적 aspect-match + blinded judge)."]
    logger.write_report("\n".join(L))
    logger.append_registry({"run_id": run_id, "phase": "F-steering-newgenre",
                            "best_config": best, "n_newgenre_users": n_newgenre_users,
                            "newgenre_recall": {c: (res["newgenre"][c]["mean"] if res["newgenre"][c] else None) for c in configs},
                            "overall_recall": {c: res["overall"][c]["mean"] for c in configs}})
    dlog = EXP / "DELIBERATION_LOG.md"
    if dlog.exists():
        with open(dlog, "a", encoding="utf-8") as f:
            f.write(f"\n\n## (신기능 F검증) 노벨티 스티어링 신장르-recall — run `{run_id}`\n"
                    f"- {n_newgenre_users}명 신장르 holdout 보유. new-genre recall: "
                    + ", ".join(f"{c}={res['newgenre'][c]['mean']:.4f}" for c in configs if res['newgenre'][c]) + "\n"
                    f"- **best={best}** (신장르 recall CI>0). overall 트레이드오프: "
                    + ", ".join(f"{c}={res['overall'][c]['mean']:.3f}" for c in configs) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
