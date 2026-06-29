# Decisive test — tags vs pure LLM-on-descriptions (blinded)

> **유형**: experiment-report · **상태**: active · **run**: `decisive_report` · **갱신**: 2026-06-25

3-way blind ranking, n=24 NL queries, Borda 1st=3..3rd=1, combined Claude+Gemini. Higher = better.

| variant | combined Borda [95% CI] |
|---|---|
| Ve_through_tags | 2.38 [2.15, 2.60] |
| Vb_through_tags | 1.85 [1.54, 2.17] |
| Vf_llm_desc | 1.77 [1.50, 2.04] |

## Paired (combined Borda)
- Ve_through_tags − Vf_llm_desc = +0.60 [+0.21,+1.00] (SIG)
- Vb_through_tags − Vf_llm_desc = +0.08 [-0.44,+0.60] (ns)

## Verdict

**Through-tags (Ve) significantly beats pure LLM-on-descriptions → the vote-weighted, interpretable tag layer genuinely adds quality. The project's core IS defensible (as a tag-routing layer, not as custom embedding ML).**