"""Paradigm judge — generative LLM-alone vs the system (Ve), blinded.

The user's question: with grounding/hallucination being weak advantages
(LLM pool-miss only 2.5%), is "just ask the LLM" simply better? This judges
the LLM's ACTUAL output (5 named games, incl. any out-of-pool) against the
system's Ve recommendations, blind, with Claude + Gemini.

The bar for the long-tail headline: the system is much more niche (pop pctile
0.59 vs 0.89). If it MATCHES the LLM on judged quality while being more niche,
long-tail discovery is a real, defensible headline. If it loses clearly, the
niche-ness is partly just worse recommendations.

Subcommands: prepare | gemini | aggregate  (Claude via Workflow)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.paradigm_judge")
EXP = REPO_ROOT / "experiments"
VARIANTS = ["Ve_system", "LLM_alone"]
LABELS = ["A", "B"]

INSTR = (
    "당신은 게임 추천 품질 평가자입니다. 한국어 사용자 요청에 대해 2개 익명 시스템(A/B)이 각각 게임 5개를 "
    "추천했습니다. 사용자의 의도(장르·분위기·제약)에 더 잘 맞는 추천을 한 쪽을 고르세요. 유명세가 아니라 "
    "요청 적합성으로 판단하세요. 모르는 게임은 제목으로 추정.\n"
    'JSON만 출력: {"winner":"A" 또는 "B","reason":"<간단히>"}'
)


def prepare(args):
    vibe = {r["id"]: r for r in json.loads((EXP / "vibe_lists.json").read_text(encoding="utf-8"))}
    la = {q["id"]: q for q in json.loads((EXP / "llm_alone_lists.json").read_text(encoding="utf-8"))["queries"]}
    rng = np.random.default_rng(args.seed)
    tasks, key = [], []
    for qid in la:
        lists_by_variant = {"Ve_system": vibe[qid]["Ve_gemini_nn"], "LLM_alone": la[qid]["llm_raw"]}
        order = list(VARIANTS); rng.shuffle(order)
        mapping = {LABELS[i]: order[i] for i in range(2)}
        tasks.append({"id": qid, "query": vibe[qid]["query"],
                      "lists": {LABELS[i]: lists_by_variant[order[i]] for i in range(2)}})
        key.append({"id": qid, "label_to_variant": mapping})
    (EXP / "paradigm_tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    (EXP / "paradigm_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"prepared {len(tasks)} 2-way tasks")
    return 0


def _task_text(t):
    s = INSTR + "\n\n사용자 요청: " + t["query"] + "\n\n"
    for lab in LABELS:
        s += f"[{lab}] " + " | ".join(t["lists"][lab]) + "\n"
    return s


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
    tasks = json.loads((EXP / "paradigm_tasks.json").read_text(encoding="utf-8"))
    out = []
    for i, t in enumerate(tasks):
        try:
            r = llm.invoke([HumanMessage(content=_task_text(t))])
            w = _winner(r.content if hasattr(r, "content") else str(r))
        except Exception as e:
            log.warning("fail %s: %s", t["id"], e); w = None
        out.append({"id": t["id"], "winner": w})
        log.info("[%d/%d] %s -> %s", i + 1, len(tasks), t["id"], w)
    (EXP / "paradigm_gemini.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def aggregate(args):
    from pipeline.game_rec.evaluation.stats import bootstrap_ci
    key = {r["id"]: r["label_to_variant"] for r in json.loads((EXP / "paradigm_key.json").read_text(encoding="utf-8"))}
    gem = {r["id"]: r["winner"] for r in json.loads((EXP / "paradigm_gemini.json").read_text(encoding="utf-8"))}
    cla = {}
    if (EXP / "paradigm_claude.json").exists():
        cla = {r["id"]: r["winner"] for r in json.loads((EXP / "paradigm_claude.json").read_text(encoding="utf-8"))}

    # per-query: 1 if Ve_system won, 0 if LLM_alone won (averaged over judges present)
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

    la = json.loads((EXP / "llm_alone_lists.json").read_text(encoding="utf-8"))
    L = ["# Paradigm judge — system (Ve) vs generative LLM-alone (blinded)", "",
         f"n={len(sys_win)} NL queries, Claude+Gemini. Value = fraction where the SYSTEM (Ve) was judged better.", "",
         f"- **System(Ve) win-rate vs LLM-alone: {ci['mean']:.2f} [{ci['lo']:.2f}, {ci['hi']:.2f}]** "
         f"(0.5 = tie; <0.5 means LLM-alone judged better)",
         f"- LLM-alone out-of-catalog (pool-miss) rate: {la['pool_miss_rate']*100:.1f}%",
         "- Popularity percentile: system 0.59 (niche) vs LLM-alone 0.89 (mainstream)",
         "", "## Verdict", ""]
    m = ci["mean"]
    if m >= 0.5 or (ci["lo"] <= 0.5 <= ci["hi"]):
        L.append("**System matches/beats LLM-alone on judged quality WHILE being much more niche → long-tail "
                 "discovery is a DEFENSIBLE headline (more niche, not worse).**" if m >= 0.45 else "")
    if m < 0.45 and ci["hi"] < 0.5:
        L.append("**LLM-alone is judged better → the system's niche-ness is partly just lower quality; "
                 "'long-tail' alone is NOT a sufficient headline (must pair with a use-case needing the catalog).**")
    elif ci["lo"] <= 0.5 <= ci["hi"]:
        L.append("**No significant quality difference → system ties LLM-alone on quality but is far more niche → "
                 "long-tail discovery IS a defensible, honest differentiator.**")
    (EXP / "paradigm_report.md").write_text("\n".join([x for x in L if x is not None]), encoding="utf-8")
    with open(EXP / "registry.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": "paradigm_judge", "phase": "2e-paradigm",
                            "system_winrate_vs_llm": ci["mean"], "ci": [ci["lo"], ci["hi"]],
                            "llm_pool_miss": la["pool_miss_rate"]}, ensure_ascii=False) + "\n")
    print("\n".join([x for x in L if x]))
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
