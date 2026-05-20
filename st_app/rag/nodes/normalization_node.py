
import json
import os
from typing import List, Dict, Any

def jaccard_similarity(s1: str, s2: str) -> float:
    """Calculates Jaccard similarity between two strings based on character bigrams."""
    s1_lower = s1.lower()
    s2_lower = s2.lower()
    
    s1_bigrams = set([s1_lower[i:i+2] for i in range(len(s1_lower) - 1)])
    s2_bigrams = set([s2_lower[i:i+2] for i in range(len(s2_lower) - 1)])
    
    if not s1_bigrams and not s2_bigrams:
        return 1.0 if s1_lower == s2_lower else 0.0
    if not s1_bigrams or not s2_bigrams:
        return 0.0
    
    intersection = len(s1_bigrams.intersection(s2_bigrams))
    union = len(s1_bigrams.union(s2_bigrams))
    return intersection / union

def find_best_match(query: str, choices: List[str], threshold: float = 0.3) -> str:
    """Finds the best match for a query string from a list of choices."""
    best_score = -1
    best_match = query  # Default to original query

    for choice in choices:
        score = jaccard_similarity(query, choice)
        
        if score > best_score:
            best_score = score
            best_match = choice
            
    if best_score >= threshold:
        return best_match
    else:
        return query

def game_name_normalizer_node(state: Dict[str, Any], recommender) -> Dict[str, Any]:
    """
    Normalizes game names parsed from user query to their canonical titles
    using fuzzy string matching.
    """
    parsed_json = state.get('parsed_json', {})
    game_names_to_normalize = parsed_json.get('games', [])

    if not game_names_to_normalize:
        return state

    canonical_titles = recommender.games_df['game_title'].tolist()
    
    normalized_games = []
    for game_name in game_names_to_normalize:
        best_match = find_best_match(game_name, canonical_titles)
        normalized_games.append(best_match)
    
    state['parsed_json']['games'] = normalized_games
    
    print(f"Normalized game names: {game_names_to_normalize} -> {normalized_games}")
    
    return state
