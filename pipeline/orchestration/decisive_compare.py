"""Decisive test — do tags earn their place, or is pure LLM-on-descriptions enough?

Compares 3 ways to answer a natural-language game query:
  Ve_through_tags : query -Gemini-NN-> tags -vote-weighted tag-cosine-> games
                    (the fix; routes through the community vote-weighted tag layer)
  Vb_through_tags : query -parser tags-> vote-weighted tag-cosine -> games
                    (also through tags, no SVD/no Gemini-NN)
  Vf_llm_desc     : query -Gemini embed-> cosine vs game DESCRIPTION embeddings
                    -> games  (NO tags, NO vote weighting, NO custom embedding)

If Vf >= Ve, the tag layer (and thus the project's reason to exist beyond
generic LLM-RAG over descriptions) is redundant. If Ve > Vf, the vote-weighted,
interpretable tag layer genuinely adds quality. Judged blind by Claude + Gemini.

Subcommands: prepare | gemini | aggregate  (Claude via Workflow, like vibe_judge)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from sklearn.preprocessing import normalize

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.agent.baselines import Catalog  # noqa: E402
from pipeline.game_rec.io import load_vectors  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.decisive")
EXP = REPO_ROOT / "experiments"
VARIANTS = ["Ve_through_tags", "Vb_through_tags", "Vf_llm_desc"]
LABELS = ["A", "B", "C"]

INSTR = (
    "당신은 게임 추천 품질 평가자입니다. 한국어 사용자 요청에 대해 3개 익명 시스템(A/B/C)이 각각 "
    "게임 5개를 추천했습니다. 사용자의 의도(장르·분위기·제약)에 가장 잘 맞는 추천을 한 시스템부터 "
    "순위를 매기세요. 모르는 게임은 제목으로 합리적으로 추정하세요.\n"
    'JSON만 출력: {"ranking":["<best>",...,"<worst>"],"reason":"<간단히>"}'
)


def _vf_lists(queries, embeddings, top_k):
    cat = Catalog(REPO_ROOT / "serving" / "data")
    G = normalize(load_vectors(EXP / "game_desc_vecs.npy", "float64"), norm="l2", axis=1)
    out = {}
    for q in queries:
        v = np.array(embeddings.embed_query(q["query"]), dtype=np.float64)
        v = v / max(np.linalg.norm(v), 1e-12)
        scores = G @ v
        k = min(top_k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        out[q["id"]] = [cat.appid2title.get(int(cat.row2appid[int(r)]), str(r)) for r in top]
        log.info("Vf %s -> %s", q["id"], out[q["id"]][:3])
    return out


def prepare(args):
    from dotenv import load_dotenv
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    load_dotenv(REPO_ROOT / ".env")
    emb = GoogleGenerativeAIEmbeddings(
        model=os.environ.get("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-2"),
        google_api_key=os.environ["GEMINI_API_KEY"])
    vibe = json.loads((EXP / "vibe_lists.json").read_text(encoding="utf-8"))
    queries = [{"id": r["id"], "query": r["query"]} for r in vibe]
    vf = _vf_lists(queries, emb, args.top_k)
    (EXP / "decisive_vf_lists.json").write_text(json.dumps(vf, ensure_ascii=False, indent=2), encoding="utf-8")

    by_id = {r["id"]: r for r in vibe}
    rng = np.random.default_rng(args.seed)
    tasks, key = [], []
    for q in queries:
        r = by_id[q["id"]]
        variant_lists = {
            "Ve_through_tags": r.get("Ve_gemini_nn", []),
            "Vb_through_tags": r.get("Vb_tagcosine", []),
            "Vf_llm_desc": vf.get(q["id"], []),
        }
        order = list(VARIANTS); rng.shuffle(order)
        mapping = {LABELS[i]: order[i] for i in range(3)}
        lists = {LABELS[i]: variant_lists[order[i]] for i in range(3)}
        tasks.append({"id": q["id"], "query": q["query"], "lists": lists})
        key.append({"id": q["id"], "label_to_variant": mapping})
    (EXP / "decisive_tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    (EXP / "decisive_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("prepared %d decisive 3-way tasks", len(tasks))
    print(f"prepared {len(tasks)} tasks")
    return 0


def _task_text(t):
    s = INSTR + "\n\n사용자 요청: " + t["query"] + "\n\n"
    for lab in LABELS:
        s += f"[{lab}] " + " | ".join(t["lists"][lab]) + "\n"
    return s


def _parse(text):
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


def gemini(args):
    from dotenv import load_dotenv
    from langchain_core.messages import HumanMessage
    from langchain_google_genai import ChatGoogleGenerativeAI
    load_dotenv(REPO_ROOT / ".env")
    llm = ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"),
                                 google_api_key=os.environ["GEMINI_API_KEY"], temperature=0.0)
    tasks = json.loads((EXP / "decisive_tasks.json").read_text(encoding="utf-8"))
    out = []
    for i, t in enumerate(tasks):
        try:
            resp = llm.invoke([HumanMessage(content=_task_text(t))])
            ranking = _parse(resp.content if hasattr(resp, "content") else str(resp))
        except Exception as e:
            log.warning("gemini fail %s: %s", t["id"], e); ranking = None
        out.append({"id": t["id"], "ranking": ranking})
        log.info("[%d/%d] %s -> %s", i + 1, len(tasks), t["id"], ranking)
    (EXP / "decisive_gemini.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def _borda(rankings, key):
    k2v = {r["id"]: r["label_to_variant"] for r in key}
    pts = {v: [] for v in VARIANTS}
    per_q = {}
    for qid, rk in rankings.items():
        if not rk:
            continue
        m = k2v.get(qid, {}); per_q[qid] = {}
        for pos, lab in enumerate(rk):
            v = m.get(lab)
            if v:
                pts[v].append(3 - pos); per_q[qid][v] = 3 - pos  # 1st=3..3rd=1
    return pts, per_q


def aggregate(args):
    from pipeline.game_rec.evaluation.stats import bootstrap_ci, paired_bootstrap_diff
    key = json.loads((EXP / "decisive_key.json").read_text(encoding="utf-8"))
    gem = {r["id"]: r["ranking"] for r in json.loads((EXP / "decisive_gemini.json").read_text(encoding="utf-8"))}
    cla = {}
    if (EXP / "decisive_claude.json").exists():
        cla = {r["id"]: r["ranking"] for r in json.loads((EXP / "decisive_claude.json").read_text(encoding="utf-8"))}

    _, gq = _borda(gem, key)
    _, cq = _borda(cla, key) if cla else (None, {})
    ids = [q for q in gq if (not cla or q in cq)]
    combined = {v: [] for v in VARIANTS}
    for q in ids:
        for v in VARIANTS:
            vals = [gq[q][v]]
            if cla and q in cq:
                vals.append(cq[q][v])
            combined[v].append(np.mean(vals))
    combined = {v: np.array(x) for v, x in combined.items()}

    L = ["# Decisive test — tags vs pure LLM-on-descriptions (blinded)", "",
         f"3-way blind ranking, n={len(ids)} NL queries, Borda 1st=3..3rd=1, "
         f"combined Claude+Gemini. Higher = better.", "",
         "| variant | combined Borda [95% CI] |", "|---|---|"]
    cis = {}
    for v in VARIANTS:
        c = bootstrap_ci(combined[v], B=2000, seed=42); cis[v] = c
        L.append(f"| {v} | {c['mean']:.2f} [{c['lo']:.2f}, {c['hi']:.2f}] |")
    dve_vf = paired_bootstrap_diff(combined["Vf_llm_desc"], combined["Ve_through_tags"], B=2000, seed=42)
    dvb_vf = paired_bootstrap_diff(combined["Vf_llm_desc"], combined["Vb_through_tags"], B=2000, seed=42)
    L += ["", "## Paired (combined Borda)",
          f"- Ve_through_tags − Vf_llm_desc = {dve_vf['mean_diff']:+.2f} [{dve_vf['lo']:+.2f},{dve_vf['hi']:+.2f}] "
          f"({'SIG' if dve_vf['significant'] else 'ns'})",
          f"- Vb_through_tags − Vf_llm_desc = {dvb_vf['mean_diff']:+.2f} [{dvb_vf['lo']:+.2f},{dvb_vf['hi']:+.2f}] "
          f"({'SIG' if dvb_vf['significant'] else 'ns'})",
          "", "## Verdict", ""]
    best = max(VARIANTS, key=lambda v: cis[v]["mean"])
    if best == "Vf_llm_desc" or (dve_vf["significant"] and dve_vf["mean_diff"] < 0):
        L.append("**Pure LLM-on-descriptions wins/ties → the tag layer is REDUNDANT. The project's "
                 "distinctive value over generic LLM-RAG is not supported by the data.**")
    elif dve_vf["significant"] and dve_vf["mean_diff"] > 0:
        L.append("**Through-tags (Ve) significantly beats pure LLM-on-descriptions → the vote-weighted, "
                 "interpretable tag layer genuinely adds quality. The project's core IS defensible (as a "
                 "tag-routing layer, not as custom embedding ML).**")
    else:
        L.append("**No significant difference → tags neither help nor hurt quality; their only remaining "
                 "justification is interpretability, not measured quality.**")
    (EXP / "decisive_report.md").write_text("\n".join(L), encoding="utf-8")
    with open(EXP / "registry.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": "decisive_tags_vs_llm", "phase": "2d-decisive",
                            "borda": {v: cis[v]["mean"] for v in VARIANTS},
                            "Ve_minus_Vf": dve_vf["mean_diff"], "sig": dve_vf["significant"]},
                           ensure_ascii=False) + "\n")
    print("\n".join(L))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--seed", type=int, default=42); p.add_argument("--top-k", type=int, default=5)
    sub.add_parser("gemini")
    sub.add_parser("aggregate")
    a = ap.parse_args()
    return {"prepare": prepare, "gemini": gemini, "aggregate": aggregate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
