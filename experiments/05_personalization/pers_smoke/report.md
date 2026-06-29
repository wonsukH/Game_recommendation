# Personalization hold-out — CF (playtime-weighted) vs LLM-with-library (run `pers_smoke`)

> **유형**: experiment-report · **상태**: active · **run**: `pers_smoke` · **갱신**: 2026-06-25

12 test users, leave-user-out CF, profile 70% / hold-out rest. Behavioral ground truth (held-out liked games). 95% bootstrap CI.


| system | recall@10 | recall@20 | ndcg@10 | ndcg@20 | recall@20 debiased | recall@20 long-tail |
|---|---|---|---|---|---|---|
| ORACLE | 1.000 [1.000,1.000] | 1.000 [1.000,1.000] | 1.000 [1.000,1.000] | 1.000 [1.000,1.000] | 1.000 [1.000,1.000] | 0.000 [0.000,0.000] |
| CF | 0.069 [0.000,0.167] | 0.139 [0.034,0.264] | 0.052 [0.000,0.129] | 0.073 [0.012,0.154] | 0.121 [0.000,0.333] | 0.000 [0.000,0.000] |
| POP | 0.028 [0.000,0.098] | 0.111 [0.013,0.236] | 0.017 [0.000,0.059] | 0.042 [0.006,0.090] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] |

## Paired comparisons

| comparison | Δ [CI] | significant |
|---|---|---|
| CF - POP recall@20 | +0.028 [-0.125,+0.181] | False |

## Decision (pre-registered)

(LLM arm skipped — CF/POP smoke only.)