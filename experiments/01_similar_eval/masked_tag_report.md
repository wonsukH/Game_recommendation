# Phase 2a — Masked-tag recovery (does SVD generalize?)

> **유형**: experiment-report · **상태**: active · **run**: `masked_tag_report` · **갱신**: 2026-06-25

Masked **360** strong (game,tag) memberships across **120** tags, rebuilt PPMI+SVD (dim=128) on the masked matrix, then tried to recover the removed game from the removed tag's vector. n_games=9956.

| k | SVD recall@k | raw-masked recall@k | chance |
|---|---|---|---|
| 10 | 0.011 | 0.000 | 0.0010 |
| 50 | 0.069 | 0.000 | 0.0050 |
| 100 | 0.131 | 0.003 | 0.0100 |

- **SVD median rank percentile**: 0.100 (0 = top, 0.5 = chance)
- **raw-masked median rank percentile**: 0.506

## Reading

- SVD recall@10 = 0.011 vs chance 0.0010: SVD recovers removed memberships **far above chance** → genuine second-order generalization capacity.
- raw-masked ≈ chance by construction (the masked entry is 0): tag-cosine structurally CANNOT recover removed memberships. This is the one thing SVD can do that raw tags cannot.

## Honest caveat

Recovery-above-chance shows generalization CAPACITY, not that SVD recommends better than tag-cosine. Phase 1 showed SVD is worse for exact similar-mode retrieval; whether its generalization is a NET win for vibe recommendations is decided by the vibe-mode judge (Phase 2 part 3).