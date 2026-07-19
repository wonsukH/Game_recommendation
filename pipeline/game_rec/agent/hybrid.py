"""Hybrid recommender — the CF moat as the base, with a content (tag-cosine) layer
for cold-start fallback (D1) and directional steering (the new feature, F).

Design (data-backed):
  - CF (playtime-weighted item-item co-occurrence) is the moat: it beats "give the
    LLM your library" on behavioral hold-out (experiments/05_personalization). It
    is ALWAYS the base ranking — content never reorders CF's warm picks.
  - CF covers only 8,450/9,956 games and underfills for thin/cold libraries. The
    content layer (validated Vb tag-cosine, 100% pool coverage) fills the gap:
      * cold fallback: when CF returns < k, append content-ranked games that CF
        can't reach, QUALITY-GATED (niche != good — P2e), so warm recall is
        unchanged by construction (cold only fills below CF).
      * steering: rerank CF candidates toward unexplored genres (adjacent novelty)
        or a liked aspect (tag set) — the new directional feature.

Returns (appid, score, source) tuples; source ∈ {"cf","cold","steer"} so the UI/
explanation can be honest about why each pick is there.
"""

from __future__ import annotations

import numpy as np

from pipeline.game_rec.agent.cf_recommender import CFRecommender
from pipeline.game_rec.agent.content import ContentLayer
from pipeline.game_rec.log import get_logger

log = get_logger("game_rec.agent.hybrid")


class HybridRecommender:
    def __init__(self, cf: CFRecommender | None = None, content: ContentLayer | None = None, meta=None):
        self.cf = cf or CFRecommender()
        self.content = content or ContentLayer()
        self.meta = meta  # CatalogMeta, optional (for quality-gating cold fill)

    # ---------- warm ranking (ranker-agnostic) ----------
    def _cf_ranked(self, library_pt: dict[int, float], exclude: set[int],
                   cap: int = 2000):
        """Rank the FULL score vector — no score<=0 break. EASE scores are
        legitimately negative in the tail (T33/T35 cutoff bug; T-a ablation
        proved the negative weights carry signal). Cap is cost-only."""
        acc = self.cf.score(library_pt)
        order = np.argsort(-acc)
        warm = []
        for j in order:
            s = acc[int(j)]
            if not np.isfinite(s):
                break
            a = self.cf.inv_col.get(int(j))
            if a is not None and a not in exclude:
                warm.append((a, float(s)))
            if len(warm) >= cap:
                break
        return warm, acc

    # ---------- D1: cold-start fallback ----------
    def recommend(self, library_pt: dict[int, float], k: int = 20,
                  exclude: set[int] | None = None, cold_fallback: bool = True,
                  min_quality_pct: float | None = 0.30):
        """CF-ranked warm picks, then (only on shortfall) content-ranked cold fill."""
        exclude = (exclude or set()) | set(int(a) for a in library_pt)
        warm, _ = self._cf_ranked(library_pt, exclude)
        out = [(a, s, "cf") for a, s in warm[:k]]
        if len(out) >= k or not cold_fallback:
            return out

        warm_set = {a for a, _ in warm}
        cs = self.content.content_scores(library_pt, self.cf.game_avg_pt)
        cold_order = np.argsort(-cs)
        need = (k - len(out))
        cands = []
        for r in cold_order:
            sc = cs[int(r)]
            if sc <= 0:
                break
            a = self.content.row2appid[int(r)]
            if a in warm_set or a in exclude:
                continue
            cands.append((a, float(sc)))
            if len(cands) >= need * 8:  # headroom for the quality gate
                break
        if self.meta is not None and min_quality_pct is not None:
            keep = set(self.meta.quality_gate([a for a, _ in cands],
                                              min_metacritic=None, min_quality_pct=min_quality_pct))
            cands = [(a, s) for a, s in cands if a in keep]
        out += [(a, s, "cold") for a, s in cands[:need]]
        return out

    def coverage(self) -> dict:
        """How many pool games are reachable by CF alone vs +content fallback."""
        cf_col = set(self.cf.col.keys())
        pool = set(self.content.appid2row.keys())
        return {"pool": len(pool), "cf_reachable": len(cf_col & pool),
                "with_content": len(pool), "cold_recovered": len(pool - cf_col)}

    # ---------- F: directional steering (adjacent novelty + aspect) ----------
    def recommend_steered(self, library_pt: dict[int, float], k: int = 20,
                          exclude: set[int] | None = None, *,
                          novelty_beta: float = 0.0, novelty_mode: str = "content",
                          aspect_tags: list[int] | None = None, aspect_alpha: float = 1.0,
                          cand_pool: int = 600, min_quality_pct: float | None = 0.30):
        """Rerank CF-validated candidates toward unexplored genres and/or a liked aspect.

        ADJACENT NOVELTY (user-chosen design): we only reorder games CF already
        scores positively (the moat keeps quality); we do NOT inject random new-genre
        games. novelty_beta>0 pushes toward genres the user hasn't played; aspect_tags
        pushes toward games strong on those tags (e.g. combat/story/atmosphere).

        novelty_mode:
          - "content": novelty = 1 - taste-cosine (genre-DISsimilarity to the library
            tag profile), normalized over candidates. Wide-range, discriminative.
          - "centrality": 1 - avg centrality of a game's tags to the library.
        """
        exclude = (exclude or set()) | set(int(a) for a in library_pt)
        warm, _ = self._cf_ranked(library_pt, exclude)
        if not warm:
            return self.recommend(library_pt, k, exclude, min_quality_pct=min_quality_pct)
        cand = warm[:cand_pool]
        appids = [a for a, _ in cand]
        rows = np.array([self.content.appid2row[a] for a in appids])
        cf_s = np.array([s for _, s in cand], dtype=np.float64)
        # min-max over candidates -> [0,1] (divide-by-max breaks when the base
        # ranker emits negative scores, e.g. EASE's linear tail)
        lo_s, hi_s = cf_s.min(), cf_s.max()
        cf_s = (cf_s - lo_s) / (hi_s - lo_s + 1e-12)

        mult = np.ones(len(cand), dtype=np.float64)
        if novelty_beta > 0:
            if novelty_mode == "content":
                sim = self.content.content_scores(library_pt, self.cf.game_avg_pt)[rows]
                lo, hi = sim.min(), sim.max()
                fam = (sim - lo) / (hi - lo + 1e-12)   # familiarity in [0,1] over candidates
                nv = 1.0 - fam
            else:
                nov = self.content.novelty_scores(library_pt)
                nv = nov[rows]
            mult *= np.power(np.clip(nv, 1e-6, 1.0), novelty_beta)
        if aspect_tags:
            av = self.content.aspect_scores(aspect_tags)[rows]  # [0,1]
            mult *= (1.0 + aspect_alpha * av)

        score = cf_s * mult
        # quality gate (steering surfaces niche -> guard with the dense user-score)
        if self.meta is not None and min_quality_pct is not None:
            keep = set(self.meta.quality_gate(appids, min_metacritic=None, min_quality_pct=min_quality_pct))
            mask = np.array([a in keep for a in appids])
            score = np.where(mask, score, -np.inf)
        order = np.argsort(-score)
        out = [(appids[i], float(score[i]), "steer") for i in order if np.isfinite(score[i])][:k]
        return out


if __name__ == "__main__":
    import json
    from pipeline.game_rec.agent.tools import CatalogMeta
    hr = HybridRecommender(meta=CatalogMeta())
    print("coverage:", hr.coverage())
    # a thin/cold library: pick two CF-cold games so CF underfills -> cold fallback fires
    cf_col = set(hr.cf.col.keys())
    cold = [a for a in hr.content.appid2row if a not in cf_col][:2]
    rec = hr.recommend({cold[0]: 100.0, cold[1]: 100.0}, k=10)
    print(f"cold-library rec -> {len(rec)} results, sources={[s for *_, s in rec]}")
