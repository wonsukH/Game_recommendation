"""Deploy smoke: prove the assembled Space payload is self-contained AND that
the app survives Space-like conditions (no GEMINI_API_KEY -> no-LLM mode).

Usage:  python scripts/space_smoke.py          # build payload + run checks
        python scripts/space_smoke.py --inner <payload>   (internal)

Outer: rebuilds deploy/space, then re-runs itself in a subprocess whose env has
NO GEMINI key and whose import root is the PAYLOAD (not the repo) — so a
missing module/data file in the payload fails here, not on the Space.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inner(payload: Path) -> None:
    sys.path.insert(0, str(payload))
    os.chdir(payload)

    # 1) every shipped module at least compiles
    import compileall
    assert compileall.compile_dir(str(payload), quiet=1, force=True), "compile failed"

    # 2) the serving stack loads from payload data alone
    from pipeline.game_rec.agent.ease_recommender import EASERecommender
    from pipeline.game_rec.agent.tools import CatalogMeta
    from serving.agent_graph import build_agentic_graph
    from serving.llm_guard import build_guarded_llm

    data = str(payload / "serving" / "data")
    cf = EASERecommender()
    meta = CatalogMeta(data)
    guard = build_guarded_llm(data)
    assert not guard.has_llm, "env leak: smoke must run WITHOUT a Gemini key"
    graph = build_agentic_graph(cf, meta, guard, data)

    # 3) no-LLM e2e: router falls back -> library route -> EASE recs -> plain reply
    lib = {cf.inv_col[j]: 600.0 for j in range(40) if j in cf.inv_col}
    res = graph.invoke({"user_query": "나한테 맞는 게임 추천해줘", "k": 5,
                        "played": [], "library": lib, "friend_library": {}})
    recs = (res.get("filtered") or res.get("candidates") or [])[:5]
    assert res.get("request_type") == "library", f"route={res.get('request_type')}"
    assert len(recs) == 5, f"recs={recs}"
    assert all(a not in lib for a in recs), "library leak into recs"
    assert res.get("response", "").startswith("추천:"), "fallback reply missing"
    print("INNER PASS: payload self-contained, no-LLM mode serves "
          f"{len(recs)} recs (e.g. {recs[:3]})")


def outer() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_space import build
    payload = ROOT / "deploy" / "space"
    build(payload)
    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    r = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                        "--inner", str(payload)], env=env)
    sys.exit(r.returncode)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--inner":
        inner(Path(sys.argv[2]))
    else:
        outer()
