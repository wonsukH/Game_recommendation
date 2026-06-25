"""Small empirical test — does personalized CF beat "LLM + my library"?

The whole investigation converged on: a frontier LLM beats this system ~96% on
recommendation quality, and the only genuine moat candidate is PERSONALIZATION
from the user's full library (not anonymous/seed). But even that has a strong
baseline: give the LLM your library and ask. Before any big redesign, test which
wins — on BEHAVIORAL ground truth (real users' held-out liked games), so there
is no judge familiarity bias.

Design (leave-user-out hold-out):
- Sample test users with >= MIN_LIKED in-pool liked games (s_round10_rec>=7).
- Split each user's liked into profile (70%, their "library") + hold-out (30%, hidden truth).
- Playtime weighting: each profile game weighted w_p = log(1 + playtime / game_avg_playtime)
  ("played longer than average for that game => stronger taste signal").
- Recommenders (candidates = in-pool minus profile):
    CF   : item-item co-occurrence built from all users EXCEPT the test users
           (leave-user-out, no leakage); score(g)=sum_p w_p*condcos(g,p).
    LLM  : Gemini given the profile titles (+playtime hours) -> recommend K -> map to pool.
    POP  : top-K by popularity (popularity-confound control).
    ORACLE: the hold-out set itself (ceiling sanity check for the metric).
- Metric: recall@K / ndcg@K vs the hold-out liked set. Also popularity-debiased
  (drop hold-out games in top-5% popularity) and a long-tail slice (hold-out games
  below median popularity — where CF is expected to help most).
- Bootstrap 95% CI over users; paired-bootstrap CF-LLM / CF-POP / LLM-POP.

Decision rule (pre-registered): CF > LLM (paired CI excludes 0) on recall/ndcg ->
personalization is a genuine moat -> proceed to redesign. CI includes 0 -> "just
give the LLM your library"; no custom CF needed.
"""

from __future__ import annotations

import argparse
import collections
import csv
import difflib
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.evaluation.coplay_labels import build_cooccurrence  # noqa: E402
from pipeline.game_rec.evaluation.metrics import recall_at_k, ndcg_at_k, popularity_percentile  # noqa: E402
from pipeline.game_rec.evaluation.stats import bootstrap_ci, paired_bootstrap_diff  # noqa: E402
from pipeline.game_rec.evaluation.run_logger import RunLogger, fingerprint  # noqa: E402
from pipeline.game_rec.io import load_index_maps  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.personalization")
EXP = REPO_ROOT / "experiments"


def load_user_data(scores_path: Path, pool: set, like_threshold: float):
    """Return (user_liked_pt: {steamid:{appid:playtime}}, game_avg_pt: {appid:mean})."""
    log.info("reading %s", scores_path)
    user_liked_pt: dict[str, dict[int, float]] = collections.defaultdict(dict)
    pt_sum = collections.defaultdict(float)
    pt_cnt = collections.defaultdict(int)
    with open(scores_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                a = int(row["appid"])
            except (TypeError, ValueError):
                continue
            if a not in pool:
                continue
            try:
                pt = float(row["playtime_forever"])
            except (TypeError, ValueError):
                pt = 0.0
            pt_sum[a] += pt
            pt_cnt[a] += 1
            try:
                s = float(row["s_round10_rec"])
            except (TypeError, ValueError):
                continue
            if s >= like_threshold:
                user_liked_pt[row["steamid"]][a] = pt
    game_avg_pt = {a: (pt_sum[a] / pt_cnt[a]) for a in pt_sum if pt_cnt[a] > 0}
    log.info("users with >=1 liked: %d ; games with playtime: %d", len(user_liked_pt), len(game_avg_pt))
    return user_liked_pt, game_avg_pt


def pt_weight(playtime: float, avg: float) -> float:
    if avg and avg > 0:
        return math.log1p(playtime / avg)
    return 1.0


def cf_scores(profile_weighted, C, deg, col, min_cooc: int):
    """score(g) = sum_p w_p * C[g,p]/sqrt(deg[g]*deg[p]) over profile games p in the matrix."""
    n = C.shape[0]
    acc = np.zeros(n, dtype=np.float64)
    for appid, w in profile_weighted:
        j = col.get(appid)
        if j is None:
            continue
        row = C.getrow(j).tocoo()
        dj = deg[j]
        for g, c in zip(row.col, row.data):
            if c < min_cooc or g == j:
                continue
            denom = math.sqrt(dj * deg[g])
            if denom > 0:
                acc[g] += w * (c / denom)
    return acc


def llm_recommend(llm, HumanMessage, profile_titles_pt, k, pool_lower):
    lines = "\n".join(f"- {t} ({int(h)}h)" for t, h in profile_titles_pt)
    prompt = (
        "A user's Steam library (game + hours played) is below. Recommend exactly "
        f"{k} OTHER real Steam games they would most likely enjoy, based on their taste. "
        "Output ONLY official English Steam titles, one per line, no numbering.\n\n"
        f"Library:\n{lines}\n\n{k} recommendations:"
    )
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        log.warning("llm fail: %s", e)
        return [], 0
    titles = []
    for raw in text.split("\n"):
        c = raw.strip()
        for p in ("- ", "* ", "• "):
            if c.startswith(p):
                c = c[len(p):]
        if len(c) > 2 and c[0].isdigit() and c[1] in ".)":
            c = c[2:].strip()
        if c:
            titles.append(c)
    titles = titles[:k]
    miss = 0
    matched = []
    for t in titles:
        tl = t.lower().strip()
        if tl in pool_lower:
            matched.append(pool_lower[tl])
        else:
            m = difflib.get_close_matches(tl, pool_lower.keys(), n=1, cutoff=0.85)
            if m:
                matched.append(pool_lower[m[0]])
            else:
                miss += 1
    return matched, miss


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "outputs" / "user_game_scores.csv")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--n-users", type=int, default=80)
    ap.add_argument("--min-liked", type=int, default=15)
    ap.add_argument("--profile-frac", type=float, default=0.7)
    ap.add_argument("--llm-cap", type=int, default=40)
    ap.add_argument("--min-cooc", type=int, default=3)
    ap.add_argument("--like-threshold", type=float, default=7.0)
    ap.add_argument("--topk", type=int, nargs="+", default=[10, 20])
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-llm", action="store_true", help="skip the Gemini arm (fast CF/pop smoke)")
    ap.add_argument("--run-id", type=str, default=None)
    args = ap.parse_args()

    ks = sorted(args.topk)
    run_id = args.run_id or ("personalization_" + datetime.now().strftime("%Y%m%d_%H%M%S"))

    maps = load_index_maps(args.data_dir / "index_maps.json")
    pool = set(int(a) for a in maps["appid2row"].keys())
    appid2row = {int(a): int(r) for a, r in maps["appid2row"].items()}
    df_titles = pd.read_csv(args.data_dir / "steam_games_tags.csv")
    appid2title = dict(zip(df_titles["appid"].astype(int), df_titles["game_title"].astype(str)))
    pool_lower = {str(v).lower(): int(k) for k, v in appid2title.items()}
    popularity = np.load(args.data_dir / "game_popularity.npy").astype(np.float64)
    pop_pct_byrow = popularity_percentile(popularity)
    ap_pct = {a: float(pop_pct_byrow[appid2row[a]]) for a in appid2row}

    user_liked_pt, game_avg_pt = load_user_data(args.scores, pool, args.like_threshold)

    # eligible test users: >= min_liked liked games
    eligible = [u for u, g in user_liked_pt.items() if len(g) >= args.min_liked]
    log.info("eligible test users (>=%d liked): %d", args.min_liked, len(eligible))
    rng = np.random.default_rng(args.seed)
    # stratify by liked-count terciles
    eligible.sort(key=lambda u: len(user_liked_pt[u]))
    strata = np.array_split(np.array(eligible, dtype=object), 3)
    per = max(1, args.n_users // 3)
    test_users = []
    for st in strata:
        if len(st) == 0:
            continue
        take = min(per, len(st))
        test_users.extend(rng.choice(st, size=take, replace=False).tolist())
    test_users = list(dict.fromkeys(test_users))[: args.n_users]
    test_set = set(test_users)
    log.info("sampled %d test users", len(test_users))

    # leave-user-out CF: co-occurrence from all NON-test users
    train_liked = {u: set(g.keys()) for u, g in user_liked_pt.items() if u not in test_set}
    C, deg, col = build_cooccurrence(train_liked)

    llm = HumanMessage = None
    if not args.no_llm:
        from dotenv import load_dotenv
        from langchain_core.messages import HumanMessage as HM
        from langchain_google_genai import ChatGoogleGenerativeAI
        import os
        load_dotenv(REPO_ROOT / ".env")
        llm = ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"),
                                     google_api_key=os.environ["GEMINI_API_KEY"], temperature=0.3)
        HumanMessage = HM

    # per-user eval
    recs_systems = ["CF", "LLM", "POP", "ORACLE"]
    metrics = {s: {f"recall@{k}": [] for k in ks} for s in recs_systems}
    for s in recs_systems:
        metrics[s].update({f"ndcg@{k}": [] for k in ks})
    deb_recall = {s: [] for s in recs_systems}      # popularity-debiased recall@maxk
    lt_recall = {s: [] for s in recs_systems}       # long-tail recall@maxk
    llm_miss_total = llm_n = 0
    per_user_rows = []
    maxk = ks[-1]
    DEBIAS_THR = 0.95

    for ui, u in enumerate(test_users):
        liked = user_liked_pt[u]
        appids = list(liked.keys())
        urng = np.random.default_rng(args.seed + ui)
        urng.shuffle(appids)
        n_prof = max(1, int(round(len(appids) * args.profile_frac)))
        profile = appids[:n_prof]
        holdout = set(appids[n_prof:])
        if not holdout:
            continue
        # playtime-weighted profile
        prof_w = [(a, pt_weight(liked[a], game_avg_pt.get(a, 0.0))) for a in profile]
        excl = set(profile)

        # CF
        scores = cf_scores(prof_w, C, deg, col, args.min_cooc)
        # map matrix-col index -> appid
        inv_col = {j: a for a, j in col.items()}
        order = np.argsort(-scores)
        cf_rec = []
        for j in order:
            if scores[j] <= 0:
                break
            a = inv_col.get(int(j))
            if a is not None and a not in excl:
                cf_rec.append(a)
            if len(cf_rec) >= maxk:
                break

        # POP
        pop_order = np.argsort(-popularity)
        pop_rec = []
        row2appid = {int(r): int(a) for a, r in appid2row.items()}
        for r in pop_order:
            a = row2appid.get(int(r))
            if a is not None and a not in excl:
                pop_rec.append(a)
            if len(pop_rec) >= maxk:
                break

        # ORACLE (ceiling): the hold-out itself
        oracle_rec = list(holdout)[:maxk]

        # LLM
        if not args.no_llm:
            prof_titles_pt = sorted(
                [(appid2title.get(a, str(a)), liked[a] / 60.0) for a in profile],
                key=lambda x: -x[1])[: args.llm_cap]
            llm_rec, miss = llm_recommend(llm, HumanMessage, prof_titles_pt, maxk, pool_lower)
            llm_rec = [a for a in llm_rec if a not in excl]
            llm_miss_total += miss
            llm_n += maxk
        else:
            llm_rec = []

        recs = {"CF": cf_rec, "POP": pop_rec, "ORACLE": oracle_rec, "LLM": llm_rec}
        for s in recs_systems:
            for k in ks:
                metrics[s][f"recall@{k}"].append(recall_at_k(holdout, recs[s], k))
                metrics[s][f"ndcg@{k}"].append(ndcg_at_k(holdout, recs[s], k))
            # debiased: hold-out minus top-5% popular
            hd = {a for a in holdout if ap_pct.get(a, 0.0) < DEBIAS_THR}
            deb_recall[s].append(recall_at_k(hd, recs[s], maxk) if hd else np.nan)
            # long-tail: hold-out below median popularity
            lt = {a for a in holdout if ap_pct.get(a, 0.0) < 0.5}
            lt_recall[s].append(recall_at_k(lt, recs[s], maxk) if lt else np.nan)

        per_user_rows.append({
            "steamid": u, "n_liked": len(appids), "n_profile": len(profile), "n_holdout": len(holdout),
            **{f"{s}_recall@{maxk}": metrics[s][f"recall@{maxk}"][-1] for s in recs_systems},
        })
        if (ui + 1) % 10 == 0:
            log.info("  evaluated %d/%d users", ui + 1, len(test_users))

    # aggregate
    def arr(s, m):
        return np.array(metrics[s][m], dtype=np.float64)

    agg = {}
    for s in recs_systems:
        agg[s] = {}
        for k in ks:
            agg[s][f"recall@{k}"] = bootstrap_ci(arr(s, f"recall@{k}"), B=args.bootstrap, seed=args.seed)
            agg[s][f"ndcg@{k}"] = bootstrap_ci(arr(s, f"ndcg@{k}"), B=args.bootstrap, seed=args.seed)
        agg[s][f"recall@{maxk}_debiased"] = bootstrap_ci(np.array(deb_recall[s]), B=args.bootstrap, seed=args.seed)
        agg[s][f"recall@{maxk}_longtail"] = bootstrap_ci(np.array(lt_recall[s]), B=args.bootstrap, seed=args.seed)

    comparisons = {}
    if not args.no_llm:
        comparisons[f"CF - LLM recall@{maxk}"] = paired_bootstrap_diff(arr("LLM", f"recall@{maxk}"), arr("CF", f"recall@{maxk}"), B=args.bootstrap, seed=args.seed)
        comparisons[f"CF - LLM ndcg@{maxk}"] = paired_bootstrap_diff(arr("LLM", f"ndcg@{maxk}"), arr("CF", f"ndcg@{maxk}"), B=args.bootstrap, seed=args.seed)
        comparisons[f"CF - LLM recall@{maxk}_longtail"] = paired_bootstrap_diff(np.array(lt_recall["LLM"]), np.array(lt_recall["CF"]), B=args.bootstrap, seed=args.seed)
    comparisons[f"CF - POP recall@{maxk}"] = paired_bootstrap_diff(arr("POP", f"recall@{maxk}"), arr("CF", f"recall@{maxk}"), B=args.bootstrap, seed=args.seed)

    # write
    logger = RunLogger(run_id, EXP)
    logger.write_per_query(pd.DataFrame(per_user_rows))
    logger.write_aggregate({"aggregate": agg, "comparisons": comparisons,
                            "llm_pool_miss": (llm_miss_total / llm_n) if llm_n else None})
    logger.write_manifest({
        "run_id": run_id, "phase": "personalization-holdout", "n_test_users": len(test_users),
        "min_liked": args.min_liked, "profile_frac": args.profile_frac, "min_cooc": args.min_cooc,
        "ks": ks, "bootstrap": args.bootstrap, "seed": args.seed, "no_llm": args.no_llm,
        "artifacts": {"scores": fingerprint(args.scores), "index_maps": fingerprint(args.data_dir / "index_maps.json")},
    })

    def ci(s, m):
        c = agg[s][m]
        return f"{c['mean']:.3f} [{c['lo']:.3f},{c['hi']:.3f}]"

    L = [f"# Personalization hold-out — CF (playtime-weighted) vs LLM-with-library (run `{run_id}`)", "",
         f"{len(test_users)} test users, leave-user-out CF, profile {int(args.profile_frac*100)}% / hold-out rest. "
         f"Behavioral ground truth (held-out liked games). 95% bootstrap CI.", ""]
    if not args.no_llm:
        L.append(f"LLM out-of-catalog (pool-miss) rate: {(llm_miss_total/llm_n)*100:.1f}%" if llm_n else "")
    L += ["", "| system | " + " | ".join(f"recall@{k}" for k in ks) + " | " + " | ".join(f"ndcg@{k}" for k in ks) +
          f" | recall@{maxk} debiased | recall@{maxk} long-tail |",
          "|---|" + "---|" * (2 * len(ks) + 2)]
    for s in ["ORACLE", "CF", "LLM", "POP"]:
        if s == "LLM" and args.no_llm:
            continue
        row = [s] + [ci(s, f"recall@{k}") for k in ks] + [ci(s, f"ndcg@{k}") for k in ks]
        row += [ci(s, f"recall@{maxk}_debiased"), ci(s, f"recall@{maxk}_longtail")]
        L.append("| " + " | ".join(row) + " |")
    L += ["", "## Paired comparisons", "", "| comparison | Δ [CI] | significant |", "|---|---|---|"]
    for name, c in comparisons.items():
        L.append(f"| {name} | {c['mean_diff']:+.3f} [{c['lo']:+.3f},{c['hi']:+.3f}] | {c['significant']} |")
    L += ["", "## Decision (pre-registered)", ""]
    if not args.no_llm:
        cf_llm = comparisons[f"CF - LLM recall@{maxk}"]
        lt = comparisons[f"CF - LLM recall@{maxk}_longtail"]
        if cf_llm["significant"] and cf_llm["mean_diff"] > 0:
            L.append("**CF significantly beats LLM-with-library on held-out recall → personalization is a genuine moat → proceed to redesign.**")
        elif lt["significant"] and lt["mean_diff"] > 0:
            L.append("**CF ties overall but significantly beats LLM on the long-tail slice → narrow 'niche personalization' moat.**")
        elif cf_llm["lo"] <= 0 <= cf_llm["hi"]:
            L.append("**No significant CF vs LLM difference → 'just give the LLM your library' is the honest answer; custom CF not justified.**")
        else:
            L.append("**LLM beats CF → personalization via this CF does not justify a custom system.**")
    else:
        L.append("(LLM arm skipped — CF/POP smoke only.)")
    report = "\n".join([x for x in L if x is not None])
    logger.write_report(report)

    logger.append_registry({"run_id": run_id, "phase": "personalization-holdout",
                            "n_users": len(test_users),
                            "recall@%d" % maxk: {s: agg[s][f"recall@{maxk}"]["mean"] for s in recs_systems},
                            "CF_minus_LLM": comparisons.get(f"CF - LLM recall@{maxk}", {}).get("mean_diff"),
                            "llm_pool_miss": (llm_miss_total / llm_n) if llm_n else None})

    # append to DELIBERATION_LOG
    dlog = EXP / "DELIBERATION_LOG.md"
    if dlog.exists():
        with open(dlog, "a", encoding="utf-8") as f:
            f.write(f"\n\n## (실행) 개인화 hold-out 결과 — run `{run_id}`\n")
            f.write(f"- {len(test_users)} users. recall@{maxk}: " +
                    ", ".join(f"{s}={agg[s][f'recall@{maxk}']['mean']:.3f}" for s in recs_systems) + "\n")
            if not args.no_llm:
                c = comparisons[f"CF - LLM recall@{maxk}"]
                f.write(f"- CF−LLM recall@{maxk} = {c['mean_diff']:+.3f} [{c['lo']:+.3f},{c['hi']:+.3f}] "
                        f"({'유의' if c['significant'] else 'ns'}); LLM pool-miss {(llm_miss_total/llm_n)*100:.1f}%\n")
            f.write(f"- 상세: experiments/{run_id}/report.md\n")

    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
