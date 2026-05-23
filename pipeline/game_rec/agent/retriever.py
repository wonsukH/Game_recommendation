
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

    def expand_query_tags(self, parsed_json, top_k=5):
        if self.tag_vecs is None: return parsed_json
        query_vectors = []
        existing_tags = {t.get('name') for t in parsed_json.get('target_tags', [])}

        if self.W_align is not None and parsed_json.get('phrases'):
            try:
                text_embeddings = self.embeddings.embed_documents(parsed_json['phrases'])
                for emb in text_embeddings:
                    projected_vec = np.dot(np.array(emb).astype('float32'), self.W_align)
                    query_vectors.append(projected_vec)
            except Exception as e:
                log.exception("phrase embedding or projection failed: %s", e)

        for tag_info in parsed_json.get('target_tags', []):
            tag_name = tag_info.get('name')
            if tag_name in self.tag_to_idx:
                query_vectors.append(self.tag_vecs[self.tag_to_idx[tag_name]])

        if not query_vectors: return parsed_json

        final_query_vector = np.mean(query_vectors, axis=0).reshape(1, -1)
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

    def _create_query_vector(self, parsed_json):
        if self.tag_vecs is None: return np.zeros(1)
        final_vector = np.zeros(self.tag_vecs.shape[1], dtype=np.float32)
        
        tag_infos = parsed_json.get('target_tags', [])
        if not tag_infos:
            return final_vector

        for tag_info in tag_infos:
            tag_name = tag_info.get('name')
            if tag_name in self.tag_to_idx:
                weight = tag_info.get('weight', 1.0)
                # NaN/Inf check for weight
                if not np.isfinite(weight):
                    log.warning("invalid weight '%s' for tag '%s'. skipping.", weight, tag_name)
                    continue

                tag_vector = self.tag_vecs[self.tag_to_idx[tag_name]]

                # NaN/Inf check for tag vector
                if not np.all(np.isfinite(tag_vector)):
                    log.warning("invalid vector for tag '%s'. skipping.", tag_name)
                    continue

                final_vector += tag_vector * weight

        for tag_name in parsed_json.get('avoid_tags', []):
            if tag_name in self.tag_to_idx:
                final_vector -= self.tag_vecs[self.tag_to_idx[tag_name]]
        
        # Final check on the resulting vector
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
        if not self.faiss_index: return {"error": "Recommender not initialized"}
        game_title = parsed_json.get('games', [])[0]
        game_row = self.games_df[self.games_df['game_title'].str.lower() == game_title.lower()]
        if game_row.empty: return {"error": f"Game '{game_title}' not found."}
        game_appid = game_row.index[0]
        base_game_vector = self.game_vecs[self.appid_to_idx[game_appid]]

        # Apply expansion logic to the vibe component
        expanded_json = copy.deepcopy(parsed_json)
        expanded_json = self.expand_query_tags(expanded_json)
        vibe_vector = self._create_query_vector(expanded_json)
        
        weights = parsed_json.get('weights', {"similar_weight": 0.5, "vibe_weight": 0.5})
        query_vector = (weights['similar_weight'] * base_game_vector + weights['vibe_weight'] * vibe_vector).reshape(1, -1)

        # L2 정규화 추가
        norm = np.linalg.norm(query_vector)
        if norm > 0:
            query_vector = query_vector / norm

        distances, indices = self.faiss_index.search(query_vector, top_k + 1)
        candidate_appids = [self.idx_to_appid[i] for i in indices[0] if self.idx_to_appid[i] != game_appid]
        return {"candidates": candidate_appids[:top_k], "query_vector": query_vector}

    def rerank_candidates(self, candidate_appids, query_vector, weights, top_n=10):
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

        # Raw per-signal scores in [0, 1]
        rel_raw = V @ qv
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
