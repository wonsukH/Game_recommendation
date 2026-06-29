# Phase 0 — Metric Trust Report

> **유형**: metric-report · **상태**: active · **run**: `phase1_full` · **갱신**: 2026-06-25

Anchors + 4 real variants over **410 co-play seeds**. Headline k = **50** (recall ceiling reachable since k ≥ avg |relevant|).

## Anchor recall (validation)

| system | recall@10 | recall@20 | recall@50 | ndcg@10 | ndcg@20 | ndcg@50 |
|---|---|---|---|---|---|---|
| random | 0.001 | 0.002 | 0.005 | 0.004 | 0.003 | 0.004 |
| popularity | 0.045 | 0.094 | 0.211 | 0.102 | 0.115 | 0.154 |
| oracle | 0.585 | 0.783 | 1.000 | 1.000 | 1.000 | 1.000 |
| oracle_drop5 | 0.343 | 0.470 | 0.635 | 0.796 | 0.751 | 0.716 |
| oracle_drop10 | 0.198 | 0.292 | 0.415 | 0.612 | 0.555 | 0.491 |
| tagset_jaccard | 0.060 | 0.092 | 0.155 | 0.145 | 0.135 | 0.142 |
| Vb_tagcosine | 0.075 | 0.105 | 0.164 | 0.172 | 0.154 | 0.156 |
| Vc_ppmi_svd | 0.046 | 0.072 | 0.120 | 0.111 | 0.104 | 0.109 |
| Vd_ensemble | 0.046 | 0.072 | 0.120 | 0.111 | 0.104 | 0.109 |

## Validation checks

- **Floor/Ceiling**: random=0.005, oracle=1.000 → PASS (oracle must be ≥0.90 and random ≤0.05)
- **Perturbation monotonic**: oracle=1.000 > drop5=0.635 > drop10=0.415 → PASS
- **Discriminative power**: real-variant recall spread=0.044 → PASS (need ≥0.02 to separate systems)
- **Popularity confound**: popularity=0.211 vs random=0.005 (×46.8) → CONFOUNDED

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