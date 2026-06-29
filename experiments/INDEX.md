# Experiment Index — every comparison, where its log lives

> **유형**: index · **상태**: active · **갱신**: 2026-06-29

> **폴더 정리됨 (목적별).** 아티팩트는 이제 하위폴더에 있다: `01_similar_eval/`, `02_vibe_walign/`,
> `03_decisive_tags_vs_llm/`, `04_paradigm_vs_llm/`, `05_personalization/`, `_workflow_scripts/`.
> 구조 지도는 `README.md` 참고. 아래 표의 파일명은 해당 단계 하위폴더 기준(P0/L/P1/P2a→01, P2b→02, P2d→03, P2c·P2e·P2f→04, P3→05).

Master catalog of all experiments run while answering "is the construction
meaningful?". Every comparison writes a permanent artifact here (append-only;
production artifacts never touched). `registry.jsonl` holds one machine-readable
line per run; this file is the human-readable index.

Interpreters used: `python3` (numpy/scipy/pandas/sklearn) for offline math;
Gemini (system component) for vibe embedding/parsing; Claude sub-agents for the
independent judge. The project `.venv` is broken (anaconda base missing); deps
were restored into `python3`.

| # | comparison | question | key result | artifacts |
|---|---|---|---|---|
| P0 | Metric validation | are the metrics trustworthy before use? | floor/ceiling PASS, perturbation PASS, discriminative PASS, **popularity-confound → USE+DEBIAS**, Genre-Precision → circular/DEMOTE | `phase1_final/metric_trust_report.md` |
| L | Co-play labels | build non-circular ground truth | 410 seeds (support≥30), ~25 rel each, from 103k users | `tests/coplay_eval_set.json`, `coplay_labels_stats.json` |
| P1 | **similar: SVD vs tag-cosine** | does PPMI+SVD beat tag-cosine on co-play? | **SVD significantly WORSE** (Δrecall −0.044, Δndcg −0.047, Wilcoxon p=1.5e-17); robust to popularity-debias; Item2Vec inert (Vd==Vc) | `phase1_final/report.md`, `aggregate.json`, `per_query.csv` |
| P2a | masked-tag recovery | does SVD generalize (recover removed tags)? | **SVD recovers 10–14× above chance** (median rank top-10%); raw tag-cosine = chance (structurally cannot). Generalization capacity real but modest (recall@100=13%) | `masked_tag_report.md`, `.json` |
| P2b | vibe rec-lists | qualitative: what do vibe variants return? | **W_align (Vd) visibly broken** (cozy→utility software, roguelike→Wordle); tag-cosine (Vb) on-target | `vibe_lists.json` |
| P2c | vibe judge (blinded, Claude+Gemini) | which vibe variant is best? | **Ve(fix) best 3.24, W_align worst 1.63** [Borda]; all paired diffs significant; cross-judge top-1 agree 0.65 | `vibe_judge_report.md`, `vibe_judge_{gemini,claude,key,tasks}.json` |
| F1 | **fix: W_align → Gemini-NN (Ve)** | newer method beats broken ridge? | **YES — Ve beats shipped W_align by +1.61 Borda (sig), beats SVD-tags +0.59, beats tag-cosine +0.76** | `vibe_lists.json` (Ve_gemini_nn), `vibe_experiment.py` |

| P2d | **decisive: tags vs LLM-on-descriptions** | is the tag layer redundant vs generic LLM-RAG? | **Ve(tags) 2.38 > Vb 1.85 > Vf(LLM-desc) 1.77; Ve−Vf=+0.60 SIG** → vote-weighted tag layer significantly BEATS description-embedding RAG (descriptions = marketing text, worse genre/mood signal) | `decisive_report.md`, `decisive_*.json` |
| P2e | **LLM-alone vs system (Ve), blinded** | is "just ask the LLM" best? is niche-ness "hidden gems"? | **System win-rate 0.04 [0.00,0.12] → LLM-alone wins ~96%**. LLM pool-miss only 2.5%. System more niche (0.59 vs 0.89) but NOT higher quality (user-score 6.09 vs 6.14). → niche-ness is "obscure, not better", NOT "hidden gems" (as-is) | `paradigm_report.md`, `paradigm_*.json`, `llm_alone_lists.json` |

| P2f | **fair discovery: system vs LLM-forced-niche** | does the system win the DISCOVERY use-case (the fair test)? | **System win-rate 0.04 [0.00,0.10] → LLM wins ~96% even at discovery**. LLM-gem pool-miss rose to 13.3% (grounding finally matters) but not enough; LLM knows acclaimed gems (Tyranny/Kenshi/Underrail/Norco) better than tag-retrieval | `gem_report.md`, `gem_*.json` |
| P3 | **PERSONALIZATION: CF vs LLM-with-library** (hold-out, behavioral) | does personalized CF beat "give the LLM my library"? | **YES — first regime the system WINS. CF recall@20=0.293 vs LLM 0.173, Δ+0.120 [+0.049,+0.192] SIG; ndcg Δ+0.097 SIG; POP 0.034 (so behavioral signal, not popularity). CF ~1.7× the LLM.** Caveat: thin profiles (data cap ~10/user) handicap both → conservative for CF; real libraries likely widen gap. long-tail Δ+0.130 borderline (CI incl 0) | `personalization_full/report.md` |

| D | **agentic vs single-pass** (재설계 게이트) | 에이전트 오케스트레이션이 값을 하나? | 1차(min-combine)는 경계 ns였으나 **융합 개선(interleave)으로 strict 게이트 통과**: 다중주체 min(A,B) 0.108 vs 0.011, Δ+0.097 [+0.053,+0.147] **SIG**(친구 B 0.028→0.281); 과제약 완결성 0.98 vs 0.42. → **KEEP agentic(interleave)**, 단 복합/다중주체/과제약에 한정(단순=단일패스/CF로 라우팅) | `agentic_fusion_sweep/report.md`, `agentic_gate/`(1차) |

| DS | **data-scaling (user-count)** | 데이터 더 늘리면 CF 좋아지나? | **예, 유의·단조**: recall@20 0.192(25%)→0.268(100%), Δ+0.076 [+0.039,+0.117] SIG, 미포화(수확체감). 라이브러리 풍부도 축(GetOwnedGames)은 미측정(더 큰 레버 추정) | `datascaling_users/report.md` |

| 진단 | 데이터 문제 정량화 | 데이터 측면 병목은? | 프로파일 얇음(좋아요 mean 3.05, ≥8은 2.8%), 콜드스타트 15.1%(1506게임 CF 추천불가, 꼬리), 공출현 희소(deg<10이 50%), 품질신호 사각(metacritic 30.5%) | `DELIBERATION_LOG.md` (데이터 보강 0) |
| D2 | **user-score 품질신호** | metacritic(30.5%) 사각 메우나? | **YES**: Bayesian-shrunk user-score 86.6% 커버, metacritic과 Spearman 0.374(양의·비-redundant). quality_gate가 실제 작동(p50 게이트 9956→6577 vs metacritic≥75는 8897로 거의 무력). **채택** | `DELIBERATION_LOG.md`, `serving/data/game_quality.json` |
| D1 | **콜드스타트 콘텐츠 폴백** | CF-콜드 1506게임 추천가능·recall? | **커버리지 100%**(8450→9956), 콜드/얇은유저 robustness(완전콜드 프로파일에 CF=0→폴백 결과). 단 **전체 recall은 null**(Δ+0.003 ns — 콜드 holdout 0.3%뿐). 정직: 가치=커버리지·robustness·스티어링 base, recall 아님 | `coldstart_*/report.md` |
| D3 | **저-support shrinkage** | C/(C+λ)가 sparse 공출현 도움? | **NULL**: 어떤 λ도 baseline 못 이김(전부 Δ≈0 ns). 사전등록대로 **드롭**(min_cooc≥3+conditional-cosine으로 충분). 골대 안 옮김 | `shrinkage_*/report.md` |
| D4 | **라이브러리 풍부도 레버** | 유저당 게임 많을수록 CF↑? | **YES, 큰 레버**: recall@20 프로파일 p1=0.089→p4=0.184 **2배**, Δ+0.095 [+0.070,+0.120] SIG, 미포화(마지막 스텝도 SIG). 실현 평균 3.05가 캡(10)보다 진짜 병목 → **GetOwnedGames 입력 정당**(모델 변경 0) | `libraryrichness_*/report.md` |
| F | **방향성 스티어링: 신장르-recall (비순환)** | 인접노벨티가 유저 본인 분기행동 회복? | **YES**: plain CF 신장르 recall **0.0098**(구조적 실패=필터버블 확인) vs 노벨티 스티어 0.078~0.121, 전 β CI>0 SIG. 트레이드오프 정직: overall 0.220→0.089(β2). β3은 dominated. = 명시적 탐색모드로 정당 | `steering_large/report.md` |
| F-judge | **스티어링 blinded judge** | 스티어 리스트가 탐색/측면 요청을 더 잘 충족? | **YES, 만장일치**: 스티어 vs 자기 CF-baseline 12케이스×3 블라인드 → win-rate **1.000** [1.000,1.000] (novelty 6/6, aspect 6/6, quality_ok 1.0). baseline은 라이브러리 장르 반복으로 판정패. familiarity-bias 중립화(둘 다 실제 게임) | `steering_judge_result.json`, `steering_cases.json` |
| b | **라이브러리 풍부도 LIVE (실 GetOwnedGames)** | D4 외삽이 실데이터에서도 성립? | **YES, 확정**: 190 공개프로필 크롤(in-pool 플레이 median 119 vs 크롤 프록시 3 = ~40×). 129명 실유저 recall@20 p3=0.056→p30=0.123, Δ+0.068 [+0.054,+0.082] **SIG**(2.2×), 미포화. → GetOwnedGames 입력이 개인화 최대 레버임을 실데이터로 확정 | `libraryrichness_live_*/report.md`, `owned_libraries.json` |

## Decisions reached (data-backed)
> ⚠️ **아래 similar/vibe/SVD/W_align/Item2Vec/Genre-Precision 관련 결정은 *피벗으로 폐기된 태그-유사도 스택* 기준 — 현 시스템 아님(증거로만 보존).** 현 코어 결정은 PERSONALIZATION(P3)·AGENTIC(D)·STEERING(F)·DATA(D1–4) 항목. 현 포지셔닝: 개인화 CF = 입증된 scoped moat(LLM-lib 이김·EASE 동률), 자기비판 평가는 보완 역량(성능 '대신' 아님).
- **similar mode**: drop SVD, use vote-weighted tag-cosine (simpler + significantly better on non-circular co-play; SVD worse, p=1.5e-17).
- **vibe mode (NL→tag)**: **replace W_align ridge with Gemini-space NN tag selection (Ve)** — significantly best on blinded Claude+Gemini judge; shipped W_align is significantly worst.
- **Item2Vec / β-steering**: confirmed inert in shipped config (Vd==Vc); keep off.
- **Genre Precision**: demote to guardrail (circular — tag-cosine inflates it).
- **SVD net role**: hurts exact retrieval (similar); has modest generalization capacity (masked-tag 10–14× chance) but does NOT translate to better vibe recommendations than the simpler Ve fix. Net: the SVD/W_align stack is not earning its complexity.
- **vs just-ask-the-LLM (anonymous/NL)**: generative LLM-alone beats the system ~96% on blinded quality, barely hallucinates (2.5%), so grounding/anti-hallucination are weak selling points. The crawled pool is a *limitation*, not a moat.
- **PERSONALIZATION is the moat (P3)**: when recommending from a user's OWN library/history, behavioral CF significantly beats "LLM + library" (Δrecall@20 +0.120, ndcg +0.097, both sig; ~1.7×). This is the one direction where a custom system genuinely earns its place — the meaningful rebuild target. Multi-agent role: LLM understands NL + user, calls CF as the ranking tool (which the LLM can't replicate), explains/filters.
- **AGENTIC layer earns its place — but SCOPED (D)**: agentic orchestration (interleave multi-entity fusion + under-fill refine) significantly beats single-pass on multi-entity ("me+friend": min-recall 0.108 vs 0.011, +0.097 SIG) and over-constrained completeness (0.98 vs 0.42). It does NOT help simple single-user requests → router sends simple→single-pass/CF, anonymous-NL→LLM, compound/multi-entity/constrained→agentic. "Use the agent only where it's needed."
- **"hidden-gem discovery" headline**: NOT supported as-is. System is more niche but its niche picks are judged worse-fitting and are not higher-rated → "obscure, not gems". Caveat: judges have familiarity bias (recognize famous games), so 0.04 is a generous lower bound on the system — but it still loses decisively. To make hidden-gems real, would need to FILTER niche candidates by quality/acclaim (not just tag-similarity) and target power-users in a controlled catalog.
- **DATA side (진단→보강)**: (D2) adopt a dense user-score quality signal (86.6% vs metacritic 30.5%, spearman 0.37) so quality-gating actually bites; (D1) add a content tag-cosine cold-start fallback → 100% pool coverage + robustness for cold/thin libraries (honest: NO aggregate-recall lift — cold games are tail — value is coverage/robustness/steering-base); (D3) **reject** support-shrinkage (null, dropped per pre-registration); (D4) library RICHNESS is a large, non-saturating lever (recall doubles p1→p4, +0.095 sig) — the realized mean of 3.05 liked-games, not the cap, is the true bottleneck → **wire GetOwnedGames as the input** (no model change).
- **STEERING (new feature, user-requested)**: directional steering = CF moat reranked by content (adjacent novelty + liked-aspect), invoked in natural language. Validated non-circularly: plain CF has a STRUCTURAL ~0 on new-genre recall (filter-bubble); novelty steering recovers the user's own branch-out behavior (0.01→0.12, all β sig) at an honest overall-recall tradeoff → shipped as an explicit OPT-IN explore mode (router `explore` route), not the default. Aspect steering lifts aspect-match mechanically (0.25→0.44) and is checked by a blinded Claude judge panel.

## Notes on logging hygiene
Final results of every comparison are saved here. A few *exploratory* steps
(co-play param tuning trials, a pre-bake debias spot-check, the vibe smoke on 4
queries) were run to `/tmp` or stdout while iterating; their *canonical* re-runs
are the logged artifacts above. From F1 onward, all runs (incl. fixes + judge)
write here and append to `registry.jsonl`.
