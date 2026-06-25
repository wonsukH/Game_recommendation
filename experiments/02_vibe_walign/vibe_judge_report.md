# Phase 2c — Vibe judge (blinded, Claude + Gemini)

4 variants ranked per query, anonymized A/B/C/D. Borda: 1st=4..4th=1, averaged across 24 NL queries. Higher = better.

| variant | Gemini Borda | Claude Borda |
|---|---|---|
| Vb_tagcosine | 2.35 | 2.62 |
| Vc_svd_tags | 2.61 | 2.67 |
| Vd_walign | 1.74 | 1.50 |
| Ve_gemini_nn | 3.30 | 3.21 |

- Cross-judge top-1 agreement: 0.65

## Reading
- Higher Borda = judges preferred that method's recommendations.
- Ve (Gemini-NN fix) vs Vd (W_align): tests whether the newer method beats the broken ridge.
- Ve/Vb vs Vc: whether SVD helps vibe quality (Phase 1 said it hurt similar).
- Cross-model agreement guards against self-preference (system uses Gemini → Claude is independent).
## Bootstrap CIs + paired tests (combined Claude+Gemini Borda, n=23, B=2000)

| variant | combined Borda [95% CI] |
|---|---|
| Ve_gemini_nn (FIX) | 3.24 [2.96, 3.52] |
| Vc_svd_tags | 2.65 [2.22, 3.07] |
| Vb_tagcosine | 2.48 [2.11, 2.87] |
| Vd_walign (shipped) | 1.63 [1.30, 2.02] |

Paired (all significant, CI excludes 0):
- Ve − Vd_walign = +1.61 [+1.20, +1.98]  → fix massively beats the shipped W_align path
- Ve − Vc_svd_tags = +0.59 [+0.02, +1.20]
- Ve − Vb_tagcosine = +0.76 [+0.20, +1.30]
- Vb_tagcosine − Vd_walign = +0.85 [+0.24, +1.43]  → even plain tag-cosine beats W_align

VERDICT: W_align (shipped vibe path) is significantly the WORST natural-language→tag method.
The fix (Ve = Gemini-space NN tag selection + tag-cosine retrieval) is significantly the BEST,
confirmed by two independent blinded judges (Claude + Gemini).
