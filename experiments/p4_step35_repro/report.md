# Personalization hold-out — CF (playtime-weighted) vs LLM-with-library (run `p4_step35_repro`)

> **유형**: experiment-report · **상태**: active · **run**: `p4_step35_repro` · **갱신**: 2026-07-02

0 test users, leave-user-out CF, profile 70% / hold-out rest. Behavioral ground truth (held-out liked games). 95% bootstrap CI.


| system | recall@10 | recall@20 | ndcg@10 | ndcg@20 | recall@20 debiased | recall@20 long-tail |
|---|---|---|---|---|---|---|
| ORACLE | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] |
| CF | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] |
| POP | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] | 0.000 [0.000,0.000] |

## Paired comparisons

| comparison | Δ [CI] | significant |
|---|---|---|
| CF - POP recall@20 | +0.000 [+0.000,+0.000] | False |

## Decision (pre-registered)

(LLM arm skipped — CF/POP smoke only.)