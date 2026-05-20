
import copy
from pathlib import Path

import numpy as np
import pandas as pd
import faiss
from sklearn.metrics.pairwise import cosine_similarity
from langchain_upstage import UpstageEmbeddings

from game_rec.io import load_tag_vocab, load_vectors
from game_rec.log import get_logger

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

            tag_list = load_tag_vocab(f"{self.data_path}/tag_vocab.json")

            self.tag_to_idx = {tag: i for i, tag in enumerate(tag_list)}
            self.idx_to_tag = {i: tag for i, tag in enumerate(tag_list)}
            self.appid_to_idx = {appid: i for i, appid in enumerate(self.games_df.index)}
            self.idx_to_appid = {i: appid for i, appid in enumerate(self.games_df.index)}

        except FileNotFoundError as e:
            log.warning("Could not find data file %s. Some features may not work.", e)
            self.faiss_index = None

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
        if not candidate_appids: return pd.DataFrame()
        total_weight = weights.get('tag_match', 0) + weights.get('novelty', 0)
        if total_weight == 0: total_weight = 1
        alpha = weights.get('tag_match', 0) / total_weight
        beta = weights.get('novelty', 0) / total_weight
        candidates_df = self.games_df.loc[candidate_appids].copy()
        candidate_indices = [self.appid_to_idx[appid] for appid in candidate_appids]
        candidate_vectors = self.game_vecs[candidate_indices]
        tag_match_scores = cosine_similarity(query_vector, candidate_vectors)[0]
        candidates_df['tag_match_score'] = np.clip(tag_match_scores, 0, 1)
        candidates_df['novelty_score'] = 0.5
        candidates_df['final_score'] = (alpha * candidates_df['tag_match_score'] + beta * candidates_df['novelty_score'])
        return candidates_df.sort_values(by='final_score', ascending=False).head(top_n)
