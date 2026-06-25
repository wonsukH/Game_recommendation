# Phase 1 — Similar mode: does SVD/structure beat tag-cosine? (run `smoke1`)

Non-circular **co-play** ground truth, **50** seeds (support≥30). Evaluating RAW retrieval ranking (no rerank). 95% bootstrap CI (B=500).

> Note: avg |relevant| ≈ 25, so recall@10 is capped near 10/25; the cap is identical across variants so comparisons stay valid. Headline k = **50** (ceiling reachable).

## Ladder (recall / ndcg with 95% CI, coverage, gini)

| variant | recall@10 | recall@20 | recall@50 | ndcg@50 | coverage@10 | gini@10 |
|---|---|---|---|---|---|---|
| V0_random | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.002 [0.000,0.007] | 0.001 [0.000,0.003] | 0.049 | 0.027 |
| V1_popularity | 0.048 [0.020,0.084] | 0.106 [0.068,0.153] | 0.264 [0.205,0.330] | 0.134 [0.099,0.181] | 0.001 | 0.135 |
| tagset_jaccard | 0.103 [0.062,0.152] | 0.143 [0.097,0.198] | 0.222 [0.164,0.286] | 0.169 [0.117,0.232] | 0.048 | 0.037 |
| Vb_tagcosine | 0.127 [0.080,0.185] | 0.171 [0.111,0.239] | 0.235 [0.164,0.311] | 0.181 [0.123,0.251] | 0.048 | 0.040 |
| Vc_ppmi_svd | 0.083 [0.047,0.121] | 0.132 [0.089,0.179] | 0.200 [0.143,0.266] | 0.146 [0.098,0.197] | 0.049 | 0.031 |
| Vd_ensemble | 0.083 [0.047,0.121] | 0.132 [0.089,0.179] | 0.200 [0.143,0.266] | 0.146 [0.098,0.197] | 0.049 | 0.031 |

## Distinctiveness (overlap@10 — do variants even differ?)

- `Vc_vs_Vb@10` = 0.252  (1.0 = identical outputs, 0.0 = fully different)
- `Vd_vs_Vc@10` = 1.000  (1.0 = identical outputs, 0.0 = fully different)
- `Vb_vs_V1@10` = 0.006  (1.0 = identical outputs, 0.0 = fully different)

## Paired comparisons @50 (the decisions)

| comparison | Δrecall [CI] | Δndcg [CI] | Wilcoxon p | decision |
|---|---|---|---|---|
| Vb_tagcosine vs V1_popularity @50 | -0.029 [-0.148,+0.084] | +0.047 [-0.040,+0.126] | 5.2e-01 | **SIMPLIFY/INCONCLUSIVE (CI includes 0 — no detectable gain)** |
| Vc_ppmi_svd vs Vb_tagcosine @50 | -0.035 [-0.083,+0.011] | -0.035 [-0.061,-0.004] | 1.9e-01 | **DROP (significantly worse)** |
| Vd_ensemble vs Vc_ppmi_svd @50 | +0.000 [+0.000,+0.000] | +0.000 [+0.000,+0.000] | nan | **SIMPLIFY/INCONCLUSIVE (CI includes 0 — no detectable gain)** |

## Honest caveats

- Co-play labels are head/mid-skewed (reviews capped ~10/user); seeds restricted to support≥30. Conclusions apply to the sufficiently-reviewed catalog, not the deep long tail.
- `Vd_ensemble` == `Vc_ppmi_svd` is expected (ensemble_alpha=1.0 ⇒ Item2Vec OFF). Reported to confirm, not to claim a gain. Evaluating an actual Item2Vec variant on co-play would be CONTAMINATED.
- This measures retrieval relevance only; diversity/novelty rerank is evaluated separately.
- See `metric_trust_report.md` (this run dir) for Phase 0 metric validation.