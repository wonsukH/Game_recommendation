"""Generative LLM-alone recommendations + grounding measurement.

The 4th paradigm for "is just asking the LLM best?": ask Gemini to NAME 5 games
for each query (pure generation, no retrieval). Then measure GROUNDING — what
fraction of named games actually exist in our 9,956 operatable pool (fuzzy
title match). Pure generation's known weakness is exactly this: it can name
games outside the catalog or hallucinate, which retrieval (Vf/Ve) never does.

Judged quality is reported by the paradigm judge; grounding is reported here.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from langchain_core.messages import HumanMessage  # noqa: E402
from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.llm_alone")
EXP = REPO_ROOT / "experiments"


def gen_titles(llm, query: str) -> list[str]:
    prompt = (
        "You are a game recommendation assistant. The user gives a Korean query.\n"
        "Recommend exactly 5 real Steam games that match. Output ONLY the official English "
        "Steam title of each, one per line. No numbering, no descriptions.\n\n"
        f"User query: {query}\n\n5 titles:"
    )
    resp = llm.invoke([HumanMessage(content=prompt)])
    text = resp.content if hasattr(resp, "content") else str(resp)
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries", type=Path, default=REPO_ROOT / "tests" / "eval_queries.json")
    ap.add_argument("--data-dir", type=Path, default=REPO_ROOT / "serving" / "data")
    ap.add_argument("--out", type=Path, default=EXP / "llm_alone_lists.json")
    args = ap.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    llm = ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-pro"),
                                 google_api_key=os.environ["GEMINI_API_KEY"], temperature=0.2)
    games = pd.read_csv(args.data_dir / "steam_games_tags.csv")
    pool_titles = games["game_title"].astype(str).tolist()
    pool_lower = {t.lower(): t for t in pool_titles}

    def match(title: str):
        t = title.lower().strip()
        if t in pool_lower:
            return pool_lower[t]
        m = difflib.get_close_matches(t, pool_lower.keys(), n=1, cutoff=0.85)
        return pool_lower[m[0]] if m else None

    queries = json.loads(args.queries.read_text(encoding="utf-8"))
    nl = [q for q in queries if not q.get("category", "").startswith("similar")]
    out, miss_total, n_total = [], 0, 0
    for i, q in enumerate(nl):
        try:
            raw = gen_titles(llm, q["query"])
        except Exception as e:
            log.warning("gen failed %s: %s", q.get("id"), e); raw = []
        matched = [match(t) for t in raw]
        in_pool = [m for m in matched if m]
        miss = sum(1 for m in matched if m is None)
        miss_total += miss; n_total += len(raw)
        out.append({"id": q["id"], "query": q["query"], "llm_raw": raw,
                    "in_pool": in_pool, "pool_miss": miss, "n": len(raw)})
        log.info("[%d/%d] %s miss=%d/%d", i + 1, len(nl), q["id"], miss, len(raw))
    rate = miss_total / max(n_total, 1)
    payload = {"pool_miss_rate": rate, "n_titles": n_total, "queries": out}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("LLM-alone done: pool-miss rate %.3f over %d titles", rate, n_total)
    print(f"pool-miss (hallucination/out-of-catalog) rate: {rate:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
