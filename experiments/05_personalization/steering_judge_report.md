# F — directional-steering blinded judge

> **유형**: experiment-report · **상태**: active · **run**: `steering_judge_report` · **갱신**: 2026-06-29

**Question.** When the user asks to branch out (new genre) or emphasize a liked
aspect, does the system's *steered* list beat its own *plain-CF* list at fulfilling
that request — judged blind?

**Setup.** 12 cases (6 novelty + 6 aspect) over 6 demo libraries. For each, the
steered list and the plain-CF list were shown as A/B in randomized order (steered
side hidden). 3 independent Claude judges per case (perspective-diverse lenses:
equal-weight, strict-direction-change, best-overall), majority vote. Judges read
only request + library + the two lists (no "steered" key). Aspect cases also told
the target aspect. quality_ok flag guards against "novel but random".

**Result.**

| metric | value |
|---|---|
| steered win-rate | **1.000 [1.000, 1.000]** (12/12, 36/36 votes) |
| novelty cases | 6/6 |
| aspect cases | 6/6 |
| quality_ok rate | 1.000 |

Every case was a 3–0 sweep for the steered list. Judges consistently penalized the
plain-CF baseline for "merely echoing the library's existing genres" on branch-out
requests, and credited the steered list for moving into genuinely new-for-the-user
territory while staying coherent; for aspect cases they noted the steered list
carried the requested tag (story-rich / atmospheric / combat / open-world) far more
strongly.

**Why this is a fair test.** Unlike P2e/P2f (system vs generative LLM, where judge
familiarity bias favored famous titles), here both lists are real games from the
same catalog and the same CF base — so familiarity bias is neutralized and the
comparison isolates the steering operator itself.

**Caveats (honest).** n=12 is modest; the win is clean partly because plain-CF
structurally repeats the user's genres (the very gap steering targets). The harder,
non-circular evidence is the behavioral new-genre hold-out recall (`steering_large/
report.md`, n=153, all β significant). Steering is shipped as an explicit opt-in
explore mode, not the default, because it trades overall recall for new-genre reach.

Artifacts: `steering_judge_result.json` (per-case votes), `steering_cases.json`
(the cases + answer key in `steering_key.json`).
