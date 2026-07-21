"""P8 — end-to-end route verification with the REAL Gemini router (attended).

Drives the actual serving graph (`build_agentic_graph` + `graph.invoke`) — the
same code path as the Streamlit app minus the UI — across the six route
families, using the app's own example prompts as the corpus. This is the layer
the LLM-bypassed p5_smoke could not touch: routing, constraint extraction,
steer extraction, anonymous title mapping, critic/refine, response generation.

Costs real Gemini calls (~4 per case) — run ATTENDED only.

Per case asserts:
  route      resolved request_type ∈ expected set (post-demotion rules)
  cands      candidates non-empty
  filter     every filtered item satisfies the extracted constraints (via meta)
  response   non-empty final text
Outputs experiments/p8_e2e/<tag>/report.md + cases.json (full state dumps).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from pipeline.game_rec.agent.ease_recommender import EASERecommender  # noqa: E402
from pipeline.game_rec.agent.steam_library import proxy_library  # noqa: E402
from pipeline.game_rec.agent.tools import CatalogMeta  # noqa: E402
from pipeline.game_rec.log import get_logger  # noqa: E402

log = get_logger("orchestration.p8_e2e")

DATA = str(REPO_ROOT / "serving" / "data")
OUT = REPO_ROOT / "experiments" / "p8_e2e"

# corpus == main_agent.EXAMPLES (can't import: it boots Streamlit). One case
# per route family + both constraint chips. `expected` allows for the router's
# documented demotions.
CASES = [
    {"id": "library", "query": "나한테 맞는 게임 추천해줘", "lib": True,
     "friend": False, "expected": {"library"}},
    {"id": "seed", "query": "다크소울 같은 거", "lib": True, "friend": False,
     "expected": {"seed"}},
    {"id": "explore", "query": "안 해본 새로운 장르로 색다른 거", "lib": True,
     "friend": False, "expected": {"explore"}},
    {"id": "multi", "query": "나랑 친구 둘 다 좋아할 게임", "lib": True,
     "friend": True, "expected": {"multi_entity"}},
    {"id": "constraint_coop_kr", "query": "협동 가능하고 한국어 되는 게임",
     "lib": True, "friend": False, "expected": {"library", "anonymous"}},
    {"id": "constraint_price", "query": "2만원 이하 협동 게임", "lib": True,
     "friend": False, "expected": {"library", "anonymous"}},
    {"id": "anonymous_no_lib", "query": "차분하고 분위기 좋은 인디 게임",
     "lib": False, "friend": False, "expected": {"anonymous", "general"}},
]


def check_constraints(meta: CatalogMeta, appids, cons: dict) -> list[str]:
    """Return violation strings for filtered items vs extracted constraints."""
    bad = []
    for a in appids:
        m = meta.meta.get(int(a))
        if m is None:
            bad.append(f"{a}: no metadata survived filter")
            continue
        for key in ("coop", "multiplayer", "single_player", "korean"):
            if cons.get(key) and not m.get(key):
                bad.append(f"{a}: fails {key}")
        if cons.get("free") and not m["is_free"]:
            bad.append(f"{a}: not free")
        if cons.get("max_price") is not None:
            if m["price"] is None or m.get("currency", "KRW") != "KRW" \
                    or m["price"] > float(cons["max_price"]):
                bad.append(f"{a}: price {m['price']} {m.get('currency')} "
                           f"> {cons['max_price']}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", default="run1")
    ap.add_argument("--only", default="", help="comma list of case ids")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--sleep", type=float, default=20.0,
                    help="pause between cases (free-tier RPM headroom)")
    args = ap.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set — attended run required")
        return 1
    from langchain_google_genai import ChatGoogleGenerativeAI
    from serving.agent_graph import build_agentic_graph

    cf = EASERecommender()
    meta = CatalogMeta(DATA)
    llm = ChatGoogleGenerativeAI(
        model=os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-flash"),
        google_api_key=os.environ["GEMINI_API_KEY"], temperature=0.3)
    graph = build_agentic_graph(cf, meta, llm, DATA)
    lib = proxy_library(min_liked=10, seed=3)
    friend = proxy_library(min_liked=10, seed=5)

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    out_dir = OUT / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, dumps = [], {}
    first = True
    for case in CASES:
        if only and case["id"] not in only:
            continue
        if not first:
            time.sleep(args.sleep)
        first = False
        state = {"user_query": case["query"], "k": args.k, "played": [],
                 "library": dict(lib) if case["lib"] else {},
                 "friend_library": dict(friend) if case["friend"] else {}}
        t0 = time.time()
        try:
            res = graph.invoke(state)
            err = None
        except Exception as e:  # noqa: BLE001 — e2e must record, not die
            res, err = {}, f"{type(e).__name__}: {e}"
        dt = time.time() - t0
        route = res.get("request_type")
        cons = res.get("constraints") or {}
        cands = res.get("candidates") or []
        filtered = res.get("filtered") or []
        final = filtered or cands
        resp = (res.get("response") or "").strip()
        violations = check_constraints(meta, filtered, cons) if cons else []
        checks = {
            "no_error": err is None,
            "route_ok": route in case["expected"],
            "cands_nonempty": len(cands) > 0,
            "constraints_respected": not violations,
            "response_nonempty": len(resp) > 0,
        }
        rows.append({"case": case["id"], "query": case["query"], "route": route,
                     "expected": sorted(case["expected"]), "n_cands": len(cands),
                     "n_filtered": len(filtered), "constraints": cons,
                     "violations": violations[:5], "steer": res.get("steer"),
                     "relaxed": res.get("relaxed"), "sec": round(dt, 1),
                     "error": err, **{f"ok_{k}": v for k, v in checks.items()},
                     "PASS": all(checks.values())})
        dumps[case["id"]] = {
            "state_out": {k: v for k, v in res.items()
                          if k not in ("library", "friend_library")},
            "top_final": final[:10], "response": resp}
        log.info("%s: route=%s cands=%d filtered=%d %s (%.1fs)%s",
                 case["id"], route, len(cands), len(filtered),
                 "PASS" if rows[-1]["PASS"] else "FAIL", dt,
                 f" ERR={err}" if err else "")

    (out_dir / "cases.json").write_text(
        json.dumps(dumps, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    md = ["# P8 e2e — " + args.tag, "",
          f"> **유형**: eval-output · **상태**: active · **갱신**: "
          f"{time.strftime('%Y-%m-%d')}", ""]
    for r in rows:
        md.append(f"## {r['case']} — {'PASS' if r['PASS'] else '**FAIL**'}")
        md.append(f"- query: {r['query']}")
        md.append(f"- route: {r['route']} (expected {r['expected']}) | "
                  f"cands {r['n_cands']} → filtered {r['n_filtered']} | {r['sec']}s")
        if r["constraints"]:
            md.append(f"- constraints: {r['constraints']} | relaxed: {r['relaxed']}")
        if r["violations"]:
            md.append(f"- VIOLATIONS: {r['violations']}")
        if r["error"]:
            md.append(f"- ERROR: {r['error']}")
        failing = [k for k, v in r.items() if k.startswith("ok_") and not v]
        if failing:
            md.append(f"- failing checks: {failing}")
        md.append("")
    n_pass = sum(r["PASS"] for r in rows)
    md.append(f"**{n_pass}/{len(rows)} PASS**")
    (out_dir / "report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0 if n_pass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
