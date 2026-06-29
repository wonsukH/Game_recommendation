# Fair hidden-gem test — system (Ve) vs LLM forced into discovery

> **유형**: experiment-report · **상태**: active · **run**: `gem_report` · **갱신**: 2026-06-25

n=24 NL queries, Claude+Gemini, DISCOVERY-framed judge (famous = penalty, must be good + lesser-known).

- **System(Ve) win-rate vs LLM-gem: 0.04 [0.00, 0.10]** (0.5 = tie)
- LLM-gem out-of-catalog (pool-miss) rate: 13.3%  (vs 2.5% when LLM recommended mainstream — forcing niche RAISES hallucination)
- popularity pctile: Ve 0.59 vs LLM-gem 0.65 (both should now be niche)

## Verdict

**LLM still wins even at discovery → the LLM knows enough indie/niche games that the system's catalog retrieval is not a clear advantage; hidden-gem discovery is NOT a sufficient moat.**