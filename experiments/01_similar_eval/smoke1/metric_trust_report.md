# Phase 0 — Metric Trust Report

Anchors + 4 real variants over **50 co-play seeds**. Headline k = **50** (recall ceiling reachable since k ≥ avg |relevant|).

## Anchor recall (validation)

| system | recall@10 | recall@20 | recall@50 | ndcg@10 | ndcg@20 | ndcg@50 |
|---|---|---|---|---|---|---|
| random | 0.000 | 0.000 | 0.002 | 0.000 | 0.000 | 0.001 |
| popularity | 0.048 | 0.106 | 0.264 | 0.048 | 0.074 | 0.134 |
| oracle | 0.982 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| oracle_drop5 | 0.223 | 0.223 | 0.223 | 0.335 | 0.325 | 0.325 |
| oracle_drop10 | 0.018 | 0.018 | 0.018 | 0.037 | 0.031 | 0.031 |
| tagset_jaccard | 0.103 | 0.143 | 0.222 | 0.122 | 0.139 | 0.169 |
| Vb_tagcosine | 0.127 | 0.171 | 0.235 | 0.139 | 0.156 | 0.181 |
| Vc_ppmi_svd | 0.083 | 0.132 | 0.200 | 0.100 | 0.121 | 0.146 |
| Vd_ensemble | 0.083 | 0.132 | 0.200 | 0.100 | 0.121 | 0.146 |

## Validation checks

- **Floor/Ceiling**: random=0.002, oracle=1.000 → PASS (oracle must be ≥0.90 and random ≤0.05)
- **Perturbation monotonic**: oracle=1.000 > drop5=0.223 > drop10=0.018 → PASS
- **Discriminative power**: real-variant recall spread=0.035 → PASS (need ≥0.02 to separate systems)
- **Popularity confound**: popularity=0.264 vs random=0.002 (×119.0) → CONFOUNDED

## Verdicts (which metric may drive which decision)

| metric | verdict |
|---|---|
| `recall@50` | USE+DEBIAS (report novelty-calibration alongside) |
| `ndcg@50` | USE+DEBIAS (report novelty-calibration alongside) |
| `overlap@k` | SCREENING ONLY (distinctiveness, not quality) |
| `genre_precision` | DEMOTE→guardrail (circular for tag systems; tag-cosine inflates it by construction) |
| `coplay_recall_for_item2vec` | INVALID (contaminated — Item2Vec trains on same reviews) |
| `convergent_validity_vs_judge` | DEFERRED to Phase 2 |
| `reliability_judge_repeat` | DEFERRED to Phase 2 |

**Gate:** only metrics marked USE / USE+DEBIAS drive keep/drop decisions in Phase 1. Non-circular co-play recall/ndcg are the primary; overlap is screening; Genre Precision is a guardrail only.