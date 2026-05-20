
import copy
from pathlib import Path

import numpy as np
import pandas as pd
import faiss
from sklearn.metrics.pairwise import cosine_similarity
from langchain_upstage import UpstageEmbeddings

from pipeline.game_rec.io import load_tag_vocab, load_vectors
from pipeline.game_rec.log import get_logger
from pipeline.game_rec.agent.scoring import minmax as _minmax

log = get_logger("game_rec.agent.retriever")


class VectorBasedRecommender:
    def __init__(self, data_path, embedding_model="solar-embedding-1-large"):
        self.embeddings = UpstageEmbeddings(model=embedding_model)
        self.data_path = data_path
        self._load_data()

    def _load_data(self):
        """데이터 아티팩트를 로드하고, 조회용 매핑을 생성합니다."""
        try:
            self.faiss_index = faiss.read_index(f"{self.data_path}/faiss_index.faiss")
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
        for title in seed_game_titles:
            game_row = self.games_df[self.games_df['game_title'].str.lower() == title.lower()]
            if not game_row.empty:
                appid = game_row.index[0]
                seed_appids.add(appid)
                seed_vectors.append(self.game_vecs[self.appid_to_idx[appid]])
        if not seed_vectors: return {"error": f"Seed games not found: {seed_game_titles}"}
        query_vector = np.mean(seed_vectors, axis=0).reshape(1, -1)

        # L2 정규화 추가
        norm = np.linalg.norm(query_vector)
        if norm > 0:
            query_vector = query_vector / norm

        distances, indices = self.faiss_index.search(query_vector, top_k + len(seed_appids))
        candidate_appids = [self.idx_to_appid[i] for i in indices[0] if self.idx_to_appid[i] not in seed_appids]
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
        """Rerank candidate games with a weighted MMR over 4 signals.

        weights: dict with keys among {relevance, diversity, novelty,
        serendipity, tag_match}. `tag_match` is treated as a synonym
        for `relevance` for backward compatibility with the older UI.
        Values 0..10. Re-normalized internally.

        Returns top-N rows of self.games_df augmented with per-signal
        scores and the final composite score.
        """
        if not candidate_appids:
            return pd.DataFrame()

        # Back-compat: old UI used "tag_match" instead of "relevance"
        w_rel = float(weights.get("relevance", weights.get("tag_match", 5)))
        w_div = float(weights.get("diversity", 5))
        w_nov = float(weights.get("novelty", 2))
        w_ser = float(weights.get("serendipity", 1))
        mmr_lambda = float(weights.get("mmr_lambda", 0.5))

        cand_rows = [self.appid_to_idx[a] for a in candidate_appids if a in self.appid_to_idx]
        cand_appids = [self.idx_to_appid[r] for r in cand_rows]
        if not cand_rows:
            return pd.DataFrame()

        V = self.game_vecs[cand_rows].astype(np.float32)
        qv = np.asarray(query_vector).reshape(-1).astype(np.float32)
        qn = float(np.linalg.norm(qv))
        if qn > 0:
            qv = qv / qn

        # Relevance: cosine to query
        rel_raw = V @ qv
        rel = _minmax(rel_raw)

        # Novelty: -log2(P(item)) over the *candidate pool*'s popularities
        if self.popularity is not None:
            pop = self.popularity[cand_rows]
            probs = np.maximum(pop / max(pop.sum(), 1e-12), 1e-12)
            nov_raw = -np.log2(probs)
        else:
            nov_raw = np.full(len(cand_rows), 0.5)
        nov = _minmax(nov_raw)

        # Serendipity proxy: relevant AND non-popular
        if self.popularity is not None:
            pop = self.popularity[cand_rows]
            pct = np.argsort(np.argsort(pop)) / max(len(pop) - 1, 1)
            ser_raw = rel * (1.0 - pct)
        else:
            ser_raw = np.zeros(len(cand_rows))
        ser = _minmax(ser_raw)

        # Composite "base" score (no diversity yet — diversity enters via MMR)
        total_w = max(w_rel + w_nov + w_ser, 1e-9)
        base = (w_rel * rel + w_nov * nov + w_ser * ser) / total_w

        # MMR selection: pick top_n greedily balancing base vs novelty-of-pick
        # diversity weight modulates the (1 - lambda) penalty
        div_weight = w_div / max(w_rel + w_div + w_nov + w_ser, 1e-9)
        selected: list[int] = []
        remaining = list(range(len(cand_rows)))
        while remaining and len(selected) < top_n:
            if not selected:
                pick = max(remaining, key=lambda i: base[i])
            else:
                sel_V = V[selected]
                sim_to_sel = (V[remaining] @ sel_V.T).max(axis=1)
                mmr_score = mmr_lambda * base[remaining] - (1 - mmr_lambda) * div_weight * sim_to_sel
                pick = remaining[int(np.argmax(mmr_score))]
            selected.append(pick)
            remaining.remove(pick)

        # Build output DF
        out_appids = [cand_appids[i] for i in selected]
        out = self.games_df.loc[out_appids].copy()
        out["relevance_score"] = rel[selected]
        out["novelty_score"] = nov[selected]
        out["serendipity_score"] = ser[selected]
        out["base_score"] = base[selected]
        # Preserve old column name for back-compat with the existing UI
        out["tag_match_score"] = rel[selected]
        out["final_score"] = base[selected]
        return out
