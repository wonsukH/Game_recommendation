"""Phase 2c — blinded judge for vibe variants (the quality verdict).

Vibe mode has no clean non-circular label, so quality is judged by independent
LLMs that did NOT build the system:

- The 4 variant lists per query (Vb tag-cosine, Vc SVD-tags, Vd W_align,
  Ve Gemini-NN fix) are ANONYMIZED + SHUFFLED to A/B/C/D (blind: the judge
  never sees which method produced which list).
- Two independent judges rank them: **Gemini** (API, here) and **Claude**
  (via sub-agents / Workflow, orchestrated by the main agent — no API key
  needed). Cross-model agreement guards against self-preference: the system
  uses Gemini, so Claude is the key independent judge.

Subcommands:
  prepare   -> vibe_judge_tasks.json (anonymized) + vibe_judge_key.json (mapping)
  gemini    -> vibe_judge_gemini.json (Gemini rankings)
  aggregate -> vibe_judge_report.md  (de-anonymize, Borda, agreement) + registry

Claude rankings are produced by a Workflow the main agent runs, written to
vibe_judge_claude.json, then folded in by `aggregate`.
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

log = get_logger("orchestration.vibe_judge")

EXP = REPO_ROOT / "experiments"
VARIANTS = ["Vb_tagcosine", "Vc_svd_tags", "Vd_walign", "Ve_gemini_nn"]
LABELS = ["A", "B", "C", "D"]

JUDGE_INSTRUCTION = (
    "당신은 게임 추천 품질 평가자입니다. 아래 한국어 사용자 요청에 대해 4개의 추천 시스템"
    "(A/B/C/D)이 각각 게임 5개를 추천했습니다. 어느 시스템이 사용자의 의도(장르·분위기·제약)"
    "에 가장 잘 맞는 게임들을 추천했는지 가장 좋은 것부터 나쁜 것 순으로 순위를 매기세요.\n"
    "관련성과 적절성을 보세요. 모르는 게임은 제목으로 합리적으로 추정하세요.\n"
    'JSON만 출력: {"ranking": ["<best label>", ..., "<worst label>"], "reason": "<간단한 이유>"}'
)


def _task_text(task: dict) -> str:
    lines = [JUDGE_INSTRUCTION, "", f"사용자 요청: {task['query']}", ""]
    for lab in LABELS:
        lines.append(f"[{lab}] " + " | ".join(task["lists"][lab]))
    return "\n".join(lines)


def prepare(args) -> int:
    data = json.loads((EXP / "vibe_lists.json").read_text(encoding="utf-8"))
    rng = np.random.default_rng(args.seed)
    tasks, key = [], []
    for rec in data:
        order = list(VARIANTS)
        rng.shuffle(order)  # variant -> label by position
        mapping = {LABELS[i]: order[i] for i in range(4)}
        lists = {LABELS[i]: rec.get(order[i], []) for i in range(4)}
        tasks.append({"id": rec["id"], "category": rec["category"],
                      "query": rec["query"], "lists": lists})
        key.append({"id": rec["id"], "label_to_variant": mapping})
    (EXP / "vibe_judge_tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    (EXP / "vibe_judge_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("prepared %d blinded judge tasks", len(tasks))
    print(f"prepared {len(tasks)} tasks -> {EXP/'vibe_judge_tasks.json'}")
    return 0


def _parse_ranking(text: str) -> list | None:
    a, b = text.find("{"), text.rfind("}")
    if a == -1 or b == -1:
        return None
    try:
        r = json.loads(text[a:b + 1]).get("ranking")
        if isinstance(r, list) and sorted(r) == sorted(LABELS):
            return r
    except Exception:
        return None
    return None


def gemini(args) -> int:
    from dotenv import load_dotenv
    from langchain_core.messages import HumanMessage
    from langchain_google_genai import ChatGoogleGenerativeAI
    load_dotenv(REPO_ROOT / ".env")
    llm = ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"),
                                 google_api_key=os.environ["GEMINI_API_KEY"], temperature=0.0)
    tasks = json.loads((EXP / "vibe_judge_tasks.json").read_text(encoding="utf-8"))
    out = []
    for i, t in enumerate(tasks):
        try:
            resp = llm.invoke([HumanMessage(content=_task_text(t))])
            ranking = _parse_ranking(resp.content if hasattr(resp, "content") else str(resp))
        except Exception as e:
            log.warning("gemini judge failed on %s: %s", t["id"], e)
            ranking = None
        out.append({"id": t["id"], "ranking": ranking})
        log.info("[%d/%d] %s -> %s", i + 1, len(tasks), t["id"], ranking)
    (EXP / "vibe_judge_gemini.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def _borda(rankings_by_id: dict, key: list) -> dict:
    """Borda points per VARIANT (de-anonymized). 1st=4 ... 4th=1."""
    k2v = {row["id"]: row["label_to_variant"] for row in key}
    pts = {v: [] for v in VARIANTS}
    for qid, ranking in rankings_by_id.items():
        if not ranking:
            continue
        mapping = k2v.get(qid, {})
        for pos, lab in enumerate(ranking):
            variant = mapping.get(lab)
            if variant:
                pts[variant].append(4 - pos)  # 1st->4 ... 4th->1
    return pts


def aggregate(args) -> int:
    key = json.loads((EXP / "vibe_judge_key.json").read_text(encoding="utf-8"))
    gem = {r["id"]: r["ranking"] for r in json.loads((EXP / "vibe_judge_gemini.json").read_text(encoding="utf-8"))}
    claude_path = EXP / "vibe_judge_claude.json"
    cla = {}
    if claude_path.exists():
        cla = {r["id"]: r["ranking"] for r in json.loads(claude_path.read_text(encoding="utf-8"))}

    gem_pts = _borda(gem, key)
    cla_pts = _borda(cla, key) if cla else {v: [] for v in VARIANTS}

    def mean(d, v):
        return float(np.mean(d[v])) if d[v] else float("nan")

    # cross-judge top-1 agreement
    k2v = {row["id"]: row["label_to_variant"] for row in key}
    agree = []
    for qid in gem:
        if gem.get(qid) and cla.get(qid):
            g1 = k2v[qid].get(gem[qid][0]); c1 = k2v[qid].get(cla[qid][0])
            agree.append(g1 == c1)
    top1_agree = float(np.mean(agree)) if agree else float("nan")

    L = ["# Phase 2c — Vibe judge (blinded, Claude + Gemini)", "",
         f"4 variants ranked per query, anonymized A/B/C/D. Borda: 1st=4..4th=1, "
         f"averaged across {len(gem)} NL queries. Higher = better.", "",
         "| variant | Gemini Borda | Claude Borda |", "|---|---|---|"]
    for v in VARIANTS:
        L.append(f"| {v} | {mean(gem_pts,v):.2f} | {mean(cla_pts,v):.2f} |")
    L += ["", f"- Cross-judge top-1 agreement: {top1_agree:.2f}" if agree else "- Claude rankings not yet folded in.",
          "", "## Reading",
          "- Higher Borda = judges preferred that method's recommendations.",
          "- Ve (Gemini-NN fix) vs Vd (W_align): tests whether the newer method beats the broken ridge.",
          "- Ve/Vb vs Vc: whether SVD helps vibe quality (Phase 1 said it hurt similar).",
          "- Cross-model agreement guards against self-preference (system uses Gemini → Claude is independent)."]
    (EXP / "vibe_judge_report.md").write_text("\n".join(L), encoding="utf-8")

    # registry
    with open(EXP / "registry.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": "vibe_judge", "phase": "2c-vibe-judge",
                            "gemini_borda": {v: mean(gem_pts, v) for v in VARIANTS},
                            "claude_borda": {v: mean(cla_pts, v) for v in VARIANTS},
                            "top1_agreement": top1_agree}, ensure_ascii=False) + "\n")
    print("\n".join(L))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--seed", type=int, default=42)
    sub.add_parser("gemini")
    sub.add_parser("aggregate")
    args = ap.parse_args()
    return {"prepare": prepare, "gemini": gemini, "aggregate": aggregate}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
