"""Four-axis recommendation evaluation: Relevance / Diversity / Novelty / Serendipity.

All functions take recommendation outputs and ground-truth / context
arrays directly — no model dependency. Designed so a benchmark runner
can call them on multiple model outputs without changing the metric code.

Metric definitions:

- **Relevance** (Recall@k, Precision@k, NDCG@k):
  How many ground-truth relevant items appear in the top-k recs, and
  how high they rank. Standard IR metrics.

- **Diversity** (Intra-List Distance @ k):
  Mean pairwise (1 - cosine_similarity) among the top-k recommended
  items' embeddings. High = recs span different parts of the space.

- **Novelty** (Self-Information @ k):
  Mean of -log2(P(item)) where P(item) = popularity[i] / popularity.sum().
  Recommending a niche item scores higher than a blockbuster.

- **Serendipity** (Unexpected-and-Relevant @ k):
  Fraction of recs that are (a) in the ground-truth relevant set AND
  (b) not in the top-N popularity baseline. "Pleasant surprise" proxy.
"""

from __future__ import annotations

import numpy as np


# ----- Relevance --------------------------------------------------------------

def recall_at_k(true_set: set, pred_list: list, k: int) -> float:
    """|true ∩ pred[:k]| / |true|, or 0.0 if true_set is empty."""
    if not true_set:
        return 0.0
    hits = sum(1 for x in pred_list[:k] if x in true_set)
    return hits / len(true_set)


def precision_at_k(true_set: set, pred_list: list, k: int) -> float:
    """|true ∩ pred[:k]| / k."""
    if k <= 0:
        return 0.0
    hits = sum(1 for x in pred_list[:k] if x in true_set)
    return hits / k


def ndcg_at_k(true_set: set, pred_list: list, k: int) -> float:
    """Binary-relevance NDCG@k. Items in true_set get gain 1, others 0.

    DCG = Σ_{i<k} rel_i / log2(i+2). IDCG = max possible (all hits at top).
    """
    if not true_set:
        return 0.0
    gains = np.array([1.0 if x in true_set else 0.0 for x in pred_list[:k]])
    discounts = 1.0 / np.log2(np.arange(2, len(gains) + 2))
    dcg = float((gains * discounts).sum())
    # Ideal: as many hits as min(|true|, k), all at top
    n_ideal = min(len(true_set), k)
    ideal_gains = np.ones(n_ideal)
    ideal_discounts = 1.0 / np.log2(np.arange(2, n_ideal + 2))
    idcg = float((ideal_gains * ideal_discounts).sum())
    return dcg / idcg if idcg > 0 else 0.0


# ----- Diversity --------------------------------------------------------------

def intra_list_diversity(rec_indices: list[int], item_embeddings: np.ndarray) -> float:
    """Mean pairwise (1 - cosine) among the rec items' embeddings.

    Embeddings are assumed unit-normalized; if not, cosine is computed
    explicitly. Returns 0 if the list has < 2 items (no pairs).
    """
    if len(rec_indices) < 2:
        return 0.0
    V = item_embeddings[rec_indices].astype(np.float64)
    norms = np.linalg.norm(V, axis=1, keepdims=True)
    Vn = np.divide(V, norms, out=np.zeros_like(V), where=norms > 0)
    sim = Vn @ Vn.T
    # Take upper triangle (i<j) to count each pair once
    n = len(rec_indices)
    iu = np.triu_indices(n, k=1)
    pairwise_distance = 1.0 - sim[iu]
    return float(pairwise_distance.mean())


# ----- Novelty ----------------------------------------------------------------

def novelty(rec_indices: list[int], popularity: np.ndarray, base: float = 2.0) -> float:
    """Mean Self-Information: average of -log_base(P(item)).

    P(item) = popularity[i] / popularity.sum(). Higher = more niche /
    less-seen items on average.
    """
    if not rec_indices:
        return 0.0
    total = float(popularity.sum())
    if total <= 0:
        return 0.0
    probs = np.maximum(popularity[rec_indices] / total, 1e-12)
    info = -np.log(probs) / np.log(base)
    return float(info.mean())


# ----- Serendipity ------------------------------------------------------------

def serendipity(
    rec_indices: list[int],
    true_set: set,
    popularity_baseline_top: set,
) -> float:
    """Fraction of recs that are (relevant) AND (not in popularity baseline).

    `popularity_baseline_top` is the set of indices a naive popularity
    recommender would return at the same k. A "serendipitous" hit is
    one we got right AND that the trivial baseline would have missed.
    """
    if not rec_indices:
        return 0.0
    serend_hits = sum(
        1 for x in rec_indices
        if (x in true_set) and (x not in popularity_baseline_top)
    )
    return serend_hits / len(rec_indices)


# ----- Aggregator -------------------------------------------------------------

def evaluate_recommendation(
    rec_indices: list[int],
    true_set: set,
    item_embeddings: np.ndarray,
    popularity: np.ndarray,
    popularity_baseline_top: set,
    k: int = 10,
) -> dict[str, float]:
    """Run all four axes at @k. Returns dict of metric name -> float."""
    return {
        "recall@k": recall_at_k(true_set, rec_indices, k),
        "precision@k": precision_at_k(true_set, rec_indices, k),
        "ndcg@k": ndcg_at_k(true_set, rec_indices, k),
        "diversity@k": intra_list_diversity(rec_indices[:k], item_embeddings),
        "novelty@k": novelty(rec_indices[:k], popularity),
        "serendipity@k": serendipity(rec_indices[:k], true_set, popularity_baseline_top),
    }
