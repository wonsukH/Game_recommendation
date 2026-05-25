
import copy
import os
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import faiss
from sklearn.metrics.pairwise import cosine_similarity
from langchain_google_genai import GoogleGenerativeAIEmbeddings


# Matches " II", " III", " 2", " 3", ": Anything..." — series markers we
# slice off to recover the franchise prefix ("DARK SOULS II" -> "dark souls").
_SERIES_SUFFIX_RE = re.compile(r"\s+(?:[ivx]+|\d+)(?:\s|:|$)|\s*:\s*")


def _series_prefix(title: str) -> str:
    """Extract the franchise prefix from a game title.

    Examples:
        'DARK SOULS II'                            -> 'dark souls'
        'DARK SOULS: REMASTERED'                   -> 'dark souls'
        'DARK SOULS III'                           -> 'dark souls'
        'The Witcher 3: Wild Hunt'                 -> 'the witcher'
        'Hollow Knight'                            -> 'hollow knight'  (no marker)
    """
    t = str(title).lower().strip()
    parts = _SERIES_SUFFIX_RE.split(t, maxsplit=1)
    return parts[0].strip() if parts else t

from pipeline.game_rec.io import load_tag_vocab, load_vectors
from pipeline.game_rec.log import get_logger
from pipeline.game_rec.agent.scoring import minmax as _minmax, sigmoid_modifier as _sigmoid_mod

log = get_logger("game_rec.agent.retriever")


def _safe_read_index(path: Path):
    """faiss.read_index that survives non-ASCII paths on Windows."""
    p = str(path)
    try:
        p.encode("ascii")
        return faiss.read_index(p)
    except UnicodeEncodeError:
        pass
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "faiss_index.faiss"
        shutil.copy2(path, tmp_path)
        return faiss.read_index(str(tmp_path))


class VectorBasedRecommender:
    def __init__(self, data_path, embedding_model="models/gemini-embedding-2"):
        api_key = os.environ.get("GEMINI_API_KEY")
        self.embeddings = GoogleGenerativeAIEmbeddings(model=embedding_model, google_api_key=api_key)
        self.data_path = data_path
        self._load_data()

    def _load_data(self):
        """데이터 아티팩트를 로드하고, 조회용 매핑을 생성합니다."""
        try:
            self.faiss_index = _safe_read_index(Path(self.data_path) / "faiss_index.faiss")
            self.games_df = pd.read_csv(f"{self.data_path}/steam_games_tags.csv").set_index('appid')
            self.game_vecs = load_vectors(f"{self.data_path}/game_vecs.npy")
            self.tag_vecs = load_vectors(f"{self.data_path}/tag_vecs.npy")
            self.W_align = load_vectors(f"{self.data_path}/W_align.npy")

            # Popularity for Novelty/Serendipity (optional — falls back to uniform)
            pop_path = Path(self.data_path) / "game_popularity.npy"
            if pop_path.exists():
                self.popularity = np.load(pop_path).astype(np.float64)
            else:
                log.info("game_popularity.npy missing — using uniform popularity for rerank")
                self.popularity = np.ones(len(self.game_vecs), dtype=np.float64)

            tag_list = load_tag_vocab(f"{self.data_path}/tag_vocab.json")

            self.tag_to_idx = {tag: i for i, tag in enumerate(tag_list)}
            self.idx_to_tag = {i: tag for i, tag in enumerate(tag_list)}
            self.appid_to_idx = {appid: i for i, appid in enumerate(self.games_df.index)}
            self.idx_to_appid = {i: appid for i, appid in enumerate(self.games_df.index)}

        except FileNotFoundError as e:
            log.warning("Could not find data file %s. Some features may not work.", e)
            self.faiss_index = None
            self.popularity = None

    def _resolve_tag(self, name: str) -> str | None:
        """Map parser-emitted tag name to actual vocab entry.

        Handles hyphen variants (e.g. parser outputs `rogue-like` but vocab
        has `roguelike`). Returns the canonical vocab name, or None if no
        match. This makes the parser robust to small format drift.
        """
        if name in self.tag_to_idx:
            return name
        target = name.replace('-', '').replace('_', '').lower()
        # Build cache on first call
        if not hasattr(self, '_tag_alias_cache'):
            self._tag_alias_cache = {
                t.replace('-', '').replace('_', '').lower(): t
                for t in self.tag_to_idx
            }
        return self._tag_alias_cache.get(target)

    def expand_query_tags(self, parsed_json, top_k=5, lock_ratio: float = 2.0):
        """Expand query with semantically near tags.

        - phrase vectors (via W_align): weight 1.0 each (non-lock)
        - non-locked target_tags: parser-given weight (default 1.0)
        - locked target_tags: dynamic weight = max(non_lock_sum * lock_ratio, default)
          → lock이 항상 비-lock 신호의 lock_ratio배 우세 보장 (비율 일정)
        Each vector L2-normalized before weighted sum.
        """
        if self.tag_vecs is None: return parsed_json
        existing_tags = {t.get('name') for t in parsed_json.get('target_tags', [])}

        # Collect non-lock contributions first (phrase + non-locked target_tags)
        non_lock_vecs = []  # list of (unit_vec, weight)
        if self.W_align is not None and parsed_json.get('phrases'):
            try:
                text_embeddings = self.embeddings.embed_documents(parsed_json['phrases'])
                for emb in text_embeddings:
                    projected_vec = np.dot(np.array(emb).astype('float32'), self.W_align)
                    n = np.linalg.norm(projected_vec)
                    if n > 0 and np.all(np.isfinite(projected_vec)):
                        non_lock_vecs.append((projected_vec / n, 1.0))
            except Exception as e:
                log.exception("phrase embedding or projection failed: %s", e)

        lock_units = []  # list of unit_vec for locked tags
        # Assumes normalizer node已 canonicalized tag names.
        # _resolve_tag remains as belt-and-suspenders for direct callers
        # (e.g. eval scripts that bypass the graph).
        for tag_info in parsed_json.get('target_tags', []):
            name = self._resolve_tag(tag_info.get('name', ''))
            if not name:
                continue
            tag_vec = self.tag_vecs[self.tag_to_idx[name]]
            n = np.linalg.norm(tag_vec)
            if n <= 0 or not np.all(np.isfinite(tag_vec)):
                continue
            unit = tag_vec / n
            if bool(tag_info.get('locked')):
                lock_units.append(unit)
            else:
                w = float(tag_info.get('weight', 1.0))
                if np.isfinite(w) and w > 0:
                    non_lock_vecs.append((unit, w))

        if not non_lock_vecs and not lock_units:
            return parsed_json

        # Dynamic lock weight: 항상 비-lock 합의 lock_ratio배 (최소값 보장)
        non_lock_sum = sum(w for _, w in non_lock_vecs)
        per_lock_weight = max(non_lock_sum * lock_ratio, 2.0) if lock_units else 0.0

        weighted_vecs = list(non_lock_vecs) + [(u, per_lock_weight) for u in lock_units]
        combined = np.sum([v * w for v, w in weighted_vecs], axis=0)
        final_query_vector = combined.reshape(1, -1)
        similarities = cosine_similarity(final_query_vector, self.tag_vecs)
        sorted_indices = np.argsort(similarities[0])[::-1]
        
        expanded_tags = {}
        for idx in sorted_indices:
            if len(expanded_tags) >= top_k: break
            tag_name = self.idx_to_tag.get(idx)
            if tag_name and tag_name not in existing_tags:
                expanded_tags[tag_name] = similarities[0][idx]

        expanded_json = copy.deepcopy(parsed_json)
        if 'target_tags' not in expanded_json: expanded_json['target_tags'] = []
        for tag, weight in expanded_tags.items():
            expanded_json['target_tags'].append({"name": tag, "weight": round(float(weight), 4)})
            
        return expanded_json

    def _create_query_vector(self, parsed_json, lock_ratio: float = 2.0):
        """Build a query vector as a weighted sum of L2-normalized tag vectors.

        - non-locked target_tags: parser-given weight (default 1.0)
        - locked target_tags: dynamic weight = max(non_lock_sum * lock_ratio, 2.0)
          → 명시 lock이 다른 태그 합의 lock_ratio배 우세 (비율 일정)
        """
        if self.tag_vecs is None: return np.zeros(1)
        final_vector = np.zeros(self.tag_vecs.shape[1], dtype=np.float32)

        tag_infos = parsed_json.get('target_tags', [])
        if not tag_infos:
            return final_vector

        # Separate locked vs non-locked + collect units
        non_lock_items = []   # (unit, weight)
        lock_units = []       # unit
        for ti in tag_infos:
            name = self._resolve_tag(ti.get('name', ''))  # hyphen alias 매핑
            if not name:
                continue
            tv = self.tag_vecs[self.tag_to_idx[name]]
            if not np.all(np.isfinite(tv)):
                continue
            n = float(np.linalg.norm(tv))
            if n <= 0:
                continue
            unit = tv / n
            if bool(ti.get('locked')):
                lock_units.append(unit)
            else:
                w = float(ti.get('weight', 1.0))
                if not np.isfinite(w) or w <= 0:
                    continue
                non_lock_items.append((unit, w))

        # Dynamic lock weight = max(non_lock_sum * lock_ratio, floor)
        non_lock_sum = sum(w for _, w in non_lock_items)
        per_lock_weight = max(non_lock_sum * lock_ratio, 2.0) if lock_units else 0.0

        for unit, w in non_lock_items:
            final_vector += unit * w
        for unit in lock_units:
            final_vector += unit * per_lock_weight

        for tag_name in parsed_json.get('avoid_tags', []):
            if tag_name in self.tag_to_idx:
                av = self.tag_vecs[self.tag_to_idx[tag_name]]
                an = float(np.linalg.norm(av))
                if an > 0:
                    final_vector -= av / an

        if not np.all(np.isfinite(final_vector)):
            log.error("final query vector contains NaN/Inf values. resetting to zero vector.")
            return np.zeros(self.tag_vecs.shape[1], dtype=np.float32)

        return final_vector

    def recommend_similar(self, parsed_json, top_k=200):
        if not self.faiss_index: return {"error": "Recommender not initialized"}
        seed_game_titles = parsed_json.get('games', [])
        if not seed_game_titles: return {"error": "No seed games"}
        seed_vectors, seed_appids = [], set()
        canonical_titles: list[str] = []
        for title in seed_game_titles:
            game_row = self.games_df[self.games_df['game_title'].str.lower() == title.lower()]
            if not game_row.empty:
                appid = game_row.index[0]
                seed_appids.add(appid)
                seed_vectors.append(self.game_vecs[self.appid_to_idx[appid]])
                canonical_titles.append(str(game_row.iloc[0]['game_title']))
        if not seed_vectors: return {"error": f"Seed games not found: {seed_game_titles}"}
        query_vector = np.mean(seed_vectors, axis=0).reshape(1, -1)

        # L2 정규화 추가
        norm = np.linalg.norm(query_vector)
        if norm > 0:
            query_vector = query_vector / norm

        # Expand exclusion to the whole franchise. Without this, when the
        # user asks for "Dark Souls 시리즈 말고", only the seed (e.g. DS II)
        # is dropped and other entries (DS III, Remastered, Scholar, etc.)
        # crowd the top-5, leaving the LLM to filter them out post-hoc and
        # often returning <5 games. Filtering at the candidate stage lets
        # the recommender surface real *non-franchise* alternatives.
        excluded = set(seed_appids)
        prefixes = {p for p in (_series_prefix(t) for t in canonical_titles) if len(p) >= 4}
        if prefixes:
            title_lower = self.games_df['game_title'].astype(str).str.lower()
            mask = pd.Series(False, index=self.games_df.index)
            for p in prefixes:
                mask |= title_lower.str.contains(p, na=False, regex=False)
            franchise_appids = set(self.games_df.index[mask].tolist())
            log.info("franchise filter: prefixes=%s -> %d titles excluded",
                     prefixes, len(franchise_appids))
            excluded |= franchise_appids

        # Search with extra headroom since we're filtering out more.
        distances, indices = self.faiss_index.search(
            query_vector, top_k + len(excluded)
        )
        candidate_appids = [
            self.idx_to_appid[i] for i in indices[0]
            if self.idx_to_appid[i] not in excluded
        ]
        return {"candidates": candidate_appids[:top_k], "query_vector": query_vector}

    def recommend_vibe(self, parsed_json, top_k=200):
        log.debug("vibe node start — initial parsed_json keys: %s", list(parsed_json.keys()))

        if not self.faiss_index:
            log.error("recommender not initialized (no faiss index)")
            return {"error": "Recommender not initialized"}

        # Use deepcopy to avoid side effects
        expanded_json = copy.deepcopy(parsed_json)
        expanded_json = self.expand_query_tags(expanded_json)
        log.debug("vibe expanded tags: %d", len(expanded_json.get('target_tags', [])))

        query_vector = self._create_query_vector(expanded_json).reshape(1, -1)
        if np.all(query_vector == 0):
            log.error("vibe query vector is a zero vector — no valid tags")
            return {"error": "No valid tags"}

        norm = np.linalg.norm(query_vector)
        if norm > 0:
            query_vector = query_vector / norm

        distances, indices = self.faiss_index.search(query_vector, top_k)
        candidate_appids = [self.idx_to_appid[i] for i in indices[0]] if len(indices[0]) > 0 else []
        log.info("vibe search — found %d candidates (top_k=%d)", len(candidate_appids), top_k)

        return {"candidates": candidate_appids, "query_vector": query_vector}

    def recommend_hybrid(self, parsed_json, top_k=200):
        """Hybrid retrieval.

        Stage 1: seed 게임 벡터로 FAISS coarse search (`recommend_similar`과
        동일한 시리즈 자동 제외 적용) -> Isaac 근처 후보 200개.
        Stage 2 (rerank): 후보에 대해 rel = min(cos_seed, cos_vibe).
        둘 다 가까운 게임이 top — vibe direction은 reranker로 전달되는
        `vibe_vector`를 통해 반영.

        가중 합(seed + vibe) 방식의 옛 hybrid는 vibe vector magnitude가
        커지면 narrative-adventure 같은 다른 cluster로 끌려가는 문제가
        있었음. 본 방식은 retrieval pool을 seed 정체성으로 한정하고
        그 안에서만 vibe direction으로 정렬해 의도 일치도 ↑.
        """
        if not self.faiss_index: return {"error": "Recommender not initialized"}
        seed_titles = parsed_json.get('games', [])
        if not seed_titles: return {"error": "No seed games"}

        seed_vectors, seed_appids, canonical_titles = [], set(), []
        for title in seed_titles:
            row = self.games_df[self.games_df['game_title'].str.lower() == str(title).lower()]
            if not row.empty:
                appid = row.index[0]
                seed_appids.add(appid)
                seed_vectors.append(self.game_vecs[self.appid_to_idx[appid]])
                canonical_titles.append(str(row.iloc[0]['game_title']))
        if not seed_vectors:
            return {"error": f"Seed games not found: {seed_titles}"}

        # Stage 1: seed로 FAISS coarse retrieval (similar과 동일 패턴)
        query_vector = np.mean(seed_vectors, axis=0).reshape(1, -1)
        qn = float(np.linalg.norm(query_vector))
        if qn > 0:
            query_vector = query_vector / qn

        excluded = set(seed_appids)
        prefixes = {p for p in (_series_prefix(t) for t in canonical_titles) if len(p) >= 4}
        if prefixes:
            title_lower = self.games_df['game_title'].astype(str).str.lower()
            mask = pd.Series(False, index=self.games_df.index)
            for p in prefixes:
                mask |= title_lower.str.contains(p, na=False, regex=False)
            excluded |= set(self.games_df.index[mask].tolist())
            log.info("hybrid franchise filter: prefixes=%s -> %d titles excluded",
                     prefixes, len(excluded) - len(seed_appids))

        distances, indices = self.faiss_index.search(
            query_vector, top_k + len(excluded)
        )
        candidate_appids = [
            self.idx_to_appid[i] for i in indices[0]
            if self.idx_to_appid[i] not in excluded
        ][:top_k]

        # vibe direction: rerank에서 rel = min(cos_seed, cos_vibe)에 사용
        expanded_json = copy.deepcopy(parsed_json)
        expanded_json = self.expand_query_tags(expanded_json)
        vibe_vector = self._create_query_vector(expanded_json).reshape(1, -1)
        vn = float(np.linalg.norm(vibe_vector))
        if vn > 0:
            vibe_vector = vibe_vector / vn

        log.info("hybrid retrieval: %d candidates (seed pool, franchise excluded)", len(candidate_appids))
        return {
            "candidates": candidate_appids,
            "query_vector": query_vector,
            "vibe_vector": vibe_vector,
        }

    def rerank_candidates(self, candidate_appids, query_vector, weights, top_n=10, *, vibe_vector=None):
        """Rerank candidate games with a signed-modifier scheme.

        weights: dict with keys among {relevance, diversity, novelty,
        tag_match}. `tag_match` is a back-compat alias for `relevance`.
        Each slider is 0..10.

        Semantics:
          - relevance: positive-only importance. 0 = ignore cosine, 10 = max weight.
          - novelty / diversity: SIGNED via sigmoid modifier.
            Slider 5 = neutral (no effect). >5 = push that signal up
            (more niche / more diverse). <5 = push the opposite
            (popular / clustered).

        Note (M9 follow-up): Serendipity slider was removed — it was
        redundant with Novelty (both popularity-based, with rel * (1-pct)
        just being a multiplicative variant). User control via Relevance
        + Novelty already covers the "niche but relevant" case naturally.
        Serendipity@K metric is kept in evaluation/metrics.py.

        Returns top-N rows of self.games_df augmented with per-signal scores.
        """
        if not candidate_appids:
            return pd.DataFrame()

        # Back-compat: old UI used "tag_match" instead of "relevance"
        w_rel = float(weights.get("relevance", weights.get("tag_match", 5)))
        w_div = float(weights.get("diversity", 5))
        w_nov = float(weights.get("novelty", 5))

        cand_rows = [self.appid_to_idx[a] for a in candidate_appids if a in self.appid_to_idx]
        cand_appids = [self.idx_to_appid[r] for r in cand_rows]
        if not cand_rows:
            return pd.DataFrame()

        V = self.game_vecs[cand_rows].astype(np.float32)
        qv = np.asarray(query_vector).reshape(-1).astype(np.float32)
        qn = float(np.linalg.norm(qv))
        if qn > 0:
            qv = qv / qn

        # Raw per-signal scores in [0, 1].
        # Hybrid 모드는 vibe_vector가 함께 들어옴 — relevance를
        # min(cos_seed, cos_vibe)으로 정의해 "둘 다 가까운" 후보가 top.
        cos_seed = V @ qv
        if vibe_vector is not None:
            vv = np.asarray(vibe_vector).reshape(-1).astype(np.float32)
            vn = float(np.linalg.norm(vv))
            if vn > 0:
                vv = vv / vn
            cos_vibe = V @ vv
            rel_raw = np.minimum(cos_seed, cos_vibe)
        else:
            rel_raw = cos_seed
        rel = _minmax(rel_raw)

        if self.popularity is not None:
            pop = self.popularity[cand_rows]
            probs = np.maximum(pop / max(pop.sum(), 1e-12), 1e-12)
            nov_raw = -np.log2(probs)
        else:
            nov_raw = np.full(len(cand_rows), 0.5, dtype=np.float32)
        nov = _minmax(nov_raw)

        # Center novelty to [-1, +1]: niche = +1, popular = -1
        nov_centered = (2.0 * nov - 1.0).astype(np.float32)

        # Slider -> signed modifier in (-1, +1). 5 = neutral.
        nov_mod = _sigmoid_mod(w_nov)
        div_mod = _sigmoid_mod(w_div)

        # Relevance keeps positive-only semantics (slider scales how strongly
        # cosine fit matters). Novelty contributes a signed term whose
        # direction depends on whether the slider is above or below 5.
        rel_contrib = (w_rel / 10.0) * rel
        base = rel_contrib + 0.5 * nov_mod * nov_centered

        # Diversity via MMR: only kicks in when div slider is above 5
        # (positive modifier). Below 5 -> no penalty (pure base ordering).
        # The penalty strength is proportional to div_mod, capped at 0.5.
        sim_penalty = max(div_mod, 0.0) * 0.5
        selected: list[int] = []
        remaining = list(range(len(cand_rows)))
        while remaining and len(selected) < top_n:
            if not selected or sim_penalty <= 0:
                pick = max(remaining, key=lambda i: base[i])
            else:
                sel_V = V[selected]
                sim_to_sel = (V[remaining] @ sel_V.T).max(axis=1)
                mmr_score = (1 - sim_penalty) * base[remaining] - sim_penalty * sim_to_sel
                pick = remaining[int(np.argmax(mmr_score))]
            selected.append(pick)
            remaining.remove(pick)

        # Build output DF
        out_appids = [cand_appids[i] for i in selected]
        out = self.games_df.loc[out_appids].copy()
        out["relevance_score"] = rel[selected]
        out["novelty_score"] = nov[selected]
        out["base_score"] = base[selected]
        # Preserve old column name for back-compat with the existing UI
        out["tag_match_score"] = rel[selected]
        out["final_score"] = base[selected]
        return out
