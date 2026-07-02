# Phase 1 — Similar mode: does SVD/structure beat tag-cosine? (run `phase1_full`)

> **유형**: experiment-report · **상태**: active · **run**: `phase1_full` · **갱신**: 2026-06-25

Non-circular **co-play** ground truth, **410** seeds (support≥30). Evaluating RAW retrieval ranking (no rerank). 95% bootstrap CI (B=1000).

> Note: avg |relevant| ≈ 25, so recall@10 is capped near 10/25; the cap is identical across variants so comparisons stay valid. Headline k = **50** (ceiling reachable).

## Ladder (recall / ndcg with 95% CI, coverage, gini)

| variant | recall@10 | recall@20 | recall@50 | ndcg@50 | coverage@10 | gini@10 |
|---|---|---|---|---|---|---|
| V0_random | 0.001 [0.001,0.002] | 0.002 [0.001,0.003] | 0.005 [0.003,0.006] | 0.004 [0.003,0.006] | 0.339 | 0.147 |
| V1_popularity | 0.045 [0.038,0.052] | 0.094 [0.084,0.104] | 0.211 [0.196,0.227] | 0.154 [0.142,0.165] | 0.001 | 0.104 |
| tagset_jaccard | 0.060 [0.052,0.069] | 0.092 [0.081,0.103] | 0.155 [0.141,0.169] | 0.142 [0.130,0.156] | 0.255 | 0.286 |
| Vb_tagcosine | 0.075 [0.065,0.085] | 0.105 [0.092,0.118] | 0.164 [0.149,0.179] | 0.156 [0.143,0.171] | 0.253 | 0.297 |
| Vc_ppmi_svd | 0.046 [0.039,0.053] | 0.072 [0.063,0.081] | 0.120 [0.107,0.134] | 0.109 [0.099,0.120] | 0.277 | 0.252 |
| Vd_ensemble | 0.046 [0.039,0.053] | 0.072 [0.063,0.081] | 0.120 [0.107,0.134] | 0.109 [0.099,0.120] | 0.277 | 0.252 |

## Distinctiveness (overlap@10 — do variants even differ?)

- `Vc_vs_Vb@10` = 0.252  (1.0 = identical outputs, 0.0 = fully different)
- `Vd_vs_Vc@10` = 1.000  (1.0 = identical outputs, 0.0 = fully different)
- `Vb_vs_V1@10` = 0.002  (1.0 = identical outputs, 0.0 = fully different)

## Paired comparisons @50 (the decisions)

| comparison | Δrecall [CI] | Δndcg [CI] | Wilcoxon p | decision |
|---|---|---|---|---|
| Vb_tagcosine vs V1_popularity @50 | -0.047 [-0.068,-0.023] | +0.002 [-0.016,+0.021] | 2.0e-06 | **DROP (significantly worse)** |
| Vc_ppmi_svd vs Vb_tagcosine @50 | -0.044 [-0.054,-0.033] | -0.047 [-0.056,-0.038] | 1.5e-17 | **DROP (significantly worse)** |
| Vd_ensemble vs Vc_ppmi_svd @50 | +0.000 [+0.000,+0.000] | +0.000 [+0.000,+0.000] | nan | **SIMPLIFY/INCONCLUSIVE (CI includes 0 — no detectable gain)** |

## Honest caveats

- Co-play labels are head/mid-skewed (reviews capped ~10/user); seeds restricted to support≥30. Conclusions apply to the sufficiently-reviewed catalog, not the deep long tail.
- `Vd_ensemble` == `Vc_ppmi_svd` is expected (ensemble_alpha=1.0 ⇒ Item2Vec OFF). Reported to confirm, not to claim a gain. Evaluating an actual Item2Vec variant on co-play would be CONTAMINATED.
- This measures retrieval relevance only; diversity/novelty rerank is evaluated separately.
- See `metric_trust_report.md` (this run dir) for Phase 0 metric validation.