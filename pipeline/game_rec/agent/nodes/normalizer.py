import re
from typing import List, Dict, Any

from pipeline.game_rec.log import get_logger

log = get_logger("game_rec.agent.normalizer")


# Roman numeral → arabic, applied in length-desc order so "III" is replaced
# before "II". Word-boundary so a token like "Dark Souls II" → "dark souls 2"
# but words like "vivid" are untouched.
_ROMAN_TO_ARABIC = [
    (re.compile(r"\bviii\b"), "8"),
    (re.compile(r"\bvii\b"), "7"),
    (re.compile(r"\bvi\b"), "6"),
    (re.compile(r"\biv\b"), "4"),
    (re.compile(r"\biii\b"), "3"),
    (re.compile(r"\bii\b"), "2"),
    (re.compile(r"\bix\b"), "9"),
    (re.compile(r"\bx\b"), "10"),
]


def _canonical_form(s: str) -> str:
    """Lowercase + collapse roman numerals to arabic for matching.

    Without this, Jaccard-bigram similarity rates 'Dark Souls 3' equally
    close to 'DARK SOULS II' and 'DARK SOULS III' (the 'i' bigrams swamp
    the digit difference), so the wrong installment can win the tie.
    """
    s = s.lower().strip()
    for pat, rep in _ROMAN_TO_ARABIC:
        s = pat.sub(rep, s)
    # Drop punctuation that breaks bigrams without carrying meaning
    s = re.sub(r"[:\-™®©]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def jaccard_similarity(s1: str, s2: str) -> float:
    """Calculates Jaccard similarity between two strings based on character bigrams.

    Strings are first canonicalized (lowercase + roman→arabic) so that
    'Dark Souls 3' and 'DARK SOULS III' compare as identical.
    """
    s1_lower = _canonical_form(s1)
    s2_lower = _canonical_form(s2)

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
    """Normalize parser-emitted entities to canonical forms used inside the system.

    Two responsibilities:
      1. Game names — fuzzy-match parser output to canonical Steam titles
         (e.g. "Dark Souls 3" → "DARK SOULS III"). Roman ↔ Arabic handled.
      2. Tag names — map parser output to vocab entries (e.g. parser emits
         "rogue-like" but vocab has "roguelike"). Without this normalize the
         tag is silently dropped at lookup time and the lock has no effect.

    Centralising both keeps the contract "after this node, all entities are
    canonical" — downstream nodes (router, recommender) can rely on it.
    """
    parsed_json = state.get('parsed_json', {})

    # 1) 게임명 normalize (기존 책임)
    game_names_to_normalize = parsed_json.get('games', [])
    if game_names_to_normalize:
        canonical_titles = recommender.games_df['game_title'].tolist()
        normalized_games = [find_best_match(g, canonical_titles) for g in game_names_to_normalize]
        parsed_json['games'] = normalized_games
        log.info("normalized game names: %s -> %s", game_names_to_normalize, normalized_games)

    # 2) 태그명 normalize (parser ↔ vocab format drift 안전망)
    target_tags = parsed_json.get('target_tags', [])
    if target_tags:
        for tag_info in target_tags:
            original = tag_info.get('name')
            if not original:
                continue
            canonical = recommender._resolve_tag(original)
            if canonical and canonical != original:
                log.info("normalized tag: %s -> %s", original, canonical)
                tag_info['name'] = canonical

    avoid_tags = parsed_json.get('avoid_tags', [])
    if avoid_tags:
        normalized_avoid = []
        for tag_name in avoid_tags:
            canonical = recommender._resolve_tag(tag_name)
            normalized_avoid.append(canonical if canonical else tag_name)
        parsed_json['avoid_tags'] = normalized_avoid

    state['parsed_json'] = parsed_json
    return state
