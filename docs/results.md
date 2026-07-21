# Results — current truth (P4 + P6)

> type: experiment-report · status: active · updated: 2026-07-14

**This page is the single source of truth for headline numbers.** Other pages cross-link here
instead of restating figures. Methodology and the circularity caveat: [evaluation](evaluation.md).
Evidence (Korean, append-only): [`experiments/p4_sweep/JOURNAL.md`](../experiments/p4_sweep/JOURNAL.md),
[`experiments/p4_sweep/LEADERBOARD.md`](../experiments/p4_sweep/LEADERBOARD.md).

## Bottom line
- **Serving ranker = EASE (λ ≈ 100) — CONFIRMED on the unbiased OOD panel (P6, 2026-07-14).**
  On 1,000 never-seen random-sampled users, EASE beats `userknn` **+0.0417** and old production
  `condcos` **+0.0447** on graded NDCG@20 (both q ≈ 0 after BH-FDR), and — decisively — also wins
  the **target-independent wishlist axis** (+0.0122 over userknn, q = 0.0013). The P4 shortlist pick
  now stands free of both cohort bias and metric circularity.
- **Preference definition = `pctl_game` (simplest).** On the OOD panel `pvalue` vs `pctl_game` is
  ns on wishlist (the registered decision axis) and `pctl_game` is even marginally *better* on
  NDCG (−0.0025 for pvalue, q = 0.023). Aggregate playtime-weighting suffices.
- **`knnpd03` (β = 0.3) is dead**: its in-cohort wishlist edge collapsed OOD (+0.0021 ns) and it
  significantly harms accuracy (−0.0156 NDCG, q ≈ 0). The registered grid point **β = 0.2** keeps a
  borderline wishlist edge (+0.0042, q = 0.0494) but is **dominated by EASE on both axes** — kept
  only as a legacy userknn-family lever, irrelevant to serving.
- **Absolute meaning — dual notation** (policy: every headline framing is an arithmetic
  derivation of a recorded raw value; raw stays in parentheses; caveats stay attached):
  - **"Blind-judged indistinguishable from the user's own loved games"** — EASE 50.0% High
    [41.5, 58.0] vs instrument ceiling 51.3% [44.1, 58.0] ⇒ **ceiling-normalized precision ≈ 97%**;
    operating-characteristic correction (sensitivity 0.513 / false-positive 0.075) puts the true
    interest share of EASE's top-10 at **~90%+** (rough 2-class estimate, n = 20).
    **Independently cross-validated (2026-07-21)**: a Gemini judge agrees with Sonnet at
    κ = 0.49 (arms) / 0.58 (ceiling), and its own blind ratings reproduce the ordering —
    EASE **59.5%** High vs own-loved-games 52.2% vs POP 31.5% vs random 6.0% — closing the
    single-judge-bias objection (JOURNAL T55).
  - **"8 of 10 recommendations at least touch the user's taste"** — High+Medium 82.0% (ceiling 80.2%).
  - **"6.7× random, +22pp over popularity"** — the pure personalization contribution on the
    popularity-tolerant v2 instrument (EASE 50.0% / POP 28.0% / random 7.5%).
  - **"~49× random-chance enrichment of unseen future behavior"** — top-20 catches 4.0% of future
    wishlist adds where chance = 0.08% (POP = 20×); **0.33 actual future-wishlist hits per 20 recs
    vs POP 0.098 (3.3×)**; offline MNAR ⇒ lower bound.
  - **"Half of a user's future wishlist sits in the top 2.3% of the ranking"** — per-user K for
    25/50/75% coverage ≈ 344 / 933 / 5,025 (POP 859 / 2,681 / 5,898); median target rank 988
    (POP 2,689). EASE dominates ~2–2.5× at every serving-relevant depth (K ≤ 5,000); the deep tail
    (K ≥ 10,000) is a POP-favoring artifact zone (enumeration + smaller rankable index) no one
    serves from; 100% coverage needs ~the whole catalog for any ranker (worst-target dominated).
  - Judge caveats (v1: no popularity-rating correlation; v2 re-admits one — dual interpretation
    recorded; card-based proxy, unvalidated vs real humans) live in JOURNAL T49–T52.
  Recruiter-facing copy: [portfolio-headlines](portfolio-headlines.md).
- **Validated core (the moat)**: playtime-weighted co-play CF beats "give an LLM my library" on
  *personalization*; on an *anonymous / vibe* framing the LLM wins — that stack stays **retired**.
- **Everything learned/neural lost or tied** (see table). The confirmed winner is the *simplest*
  linear model.

## P6 — unbiased OOD confirmation (2026-07-14; the final gate)
Pre-registered ([`P6_PREREG.md`](../experiments/p4_sweep/P6_PREREG.md) v3) one-shot run on
**1,000 users drawn unconditionally from the depth = -1 random-SteamID cohort** (521 wishlist-eligible),
frozen-graph condition decides; BH-FDR over the registered m = 8 family:

| Registered comparison | Δ [95% CI] | q (BH) | Verdict |
|---|---|---|---|
| H1 EASE − userknn [NDCG] | **+0.0417** [+0.0355, +0.0479] | 0.0000 | **SIG — H1 confirmed** |
| H1 EASE − condcos [NDCG] | **+0.0447** [+0.0382, +0.0515] | 0.0000 | **SIG — H1 confirmed** |
| H2 pvalue − pctl [NDCG] | −0.0025 [−0.0047, −0.0002] | 0.023 | SIG (favors pctl) |
| H2 pvalue − pctl [wishlist] | −0.0002 | 0.84 | ns → **adopt pctl_game** |
| H3 knnpd03(β.3) − userknn [wishlist] | +0.0021 [−0.0034, +0.0079] | 0.51 | **ns — knob(β.3) dropped** |
| H3 knnpd02(β.2) − userknn [wishlist] | +0.0042 [+0.0010, +0.0076] | 0.0494 | borderline SIG |
| harm knnpd03(β.3) − userknn [NDCG] | −0.0156 [−0.0205, −0.0107] | 0.0000 | SIG harm |
| B-axis EASE − userknn [wishlist] | **+0.0122** [+0.0052, +0.0189] | 0.0013 | **SIG** |

Supporting condition (mixed graph = train + 1,936 exploration OOD users): same ordering, EASE top
(NDCG 0.3264); every slot lifts substantially vs the frozen graph (e.g. EASE 0.2468 → 0.3264) —
the user-count lever works OOD (quantified by E4). Anchors healthy in both conditions
(ORACLE 1.0 ≫ slots ≫ POP/null). **Winner's-curse shrinkage measured**: EASE−userknn +0.062
(in-cohort fresh) → +0.042 (OOD); direction and significance survive.

*Residual honesty note — RESOLVED (2026-07-20)*: the exact serving combo `pctl_game × EASE` was
not a registered slot (EASE slots ran with `pvalue`). The P5 build's exploration-pool sanity check
(n = 400, paired) found **pctl×EASE beats pvalue×EASE +0.0104 [+0.0071, +0.0139] SIG** — the
shipped combo is supported, not merely assumed (JOURNAL T53; descriptive, not a P6-style
confirmation claim).

## Exploration track (post-verdict, exploration pool only — 2026-07-14)
One-liners; detail in [`JOURNAL.md`](../experiments/p4_sweep/JOURNAL.md) T47–T49:
- **E1 cohort shift**: real slots shrink **18–30%** OOD but ordering holds (Kendall τ 0.822) —
  in-cohort shortlists are rank-reliable, value-inflated. *Why-EASE test T-b confirmed*: the
  EASE−userknn gap grows monotonically with library size (regression handles collinearity).
- **E5 challengers**: λ grid flat 30–100 (λ100 kept); *why-EASE test T-a confirmed* — clipping
  EASE's negative weights costs −0.0088 SIG; EDLAE all SIG worse; fusions ≤ EASE; SLIM deferred
  (its family separated downward).
- **E2 unbiased popularity**: snowball vs true ownership Spearman **0.715** — reviewer cohort
  systematically underweights F2P/casual; `outputs/p6/pop_unbiased.json` shipped for P5. The old
  pop-discount knob's SNIPS edge vanishes under unbiased propensities.
- **E3 light users** (5–11 items, n=1,252, descriptive): personalization works for typical users —
  EASE 0.216 vs POP 0.091 NDCG; no popularity fallback needed.
- **E4×E6 scaling**: EASE curve still rising (0.233→0.298; keep crawling). Industry two-tower
  (id+feature) reaches only 0.03–0.07 NDCG with a slope **3.6× flatter** than EASE — **no crossover
  in any crawlable range** (pre-registered predictions P1/P2 confirmed); its only real niche is
  cold-item scoring (recall 0.01–0.02 where EASE is structurally 0; P3 directional).

## The cutoff bug (why the ranker verdict flipped)
The ranker's `recommend` had `if score <= 0: break`, which truncated EASE's (legitimately
negative-scoring) tail — so EASE looked worst and `userknn` looked best. Only EASE was affected (MF
has no such break). Fixed → EASE is the winner (+0.062 SIG, above). This is the canonical example of
why conclusions get an adversarial re-check before they ship.

## The circularity caveat (why we don't trust in-cohort NDCG alone)
The in-cohort graded-NDCG target shares provenance with the playtime-derived preference scores:
per-game Spearman **ρ ≈ 0.958**. So in-cohort NDCG largely measures "reproduce the playtime
percentile," not independent quality. **The target-independent metric is held-out wishlist recall.**
Every claim below that matters is (or will be, at P6) confirmed on wishlist. Full argument:
[evaluation](evaluation.md).

## What was tested (all vs EASE unless noted)
| Candidate | Primary (in-cohort) | Independent (wishlist) | Verdict |
|---|---|---|---|
| **EASE** (λ≈100) | **best** shortlist | — | **serving pick** |
| `userknn` | −0.062 vs EASE (SIG) | — | beaten |
| `condcos` (old prod) | worst | — | retired |
| `knnpd03` (pop-discounted kNN, "S0") | NDCG ns; recall −0.011 (SIG loss) | **+0.0073 (SIG)** | **discovery knob, not an accuracy win** |
| MF family (ALS / BPR / NMF) | lose | — | dropped |
| Informed-negative BPR | −0.0514 (SIG) | — | dropped |
| DL — Mult-DAE neural CF | −0.1497 (SIG) | — | dropped (small/sparse favors linear) |
| Learned reranker (blend) | ns | ns | dropped |
| Achievement neural reranker | ns | +0.0059 (borderline ns) | dropped |
| Individual achievements | — | story +0.0024 (ns) best; rarity slightly neg | **aggregate completion suffices** |
| rarity E-family · intent ε-tier · R5 combos | ns / lose | — | dropped |

**`knnpd03` post-P6**: the β = 0.3 knob is dropped (wishlist edge collapsed OOD + SIG accuracy harm);
β = 0.2 retains a borderline wishlist edge but EASE dominates both axes, so no discovery knob ships.

## Status
P4 shortlisting **done** (in-cohort + fresh n = 854) → **P6 OOD confirmation done (2026-07-14)** —
verdicts above. Next: **P5** builder rewire around the confirmed EASE ranker, plus the exploration
track E1–E4 and the absolute-rubric judge. Live progress: [status](status.md); plan:
[roadmap](roadmap.md).
