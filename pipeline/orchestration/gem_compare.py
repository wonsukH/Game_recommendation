"""Fair hidden-gem test — the DISCOVERY use-case done right.

The earlier paradigm judge was unfair to a discovery system: it rewarded
recommending famous best-fit games (Hades, Stardew), which a discovery tool
should NOT do — its user has already played those and wants something NEW.

This test fixes that:
  - LLM-gem  : the LLM is ALSO asked to do discovery ("recommend underrated,
               lesser-known hidden gems, avoid famous blockbusters"). This gives
               the LLM its best shot at the discovery task — but forcing it off
               mainstream may raise hallucination / out-of-catalog picks, which
               is exactly where the system's grounding could finally matter.
  - System Ve: already niche-leaning.
  - Judge    : discovery-framed — "the user has played all the famous games;
               which list better surfaces GOOD lesser-known games they likely
               haven't played? Fame = penalty (already known); non-existent /
               off-fit = penalty." Blinded, Claude + Gemini.

Also measures LLM-gem pool-miss (hallucination/out-of-catalog) and popularity,
since the discovery setting is where grounding stops being free for the LLM.

Subcommands: prepare | gemini | aggregate  (Claude via Workflow)
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.agent.baselines import Catalog  # noqa: E402
from pipeline.game_rec.evaluation.metrics import popularity_percentile  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.gem_compare")
EXP = REPO_ROOT / "experiments"
VARIANTS = ["Ve_system", "LLM_gem"]
LABELS = ["A", "B"]

GEM_PROMPT = (
    "You are a game recommendation assistant for an EXPERIENCED player who has already "
    "played all the famous, mainstream, blockbuster games. Given a Korean query, recommend "
    "exactly 5 real Steam games that fit BUT are lesser-known / underrated 'hidden gems' — "
    "AVOID obvious famous blockbusters (no Hades, Stardew Valley, Witcher 3, Dark Souls, etc.). "
    "Output ONLY the official English Steam title, one per line.\n\nUser query: {q}\n\n5 hidden-gem titles:"
)

JUDGE = (
    "당신은 게임 '발굴' 추천 평가자입니다. 사용자는 이 장르의 유명한 주류 게임은 이미 다 해봤고, "
    "덜 알려졌지만 좋은 '숨은 명작'을 원합니다. 두 익명 시스템(A/B) 중 그런 게임을 더 잘 추천한 쪽을 고르세요.\n"
    "기준: (1) 요청 적합성, (2) 덜 알려진 정도(유명 블록버스터는 이미 알아서 감점), (3) 실존+양질. "
    "없는 게임/엉뚱한 게임은 감점.\n"
    'JSON만 출력: {"winner":"A" 또는 "B","reason":"<간단히>"}'
)


def _gen_gem(llm, query, HumanMessage):
    r = llm.invoke([HumanMessage(content=GEM_PROMPT.format(q=query))])
    text = r.content if hasattr(r, "content") else str(r)
    out = []
    for raw in text.split("\n"):
        c = raw.strip()
        for p in ("- ", "* ", "• "):
            if c.startswith(p):
                c = c[len(p):]
        if len(c) > 2 and c[0].isdigit() and c[1] in ".)":
            c = c[2:].strip()
        if c:
            out.append(c)
    return out[:5]


def prepare(args):
    from dotenv import load_dotenv
    from langchain_core.messages import HumanMessage
    from langchain_google_genai import ChatGoogleGenerativeAI
    load_dotenv(REPO_ROOT / ".env")
    llm = ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"),
                                 google_api_key=os.environ["GEMINI_API_KEY"], temperature=0.4)
    cat = Catalog(REPO_ROOT / "serving" / "data")
    title2appid = {str(v).lower(): k for k, v in cat.appid2title.items()}
    pool_lower = list(title2appid.keys())
    pct = popularity_percentile(cat.popularity)
    ap2row = cat.appid2row

    def match(t):
        tl = t.lower().strip()
        if tl in title2appid:
            return title2appid[tl]
        m = difflib.get_close_matches(tl, pool_lower, n=1, cutoff=0.85)
        return title2appid[m[0]] if m else None

    vibe = {r["id"]: r for r in json.loads((EXP / "vibe_lists.json").read_text(encoding="utf-8"))}
    nl = [{"id": r["id"], "query": r["query"]} for r in vibe.values()]

    rng = np.random.default_rng(args.seed)
    tasks, key, gem_meta = [], [], []
    miss_tot, n_tot, ve_p, gem_p = 0, 0, [], []
    for q in nl:
        try:
            gems = _gen_gem(llm, q["query"], HumanMessage)
        except Exception as e:
            log.warning("gem gen fail %s: %s", q["id"], e); gems = []
        matched = [match(t) for t in gems]
        in_pool = [a for a in matched if a]
        miss = sum(1 for a in matched if a is None)
        miss_tot += miss; n_tot += len(gems)
        gem_p += [pct[ap2row[a]] for a in in_pool if a in ap2row]
        ve_titles = vibe[q["id"]]["Ve_gemini_nn"]
        ve_p += [pct[ap2row[title2appid[t.lower()]]] for t in ve_titles
                 if t.lower() in title2appid and title2appid[t.lower()] in ap2row]

        lists_by_variant = {"Ve_system": ve_titles, "LLM_gem": gems}
        order = list(VARIANTS); rng.shuffle(order)
        mapping = {LABELS[i]: order[i] for i in range(2)}
        tasks.append({"id": q["id"], "query": q["query"],
                      "lists": {LABELS[i]: lists_by_variant[order[i]] for i in range(2)}})
        key.append({"id": q["id"], "label_to_variant": mapping})
        gem_meta.append({"id": q["id"], "llm_gem": gems, "pool_miss": miss, "n": len(gems)})
        log.info("%s gem=%s miss=%d", q["id"], gems[:3], miss)

    (EXP / "gem_tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    (EXP / "gem_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    (EXP / "gem_meta.json").write_text(json.dumps(
        {"pool_miss_rate": miss_tot / max(n_tot, 1), "n": n_tot,
         "ve_pop_pctile": float(np.mean(ve_p)), "gem_pop_pctile": float(np.mean(gem_p)),
         "queries": gem_meta}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"prepared {len(tasks)} tasks | LLM-gem pool-miss {miss_tot/max(n_tot,1):.1%} | "
          f"pop pctile: Ve {np.mean(ve_p):.2f} vs LLM-gem {np.mean(gem_p):.2f}")
    return 0


def _task_text(t):
    return JUDGE + "\n\n사용자 요청: " + t["query"] + "\n\n[A] " + " | ".join(t["lists"]["A"]) + \
        "\n[B] " + " | ".join(t["lists"]["B"])


def _winner(text):
    a, b = text.find("{"), text.rfind("}")
    if a == -1 or b == -1:
        return None
    try:
        w = json.loads(text[a:b + 1]).get("winner")
        return w if w in LABELS else None
    except Exception:
        return None


def gemini(args):
    from dotenv import load_dotenv
    from langchain_core.messages import HumanMessage
    from langchain_google_genai import ChatGoogleGenerativeAI
    load_dotenv(REPO_ROOT / ".env")
    llm = ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"),
                                 google_api_key=os.environ["GEMINI_API_KEY"], temperature=0.0)
    tasks = json.loads((EXP / "gem_tasks.json").read_text(encoding="utf-8"))
    out = []
    for i, t in enumerate(tasks):
        try:
            r = llm.invoke([HumanMessage(content=_task_text(t))])
            w = _winner(r.content if hasattr(r, "content") else str(r))
        except Exception as e:
            log.warning("fail %s: %s", t["id"], e); w = None
        out.append({"id": t["id"], "winner": w}); log.info("[%d/%d] %s -> %s", i + 1, len(tasks), t["id"], w)
    (EXP / "gem_gemini.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def aggregate(args):
    from pipeline.game_rec.evaluation.stats import bootstrap_ci
    key = {r["id"]: r["label_to_variant"] for r in json.loads((EXP / "gem_key.json").read_text(encoding="utf-8"))}
    gem = {r["id"]: r["winner"] for r in json.loads((EXP / "gem_gemini.json").read_text(encoding="utf-8"))}
    cla = {}
    if (EXP / "gem_claude.json").exists():
        cla = {r["id"]: r["winner"] for r in json.loads((EXP / "gem_claude.json").read_text(encoding="utf-8"))}
    meta = json.loads((EXP / "gem_meta.json").read_text(encoding="utf-8"))

    sys_win = []
    for qid in gem:
        votes = []
        for judge in (gem, cla):
            w = judge.get(qid)
            if w:
                votes.append(1.0 if key[qid][w] == "Ve_system" else 0.0)
        if votes:
            sys_win.append(np.mean(votes))
    ci = bootstrap_ci(sys_win, B=2000, seed=42)

    L = ["# Fair hidden-gem test — system (Ve) vs LLM forced into discovery", "",
         f"n={len(sys_win)} NL queries, Claude+Gemini, DISCOVERY-framed judge "
         "(famous = penalty, must be good + lesser-known).", "",
         f"- **System(Ve) win-rate vs LLM-gem: {ci['mean']:.2f} [{ci['lo']:.2f}, {ci['hi']:.2f}]** "
         "(0.5 = tie)",
         f"- LLM-gem out-of-catalog (pool-miss) rate: {meta['pool_miss_rate']*100:.1f}%  "
         f"(vs 2.5% when LLM recommended mainstream — forcing niche {'RAISES' if meta['pool_miss_rate']>0.025 else 'keeps'} hallucination)",
         f"- popularity pctile: Ve {meta['ve_pop_pctile']:.2f} vs LLM-gem {meta['gem_pop_pctile']:.2f} "
         "(both should now be niche)",
         "", "## Verdict", ""]
    m = ci["mean"]
    if ci["lo"] > 0.5:
        L.append("**System significantly beats the LLM at discovery → 'hidden-gem discovery' IS the defensible "
                 "headline: when the obvious games are off the table, the grounded system finds better lesser-known "
                 "fits than the LLM (which hallucinates / weakens off-mainstream).**")
    elif ci["hi"] < 0.5:
        L.append("**LLM still wins even at discovery → the LLM knows enough indie/niche games that the system's "
                 "catalog retrieval is not a clear advantage; hidden-gem discovery is NOT a sufficient moat.**")
    else:
        L.append("**Statistical tie at discovery → the system is competitive with the LLM specifically on the "
                 "discovery task (unlike the best-fit task where it lost ~96%), and it adds grounding "
                 "(no out-of-catalog picks). This is the one framing where the project is defensible.**")
    (EXP / "gem_report.md").write_text("\n".join(L), encoding="utf-8")
    with open(EXP / "registry.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": "gem_compare", "phase": "2f-fair-discovery",
                            "system_winrate_vs_llmgem": ci["mean"], "ci": [ci["lo"], ci["hi"]],
                            "llm_gem_pool_miss": meta["pool_miss_rate"]}, ensure_ascii=False) + "\n")
    print("\n".join(L))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--seed", type=int, default=42)
    sub.add_parser("gemini"); sub.add_parser("aggregate")
    a = ap.parse_args()
    return {"prepare": prepare, "gemini": gemini, "aggregate": aggregate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
