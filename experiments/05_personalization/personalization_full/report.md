# Personalization hold-out — CF (playtime-weighted) vs LLM-with-library (run `personalization_full`)

> **유형**: experiment-report · **상태**: active · **run**: `personalization_full` · **갱신**: 2026-06-25

78 test users, leave-user-out CF, profile 70% / hold-out rest. Behavioral ground truth (held-out liked games). 95% bootstrap CI.

LLM out-of-catalog (pool-miss) rate: 4.7%

| system | recall@10 | recall@20 | ndcg@10 | ndcg@20 | recall@20 debiased | recall@20 long-tail |
|---|---|---|---|---|---|---|
| ORACLE | 1.000 [1.000,1.000] | 1.000 [1.000,1.000] | 1.000 [1.000,1.000] | 1.000 [1.000,1.000] | 1.000 [1.000,1.000] | 1.000 [1.000,1.000] |
| CF | 0.233 [0.167,0.306] | 0.293 [0.218,0.370] | 0.170 [0.115,0.227] | 0.190 [0.136,0.246] | 0.195 [0.121,0.277] | 0.130 [0.000,0.261] |
| LLM | 0.113 [0.066,0.165] | 0.173 [0.117,0.235] | 0.072 [0.040,0.109] | 0.092 [0.057,0.131] | 0.123 [0.069,0.185] | 0.000 [0.000,0.000] |
| POP | 0.009 [0.000,0.021] | 0.034 [0.011,0.062] | 0.005 [0.000,0.013] | 0.013 [0.003,0.025] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] |

## Paired comparisons

| comparison | Δ [CI] | significant |
|---|---|---|
| CF - LLM recall@20 | +0.120 [+0.049,+0.192] | True |
| CF - LLM ndcg@20 | +0.097 [+0.049,+0.149] | True |
| CF - LLM recall@20_longtail | +0.130 [+0.000,+0.261] | False |
| CF - POP recall@20 | +0.259 [+0.179,+0.338] | True |

## Decision (pre-registered)

**CF significantly beats LLM-with-library on held-out recall → personalization is a genuine moat → proceed to redesign.**