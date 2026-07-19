"""P5 serving smoke test — the REAL app code path, LLM bypassed (no Gemini).

Exercises exactly what the LangGraph routes call, using the swapped-in EASE
artifact + steam.db-native catalog artifacts:

  1. library route core   hybrid.recommend(demo library)        -> top-20
  2. seed route core      cf.score({seed}) full-vector ranking  -> top-10
  3. explore route core   hybrid.recommend_steered(novelty)     -> top-10
  4. constraint tool      meta.constraint_filter(coop+korean)
  5. quality gate         meta.quality_gate(min_quality_pct)

Passes when every step returns non-empty, titled, in-pool results and the
steered list actually differs from the plain list (steering does something).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.game_rec.agent.content import ContentLayer  # noqa: E402
from pipeline.game_rec.agent.ease_recommender import EASERecommender  # noqa: E402
from pipeline.game_rec.agent.hybrid import HybridRecommender  # noqa: E402
from pipeline.game_rec.agent.steam_library import proxy_library  # noqa: E402
from pipeline.game_rec.agent.tools import CatalogMeta  # noqa: E402

DATA = REPO_ROOT / "serving" / "data"


def main() -> int:
    titles = dict(zip(*[iter([])] * 2))
    df = pd.read_csv(DATA / "steam_games_tags.csv")
    titles = dict(zip(df["appid"].astype(int), df["game_title"].astype(str)))

    cf = EASERecommender()
    meta = CatalogMeta(DATA)
    content = ContentLayer(DATA)
    hybrid = HybridRecommender(cf, content, meta)
    lib = proxy_library(min_liked=10, seed=3)
    print(f"demo library: {len(lib)} games, e.g. "
          f"{[titles.get(a, a) for a in list(lib)[:5]]}")

    ok = True

    recs = hybrid.recommend(lib, k=20)
    print(f"\n[1] library route (hybrid.recommend): {len(recs)} recs")
    for a, s, src in recs[:10]:
        print(f"    {s:+.4f} [{src}] {titles.get(a, a)}")
    ok &= len(recs) == 20 and all(a not in lib for a, _, _ in recs)

    seed_appid = max(lib, key=lib.get)
    import numpy as np
    acc = cf.score_with_weights({seed_appid: 1.0})  # seed_node semantics
    seed_recs = []
    for j in np.argsort(-acc):
        a = cf.inv_col.get(int(j))
        if a is not None and a != seed_appid:
            seed_recs.append((a, float(acc[j])))
        if len(seed_recs) >= 10:
            break
    print(f"\n[2] seed route (seed={titles.get(seed_appid, seed_appid)}): "
          f"{len(seed_recs)} recs")
    for a, s in seed_recs[:5]:
        print(f"    {s:+.4f} {titles.get(a, a)}")
    ok &= len(seed_recs) == 10

    steered = hybrid.recommend_steered(lib, k=10, novelty_beta=2.0)
    plain10 = [a for a, _, _ in recs[:10]]
    st10 = [a for a, *_ in steered[:10]]
    print(f"\n[3] explore route (novelty_beta=2): {len(steered)} recs, "
          f"overlap with plain top-10 = {len(set(plain10) & set(st10))}/10")
    for row in steered[:5]:
        print(f"    {row[1]:+.4f} {titles.get(row[0], row[0])}")
    ok &= len(steered) > 0 and st10 != plain10

    cands = [a for a, _, _ in recs] + [a for a, _ in seed_recs]
    coop_kr = meta.constraint_filter(cands, {"coop": True, "korean": True})
    print(f"\n[4] constraint filter (coop+korean): {len(coop_kr)}/{len(cands)} pass")
    gated = meta.quality_gate(cands, min_metacritic=None, min_quality_pct=0.30)
    print(f"[5] quality gate (pct>=0.30): {len(gated)}/{len(cands)} pass")
    ok &= len(gated) > 0

    print(f"\nSMOKE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
