# DELIBERATION LOG — 고민·문제해결 과정의 서사 (append-only)

> **유형**: reasoning-log · **상태**: active · **갱신**: 2026-06-30

> 결과 수치가 아니라 *왜 시도했고, 무엇에 반박했고, 방향이 어떻게 바뀌었는지*의 기록.
> 사용자 상시 요구("정말정말 중요"). 매 고민/결정마다 즉시 추가. 결과 로그는 INDEX.md / registry.jsonl / 각 run report.md.

---

## 0. 백필 — 이 프로젝트 평가의 전체 추론 여정 (2026-06-22 ~ 06-23)

1. **시작**: "Game_recommendation 폴더 전체를 비판적·객관적으로 평가." → 8차원 다중에이전트 워크플로우(+적대적 검증+종합). 결론 ~5.5/10: 문서·정직성은 평균↑이나 **주장이 코드보다 앞서감**. Bayesian 가중치 shape 버그로 dead, Genre Precision 순환, 슬라이드 수치 stale/체리픽, "멀티에이전트"=고정 DAG, 테스트 ~8%, W_align underdetermined. 최강 자산 = 자기비판 평가역량.
2. **사용자: "포트폴리오 관점 빼고, 구성 자체가 의미 있나?"** → 문제·골격은 타당하나 복잡도가 단순 베이스라인을 이긴다는 증명이 한 번도 없었음. 결정적 시험 필요(SVD/W_align vs 단순).
3. **사용자: "반복 실험으로 입증+로그화. 지표 먼저 분석 제시. 멀티에이전트 살리되 단일과 비교. 무의미 부분 전수 감사. 더 나은 방법 추천."** → 지표 후보 분석(co-play / masked-tag / pairwise judge / overlap / coverage / novelty-calib / Genre 재배치)을 why-meaningful·how-distorted·when-appropriate로 제시 + 죽은 부품 감사표.
4. **사용자 반문/재정의**: "현 데이터로 다 가능?"→예(co-play 103K 유저/4,200 seed 실측). "핵심 증명 먼저", "judge는 Claude+Gemini 둘 다". **핵심 재정의: 의미 있는 구조는 refine 루프가 아니라 'similar(게임)↔vibe(자연어)' 모드 분기"** → 두-모드 입증으로 재편.
5. **사용자: "지표 자체가 적절한지 검증하는 단계 추가 + 전 과정 비판적·객관적."** → Phase 0 지표검증(floor/ceiling·구별력·순환·수렴·섭동·신뢰도) + 운영원칙(사전등록·귀무보고·CI·적대적 검증) 명문화.
6. **Phase 0+1 (similar) 실행**: 인프라 구축(co-play 라벨 410, 태그-cosine 베이스라인, metrics/stats/run_logger/metric_validation/experiment). **결과: SVD가 태그-cosine보다 유의하게 나쁨**(Δrecall −0.044, Δndcg −0.047, Wilcoxon p=1.5e-17), 인기보정 후에도 견고. Item2Vec 무용(Vd==Vc). Genre Precision 순환 확정→강등. Phase 0 통과(oracle 1.0/random 0.005/섭동 단조/인기혼입 감지).
7. **Phase 2a masked-tag**: SVD 일반화 능력 chance의 10–14×(중앙값 상위 10%)이나 modest(recall@100=13%); raw 태그=chance. 능력은 있으나 추천 이득으로 미전환.
8. **환경 복구**: `.venv` 깨짐(anaconda base 누락) → `python3`에 의존성 복구. langchain 메타패키지 버전충돌 → `langchain_core`만 사용.
9. **사용자: "Claude 심판은 서브에이전트로 직접 하면 되잖아?"** → 채택. Anthropic 키 불필요, 시스템=Gemini라 Claude가 self-preference 회피 독립 심판.
10. **Phase 2b vibe**: W_align 출력 망가짐(cozy→유틸리티 SW, roguelike→Wordle), temp=0인데도 불안정. **수정안 Ve**(Gemini 원본공간 NN 태그선택, ridge 사영 대체) 구현.
11. **사용자: "모든 비교 로그 따로 저장 중?"** → INDEX.md + registry.jsonl 통합(전 run 등록).
12. **사용자: "망가진 부분 새 방법으로 고쳐봐"** → Ve. vibe 심판(blinded Claude+Gemini): **Ve 최선(Borda 3.24), W_align 꼴찌(1.63)**, 모든 paired 유의. 수정 성공·W_align 유의하게 최악 확인.
13. **사용자: "태그를 자연어에 직접 코사인하면 의미 있나? 그냥 처음부터 자연어로 게임 분류하면?"** → 결정적 시험: Ve(태그 경유) vs Vf(LLM 설명문 임베딩). **Ve 2.38 > Vb 1.85 > Vf 1.77, Ve−Vf=+0.60 유의** → 태그(vote 합의)가 설명문보다 나음. 단 custom-ML 명제는 해체(실질 작업은 Gemini가 함).
14. **사용자: "그럼 그냥 LLM이 최고 아냐?"** → 패러다임 심판: system(Ve) vs 생성형 LLM-단독. **시스템 승률 0.04(LLM ~96% 승)**. LLM 풀이탈 2.5%. 시스템 더 niche(0.59 vs 0.89)이나 품질 동급.
15. **사용자: "유명작 이기는 건 말 안 됨; 이미 한 사람은 새 게임 원하니 발굴이면 의미 있지?"** → (방법론 반박 수용) 공정 발굴 시험: LLM도 숨은명작 강제 + 발굴-관점 심판(유명세=감점). **시스템 0.04 여전(LLM 발굴에서도 ~96% 승)**. LLM-gem 풀이탈 2.5%→13.3% 상승(grounding 처음 의미)이나 역부족. LLM이 명작(Tyranny/Kenshi/Underrail) 잘 앎.
16. **사용자: "숨은 명작 발굴이 메인?"** → 시스템 niche 픽 품질 동급(유저점수 6.09 vs 6.14), 두 심판 모두 LLM 선호 → 헤드라인으로 as-is 미달.
17. **사용자: "멀티에이전트 유지하며 전체 재설계? 어떤 방법?"** → LLM 생성 + 에이전트 그라운딩(도구·사이클·메모리) 제안. 그래프/크롤러/메타데이터 탐색(크롤러=라이브 도구 가능, 로컬 제약데이터 풍부 확인).
18. **사용자: "그럼 사실상 추가되는 건 '이미 한 게임 제외'뿐 아냐?"** → 정직 인정: 익명/seed 수준이면 맞음(LLM이 in-context로 대부분 함). 의미 있으려면 전체-라이브러리 취향 모델(개인화 CF).
19. **사용자: "'X 한 사람이 Y도 좋아함' 끌어올 수 있나? 그래도 제외뿐 아냐?"** → co-play 데이터 이미 있음(평가용으로 구축). 단 주류 seed는 LLM도 co-play 앎 → CF는 long-tail/freshness/정량에서만 우세. 진짜 moat = seed 아닌 **전체 라이브러리** 취향 모델.
20. **사용자 결정**: 전체 라이브러리 개인화로 피벗; **작은 실증 실험 먼저**(큰 재설계 전 CF vs LLM-with-library 검증); 공개 보유게임 크롤 가능(배포 입력); **플레이타임 가중 반영**("평균보다 오래 한 게임 = 그 류 선호"); **모든 고민 로그화 + 메모리 규칙화**.

**메타 교훈(이 여정의 산물):** 2026년 프론티어 LLM은 게임 추천에서 압도적 베이스라인. 커스텀 시스템이 LLM을 이기는 공간은 좁음 — (a) 개인 히스토리 기반 개인화, (b) long-tail 행동 데이터, (c) freshness, (d) 운영 니치(통제 카탈로그·결정성·대규모 비용). 이 "어디서 이기는지를 실험으로 좁혀가는 과정" 자체가 이 프로젝트의 핵심 가치.

---

## 1. 다음 단계: 작은 개인화 실증 실험 (진행 중)
**가설:** 전체 라이브러리 + 120만 유저 CF(플레이타임 가중) 개인화가, "LLM에 내 라이브러리 주고 추천받기" 베이스라인을 hold-out 정답에서 이긴다.
**설계:** 실제 유저의 liked를 profile/hold-out 분할, leave-user-out CF vs LLM-with-library vs popularity, recall/ndcg vs hold-out, 인기-debias + long-tail 슬라이스, CI + paired.
**결정규칙(사전등록):** CF>LLM(paired CI 0 제외)→재설계 진행 / CI 0 포함→"LLM에 라이브러리 주는 게 답", 보류 / long-tail에서만 이기면 좁은 niche moat로 기록.
(결과는 실행 후 이 아래에 추가.)


## (실행) 개인화 hold-out 결과 — run `pers_smoke`
- 왜: §1 가설(전체 라이브러리 CF > LLM-with-library)의 첫 소표본 스모크 — 파이프라인·지표 동작 점검용.
- 12 users. recall@20: CF=0.139, LLM=0.000, POP=0.111, ORACLE=1.000
- 상세: outputs/experiments/pers_smoke/report.md


## (실행) 개인화 hold-out 결과 — run `personalization_full`
- 왜: §1 사전등록 결정시험 본런 — CF>LLM(paired CI가 0 제외)이면 개인화 재설계 진행, 포함이면 보류.
- 78 users. recall@20: CF=0.293, LLM=0.173, POP=0.034, ORACLE=1.000
- CF−LLM recall@20 = +0.120 [+0.049,+0.192] (유의); LLM pool-miss 4.7%
- 상세: outputs/experiments/personalization_full/report.md

## (정리) outputs/experiments 목적별 폴더 정리 — 갈아엎기 전 단계
- 동기: 사용자 "제대로 갈아엎기 전에 목적별로 폴더·파일 깔끔히 정리". 40개 평면 파일 → 5개 목적 하위폴더(01_similar_eval / 02_vibe_walign / 03_decisive_tags_vs_llm / 04_paradigm_vs_llm / 05_personalization) + _workflow_scripts. 마스터 3종(INDEX/registry/DELIBERATION_LOG)은 최상위 유지. 구조 지도 README.md 추가.
- 결정: **Python 코드(orchestration/·evaluation/)는 이번에 안 옮김** — 임박한 "재설계"에서 코드 구조가 다시 바뀌므로 지금 모듈 이동은 경로 수술+재작업 낭비. 코드 그룹화는 재설계와 함께.
- 주의(기록): 산출물 이동으로 완료된 judge 체인 스크립트(vibe/decisive/paradigm/gem)는 옛 평면경로를 읽어 재실행 시 경로 불일치(이미 끝난 증거라 무방). keeper(personalization/experiment/masked_tag)는 영향 없음.


## (실행) 개인화 hold-out 결과 — run `_pathcheck`
- 왜: (정리·2) 실험을 outputs/→experiments/로 이동한 뒤, 새 경로로 기록·재생성이 정상인지 검증하는 점검 run.
- 6 users. recall@20: CF=0.333, LLM=0.000, POP=0.083, ORACLE=1.000
- 상세: experiments/_pathcheck/report.md

## (정리·2) 실험을 outputs/ 밖 최상위 experiments/ 로 이동
- 사용자 지적: "실험이 왜 outputs 안에 있나, 이것부터 이상". 타당 — outputs/는 build_offline 재생성 파이프라인 산출물용 + .gitignore 대상. 실험은 재생성 불가 연구 증거(리포트/심판/로그/HTML)라 outputs/에 두면 안 됨.
- 조치: outputs/experiments → 최상위 experiments/ (PowerShell Move-Item; git-bash mv는 'device busy'). 코드 11개 파일의 EXP/출력 경로 `"outputs"/"experiments"` → `"experiments"` 일괄 수정(sed), docstring/문자열 3곳 포함. keeper(personalization, --no-llm 6명)로 새 경로 기록 검증 후 정리.
- .gitignore: experiments/는 추적(증거), 단 큰 캐시 experiments/**/game_desc_vecs.npy(~122MB)는 제외. 메모리 2건 경로 참조도 experiments/로 갱신.

## (정리·3) 루트 문서/정보성 폴더를 docs/로 통합
- 사용자 지적: "정보성 폴더들끼리 묶거나 통합, 루트가 난잡". 조치: INTENT.md·ISSUES.md·README_PIPELINE.md(루트 흩어진 문서) + portfolio/(발표자료) → docs/ 아래로. 진입점 README.md만 루트 유지.
- 안전: 코드 참조 0(pyproject도 무관). 고친 건 README.md 링크 4종(→docs/...) + 디렉터리 트리 + .gitignore(portfolio/→docs/portfolio/). 옮긴 3문서끼리의 링크는 같은 폴더 동반 이동이라 그대로 유효.
- 결과: 루트 .md = README.md 1개. 루트 폴더 = config/ data_collection/ docs/ experiments/ outputs/ pipeline/ prompts/ scripts/ serving/ tests/ (+ 빌드/환경: .venv .pytest_cache egg-info = gitignore). 코드 폴더(pipeline/serving/...) 목적별 그룹화는 다음 "재설계"에서.

## (재설계 Phase A) CF를 프로덕션 도구로 패키징 — 완료
- `pipeline/game_rec/agent/cf_recommender.py`: 전체 유저(10.3만)로 co-occurrence(8450 items, nnz 912,868) 빌드 → `serving/data/cf/` 아티팩트. CFRecommender.recommend(library_pt, k) = 플레이타임 가중 conditional-cosine CF.
- 검증: selftest recall@20=0.317 (실험 0.293↑, 전체빌드 누설 감안 정상) → 검증된 moat 방법 재현 확인.
- 다음: Phase B 도구층(constraint_filter/quality_gate/played_filter/cf_rank wrapper) → 비-agentic 베이스라인 구성 가능.

## (재설계 Phase B) 도구층 — 핵심 완료
- `pipeline/game_rec/agent/tools.py`: CatalogMeta(steam_appdetails 메타) + constraint_filter(coop/multiplayer/korean/free/max_price/released_after) + quality_gate(metacritic/niche) + played_filter. cf_rank = CFRecommender.recommend(Phase A).
- 검증: 제약 커버리지 인벤토리 일치(co-op 2103, korean 2999, ≤$10 6157).
- 이제 비-agentic 베이스라인(library→cf_rank→constraint_filter→played) 구성 가능. freshness_verify(라이브 Steam)·library_tool(GetOwnedGames)은 서빙(Phase E)으로 연기.
- 다음: Phase C(에이전트 그래프: router+critic+refine+메모리) + Phase D(검증 게이트: agentic vs 비-agentic 복합쿼리). = 결정적 단계.


## (재설계 Phase D) 에이전트성 검증 — run `agentic_gate`
- 다중주체 min(A,B) recall: non=0.011 vs agentic=0.031; Δ=+0.019 [+0.000,+0.044] (ns).
- 친구(B) recall Δ=+0.092 (SIG). 과제약 완결성 non=0.42 vs agt=0.98.
- 결정: SIMPLIFY → single-pass (agentic 미입증). 상세: experiments/agentic_gate/report.md

## (재설계 Phase D 해석) 에이전트성 = 조건부 정당
- strict 게이트(다중주체 min-recall 유의)는 경계 미통과(Δ+0.019, CI 하단 0.000) → 사전등록 준수해 "보편 agentic 미입증"으로 기록(골대 안 옮김).
- 그러나 agentic이 단일패스가 *구조적으로 못 하는* 것을 실증: 친구(B) recall +0.092(유의), 과제약 완결성 0.98 vs 0.42(단, 부드러운 제약완화 트레이드오프).
- 결론: **agentic은 보편 래퍼로는 미정당, 복합/다중주체/과제약에서만 정당** → 우리 라우팅 설계(단순=단일패스/CF, 복합=agentic) 검증. "필요한 곳에만 에이전트"가 데이터가 지지하는 정직한 입장.
- 미해결/후속: 다중주체 융합(min-combine이 A를 0.308→0.119로 과하게 깎음 — 균형형 융합이면 strict 게이트 통과 가능성). mixed-intent는 LLM judge 필요(미실시).


## (재설계 Phase D) 에이전트성 검증 — run `agentic_fusion_sweep`
- 다중주체 min(A,B) recall: non=0.011 vs agentic(interleave)=0.108; Δ=+0.097 [+0.053,+0.147] (SIG).
- 친구(B) recall Δ=+0.253 (SIG). 과제약 완결성 non=0.42 vs agt=0.98.
- 결정: KEEP agentic (fusion=interleave). 상세: experiments/agentic_fusion_sweep/report.md

## (재설계 Phase D 보강) 융합 스윕 → interleave가 strict 게이트 통과
- 1차 min-combine은 A를 0.308→0.119로 과하게 깎아 min-recall 경계 ns였음. 융합 4종(min/geomean/balanced/interleave) 객관 스윕.
- **interleave**(각 유저 개인화 top 라운드로빈)가 최선: min(A,B)=0.108 vs 단일패스 0.011, Δ+0.097 [+0.053,+0.147] **SIG**(A 0.231 유지, 친구 B 0.028→0.281). geomean/balanced도 유의, min만 ns.
- **사전등록 strict 게이트 통과 → KEEP agentic(fusion=interleave)**. 지표 불변, 융합(시스템) 개선으로 통과(골대 안 옮김 = 정직한 "보강 후 재검").
- 확정: 에이전트 오케스트레이션은 복합/다중주체/과제약에서 단일패스를 유의하게 능가(과제약 완결성 0.98 vs 0.42도). 단순 요청엔 과함 → 조건부 라우팅이 정답. Agentic 기본 fusion=interleave로 설정됨.
- 남은 보강(선택): mixed-intent LLM judge(Gemini+Claude)로 "복합 의도 품질"까지 보면 더 완전. 미실시.


## (데이터 스케일링) 유저 수 축 — run `datascaling_users`
- 왜: 데이터 레버를 축별로 분해 — "유저 수"를 늘리면 CF recall이 오르는지(라이브러리 풍부도 축과 분리해) 측정.
- recall@20 by users: 35350=0.192, 70701=0.246, 106052=0.254, 141403=0.268
- 25→100% Δ=+0.076 (SIG), monotonic=True. 라이브러리 풍부도(GetOwnedGames)는 미측정.

## (재설계 Phase E 코어) agent_graph 완성·검증
- `serving/agent_graph.py`: LangGraph 에이전트 — router(LLM, 요청유형 분류+제약/seed 추출) →conditional→ {library|seed|multi_entity|anonymous} → filter(제약+played) →critic/refine 사이클→ response(LLM 설명). `langchain_core`만 사용(깨진 langchain 메타 회피). `serving/data/cf/` 아티팩트 + CatalogMeta 사용.
- 증거기반 라우팅: 라이브러리/seed/다중주체→CF moat, 익명 vibe→LLM-direct(LLM 우세 영역), 다중주체=interleave 융합.
- end-to-end 검증: "협동·한국어"+라이브러리→library+{coop,multiplayer,korean} 필터→개인화 추천+설명 ✓; "차분한 인디"(무라이브러리)→anonymous LLM-direct→Stardew/GRIS/Coffee Talk ✓; multi_entity interleave ✓; seed-CF ✓.
- 환경: python3에 langgraph+langchain-core 1.4.8+langchain-google-genai 공존 확인(이전 충돌 해소). GetOwnedGames 라이브러리 도구(`agent/steam_library.py`) 작성(서빙 입력+데이터보강 레버) — 라이브 호출은 공개프로필 필요, 오프라인 proxy_library 제공.
- 남은 것: Streamlit UI(steamid 입력+채팅) = 얇은 셸 + 환경 streamlit 설치. 미해결 enhancement: 장르/무드(태그) 제약(현 schema는 coop/price/korean 등 하드제약만; "차분/인디"는 LLM-direct로 우회 중).

## (재설계 Phase E 완료) Streamlit UI
- `serving/main_agent.py`: steamid(GetOwnedGames)/데모 라이브러리 입력 + 친구 라이브러리 + 채팅 + 메모리(played 제외) + route/제약완화 표시. `streamlit run serving/main_agent.py`.
- 검증: streamlit 1.58 설치, 구문 OK, 전 앱 import 해결, agent_graph end-to-end 동작 확인. 라이브 UI는 브라우저 필요(로컬 실행).
- 재설계 A~E 전부 완료: A(CF 도구)·B(도구층)·C(오케스트레이터)·D(검증 게이트: agentic 가치 입증)·E(agent_graph+UI). 기존 pytest 33 불변.

## (데이터 보강 0) 진단 — 측정부터 (read-only)
사용자 요청: "데이터 적인 측면에서 발생하는 문제들 보강". 방법론대로 **고치기 전에 먼저 측정**.
정량 진단 결과(서빙 아티팩트 기준, pool=9956):
1. **라이브러리 캡/희박**: 유저당 좋아요(s≥7, in-pool) max=10, mean=3.05, median=3. **≥8개 보유 유저 단 2.8%, ==10은 0.2%**. → 캡(10)보다 *프로파일 자체가 얇다*는 게 진짜 병목(리뷰 프록시의 한계). GetOwnedGames(수백 개)면 근본 해소 가능.
2. **콜드스타트**: pool 9956 중 CF 공출현 컬럼 미커버 **1506개(15.1%) 추천 불가**. cold 게임 인기백분위 median 0.31(커버=0.55) → cold는 대체로 비인기/꼬리. (주의: P2e — niche≠고품질. 콜드폴백은 품질 게이팅 필요.)
3. **공출현 support 희소**: CF 게임 deg median=9, **deg<10이 50.3%, <30이 71.4%**. 저-support 쌍의 conditional-cosine 추정이 노이즈. shrinkage 후보.
4. **품질신호 커버리지**: metacritic **30.5%**뿐 vs user-score(리뷰 집계) **86.6%**. quality_gate가 metacritic만 보면 70%가 사각.

→ 도출된 보강 4건(D1 콜드폴백, D2 user-score 품질, D3 저support shrinkage, D4 라이브러리 풍부도 레버 입증)과 신규 기능(방향성 스티어링)으로 진행. 각 항목은 사전등록 게이트로 검증·귀무보고.

## (데이터 보강 1) 설계 확정 — 사용자 채택
- 신규 기능 = **방향성 스티어링**: (a) 장르 노벨티 (b) 측면 스티어링.
- **핵심 설계 = 인접 노벨티** (사용자 채택): CF(행동 moat)가 "그래도 좋아할" 검증된 게임 중에서 안 해본 장르/측면을 띄움 → moat 유지하며 방향만 추가(랜덤 신장르·품질붕괴 아님). 콘텐츠 태그 재가중은 검증된 game×tag tag-cosine 사용(W_align 임베딩투영 아님 — P2b/F1에서 패배).
- **호출 = 자연어 채팅** (사용자 채택): router가 의도+측면 태그를 NL에서 추출, critic이 "실제로 그 방향 갔는지" 검증. 가장 agentic, 추가 UI 불필요.
- 공유 인프라: 게임×태그 행렬 기반 콘텐츠 레이어가 D1(콜드폴백)+F(스티어링) 공통 base.

## (데이터 보강 D2) user-score 품질신호 — 검증 후 채택
- 빌드: `build_quality.py` → `serving/data/game_quality.json`. 게임당 Bayesian-shrunk user-score `q=(n·mean+m·gmean)/(n+m)`, m=20, gmean=6.13. 커버 8622/9956 (86.6%).
- **사전 sanity 검증(측정 먼저)**: metacritic 겹치는 2733게임에서 Spearman(user-q, metacritic)=**0.374** (양의 순위상관 — 같은 품질을 본다, 단 redundant 아님). Pearson은 shrinkage 강할수록↑(m0=0.02 noisy→m20=0.23 안정), user-q std 0.43→0.04로 1리뷰 노이즈 제거 확인.
- 채택: quality_gate가 metacritic+user-score 둘 다 drop-filter로. 신호 없으면 keep(보수적). **밀도 효과 실증**: user-score≥p50 게이트는 9956→6577로 실제 작동(metacritic≥75는 8897 유지로 거의 무력 — 70%가 metacritic 없어 통과). quality_pct 신뢰커버(n≥5리뷰) 67.9%.
- 결정: **D2 채택**. 품질 게이팅의 사각(70%)을 메움. D1 콜드폴백·스티어링 품질게이팅에 사용.


## (데이터 보강 D1) 콜드스타트 폴백 — run `coldstart_20260625_013732`
- 커버리지 8604→9956 (콜드 1352 회복, 100% 추천가능).
- recall@20: CF 0.250 vs hybrid 0.253, Δ=+0.0033 (ns).
- underfill 4.0%, 완전콜드프로파일 0명, holdout-cold 0.3%.
- 결론: 커버리지·robustness 확보(설계상 warm 불변). niche 품질게이트 적용. 스티어링 base.


## (데이터 보강 D3) 저-support shrinkage — run `shrinkage_20260625_013858`
- recall@20 by λ: 0=0.2500, 1=0.2500, 3=0.2433, 5=0.2433, 10=0.2500
- best λ=0, **adopt=False** (사전등록: Δ>0 & CI 0 제외 시만). 미채택 → 정직히 드롭(기존 conditional-cosine+min_cooc로 충분).


## (데이터 보강 D4) 라이브러리 풍부도 레버 — run `libraryrichness_20260625_014052`
- recall@20 by profile size: p1=0.0894, p2=0.1294, p3=0.1650, p4=0.1844
- p1→4 Δ=+0.0950 (SIG), monotonic=True, last-step 미포화.
- 결론: 풍부도가 큰 레버 — GetOwnedGames 입력 정당. 실현 평균 3.05가 캡(10)보다 진짜 병목.


## (신기능 F검증) 노벨티 스티어링 신장르-recall — run `steering_20260625_014419`
- 22명 신장르 holdout 보유. new-genre recall: cf=0.0000, nov_b1=0.0909, nov_b2=0.1364, nov_b3=0.1818
- **best=nov_b3** (신장르 recall CI>0). overall 트레이드오프: cf=0.203, nov_b1=0.116, nov_b2=0.067, nov_b3=0.048


## (신기능 F검증) 노벨티 스티어링 신장르-recall — run `steering_large`
- 153명 신장르 holdout 보유. new-genre recall: cf=0.0098, nov_b1=0.0784, nov_b2=0.1209, nov_b3=0.1209
- **best=nov_b2** (신장르 recall CI>0). overall 트레이드오프: cf=0.220, nov_b1=0.142, nov_b2=0.089, nov_b3=0.061

## (신기능 F) 방향성 스티어링 — 구현·검증 완료
**설계**: HybridRecommender.recommend_steered = CF(행동 moat) base를 콘텐츠 태그로 재가중(인접 노벨티). novelty=1-taste코사인(content mode, 판별력↑), aspect=요청 태그 강도. 품질 게이트(user-score)로 niche≠good 방어. agent_graph에 `explore` 라우트 + steer_node(NL→{novelty_strength, aspect_tags} 추출, β: low1/med2/high2.5). 자연어 호출(사용자 채택).

**검증1 — 신장르 holdout recall (비순환, n=102 신장르유저)**: plain CF의 신장르 recall = **0.0098**(거의 0 = 필터버블 구조적 실패 확인). 노벨티 스티어 b1=0.078(Δ+0.069 SIG), b2=0.121(Δ+0.111 SIG), b3=0.121(Δ+0.111 SIG) — 전 β CI>0. **트레이드오프 정직 보고**: overall recall 0.220→(b1)0.142→(b2)0.089. b3는 b2와 신장르 동일·overall만 손해 → dominated. 결론: 스티어링은 유저 본인 분기행동을 CF가 못 하는 방식으로 회복 → **명시적 탐색 모드로 정당**(기본값 아님).

**검증2 — blinded Claude judge (12케이스×3, A/B 블라인드)**: 스티어 리스트 **win-rate 1.000 [1.000,1.000]** (novelty 6/6, aspect 6/6, 36/36표 만장일치), quality_ok 1.0. 판정은 스티어 vs 자기 CF-baseline 비교라 P2e familiarity-bias 중립화. judge들이 "baseline은 라이브러리 장르만 반복 → branch-out 요청에 부적합"을 정확히 지적. 측면 케이스도 요청 태그(story/atmospheric/combat/open-world)를 강하게 반영.

**종합**: 데이터(비순환 recall) + 인식(blinded judge) 양쪽에서 스티어링 가치 입증. CF가 구조적으로 0인 신장르 발굴을 에이전트(LLM 의도해석 + CF도구 + 콘텐츠 재가중)가 해냄 = bare-LLM도 bare-CF도 못 하는 영역. 단 n(12 judge / 102 recall) 보수적, overall 트레이드오프 명시.

## (서빙 보강) seed 라우트 다국어 매칭 + UI
- 통합 회귀 테스트 중 발견: seed 라우트가 "다크소울 같은 거"에 0건(LLM이 한국어 'Dark Souls'를 영어 카탈로그와 exact-match 못 함). 기존 한계(내 변경 아님).
- 수정: router가 seed_titles를 **공식 영어 제목**으로 출력 + seed_node에 fuzzy(substring, 인기순) 매칭. → "다크소울"→DARK SOULS REMASTERED/ELDEN RING/Sekiro 정상 co-play 추천.
- UI(main_agent.py): 탐색 모드 안내 캡션 + chat 예시 추가, 라우트/스티어(새장르·측면) meta 표시. pytest 52 통과 유지.

## (서빙 보강 2) seed 라우트 — 시리즈 멀티시드 + 프랜차이즈 제외
- 사용자 지적: "다크소울 시리즈가 여러개잖아". 확인 결과 (1) 부분일치 5개 중 인기 1개(III)만 seed로 쓰고 (2) 나머지 시리즈가 결과에 다시 노출(seed 1개만 제외)되는 문제.
- 수정(사용자 OK): `_match_titles`가 **시리즈 전체**를 반환(부분일치 + `_series_prefix` 단어경계 확장) → 전부 seed로 + 명명한 프랜차이즈 통째로 결과 제외. "~같은 거"=유사 *다른* 게임 의도.
- 결과: 다크소울→Dark Souls 5종 제외→ELDEN RING/Sekiro/Lies of P/CODE VEIN; 위쳐3→위쳐 1/2/3 제외→Kingdom Come/Cyberpunk; 엘든링→Elden Ring만 제외(Dark Souls III는 유사작으로 정상).
- **정직한 한계**: 프랜차이즈 ID 없음 → 어순 다른 스핀오프(Lightning Returns: FF XIII, Thronebreaker: The Witcher Tales)는 가끔 누출. 완벽화는 프랜차이즈 DB 또는 요청당 LLM 호출(토큰 낭비) 필요 → 공짜·결정론 휴리스틱 유지가 합리적. pytest 52 통과.


## (b) 라이브러리 풍부도 LIVE 입증 — 실제 GetOwnedGames — run `libraryrichness_live_20260625_031928`
- 129명 실제 공개프로필(중앙값 프로파일풀 78게임). recall@20 by p: p1=0.0352, p3=0.0555, p5=0.0639, p10=0.0822, p20=0.1086, p30=0.1233
- crawl-realistic p3(0.056)→p30(0.123) Δ=+0.0678 (SIG), last-step 미포화, monotonic=True.
- 결론: 오프라인 D4의 풍부도 레버가 **실데이터로 확정**. GetOwnedGames 입력 정당(모델 변경 0).


## (랭커 벤치마크) CF vs EASE vs ALS — run `rankerbench_main`
- recall@20: pop=0.0783, cf=0.2033, ease=0.2000, als=0.1742
- winner=cf. Δrecall vs CF: pop=-0.1250(SIG), ease=-0.0033(ns), als=-0.0292(ns)
- 해석: EASE 대비 위치 = 전통 recsys 대비 보수적 하한. 이기는 랭커를 에이전트 밑에 채택(교체 가능).


## (Pillar 2 데이터 인프라) 최종 SQLite 스키마 — 무손실·정규화·3-phase
**문제틀(사용자)**: "정보는 절대 누락 금지(모든 필드 포함). 고민할 건 *무엇을 담느냐*가 아니라 DB **구조**(어떻게 무손실+컴팩트하게) + **타이밍**(어느 phase에서 가장 싸게)뿐. 구 데이터는 목표가 달라 한 줄도 재사용 안 함 → wipe 후 신스키마로 새로 크롤."

**고민1 — 페이싱 버그(사용자 지적)**: 구 크롤러는 호출 *뒤* sleep(1.0) → 실간격=RTT+sleep≈1.3s(~0.77/s, 공칭 1/s 아님) → 일일 ~60~66k만 소진(90k 미달). 수정: **월-클록 페이싱** sleep=max(0,target−경과). reserve()=하드캡(타이밍무관)과 페이싱=throughput평활은 분리. 과거 429폭주는 일일캡 아닌 **버스트한도** → AIMD(429×1.7, 성공streak×0.9)+서킷브레이커가 담당. 결정: target~1.0s(예산최대화 ~86k/day).

**고민2 — 업적 저장(최대 테이블 ~수백만~천만 행)**: 자연키(steamid,appid,apiname TEXT) vs 인터닝(ach_id INT). 둘 다 무손실. apiname(~25B)이 수백만 반복 → 인터닝 시 ach_id(INT)로 ~3x↓. 읽을 때 game_achievement 조인 필요하나 *희귀도/조건은 어차피 차원에만 있어 조인 불가피* → 인터닝이 추가 부담 거의 0. **결정: 인터닝.** game_achievement(ach_id PK, appid, apiname, display_name, description, hidden, global_pct)에 이름/조건/희귀도 1부씩.

**고민3 — 무손실 보험**: 미컬럼화 가변필드(스크린샷/영상/요구사양)까지 raw_json 블롭 vs 컬럼만. 사용자 판단: "비신호 + 게임단위라 <1일 재크롤 복원 가능" → **결정: 컬럼만(raw_json 미사용).** 모든 *신호* 필드는 빠짐없이 컬럼화. (per-게임 차원은 distinct ~수만개로 바운드.)

**구조(스타스키마)**: steamid/gid INTEGER(64bit<2^63 무손실, TEXT 대비 ~3x↓). facts(owned/user_achievement/...) vs dimension(game_achievement/games/steamspy). 무손실복원: `user_achievement ⋈ game_achievement(ach_id) ⋈ games(appid)` → "유저X가 [게임명]에서 [업적명](조건:…, 글로벌Q%)를 T에 해금". player_game_ach(unlocked=0,total=N)으로 "플레이했으나 0해금"(disengagement) 명시 보존.

**타이밍(3-phase 라운드로빈, 각 데이터 최저비용 지점에서 1회)**:
- users: 게임명 **공짜**(include_appinfo=1) + 업적콜 **has_community_visible_stats 게이팅**(업적없는 게임 스킵 ~40%절감). GetBadges 1콜로 level+xp+뱃지(GetSteamLevel 대체). 업적은 해금 apiname+unlocktime만(인터닝). 트랜지언트(non-200)는 pending 유지(false-private 버그 수정). 친구→스노볼 enqueue.
- games: distinct owned appid당 1회. appdetails/steamspy/**GetSchemaForGame(이름·조건)**/GlobalAchPct(희귀도)/CurrentPlayers(CCU). games.fetched_at=방문마커(부분방문 resume는 sub-step has_* 가드).
- reviews(opt-in 최저우선): appreviews 페이지네이션(author 귀속, per-user 리뷰 API 부재). page-cap으로 1게임 예산독점 방지.

**예산 강화**: reserve를 HTTP attempt마다(429 재시도도 카운트) → 100k 하드캡 under-count 불가(구 코드는 get당 1예약이라 재시도 누락 위험).
**검증**: db.py 스모크 통과(20테이블, reserve 5/5, 인터닝 ACH_A→1, lossless join 'First Blood'/'Win a round'/1.3%/unlocktime 재구성). 단기 라이브크롤(--limit 400)로 실데이터 end-to-end 확인(→ 아래 '(Pillar 2 검증) 큐 순서 버그' 항목에서 발견·수정·재검).

**리뷰 phase 제거(사용자 결정)**: 스팀에 per-user 리뷰 이력 API 없음(appreviews=게임별 귀속만, 열거 불가) → "유저별 리뷰" 의도 충족 불가 + voted_up은 playtime과 중복(저가치). reviews/review_progress 테이블·코드 전부 제거(17테이블). 시드는 구 CSV steamid 부트스트랩(셔플)+친구 스노볼 유지(랜덤 accountID+GetPlayerSummaries 벌크 스크리닝도 검토했으나 CSV가 적중률↑·구현단순으로 채택). 랜덤발견은 향후 시드 고갈 시 옵션.

## (Pillar 2 확장 논의) 코호트 편향 — 측정·증분보정 전략 (사용자 문답)
**문제제기(사용자)**: 시드 steamid가 "특정 게임 리뷰"에서 뽑힌 거라 편향 아닐까?
**측정**: `user_game_scores.csv` = 1.19M행, distinct steamid 171,227, **distinct 게임 44,313**. top1=0.7%/top10=4.6%/top100=20.4%(소수집중 아님, 긴 꼬리). 상위 게임 장르 다양(HELLDIVERS2 슈터/BG3 CRPG/CS2 FPS/Elden Ring ARPG/Terraria 샌드박스/Cyberpunk RPG/TF2/Stardew 시뮬/Clair Obscur 턴제) → **genre-selection 편향은 약함**.
**잔존 편향(정직)**: (1) 인기/최신 편향(상위가 히트작·RPG多 → 니치/구작/비영어 게임 공동출현 희박), (2) "리뷰 작성자" 편향(몰입·의견·영어권↑), (3) **방법론 핵심**: train·평가 hold-out이 같은 코호트면 편향을 *공유*해 인-코호트 지표로는 일반화 실패가 안 보임.
**전략**: 시드는 CSV(넓음+적중률↑)+스노볼 유지. P2d에서 **랜덤 accountID OOD hold-out**(genre편향 0)으로 CF recall을 인-코호트 vs 랜덤 비교 → 편향을 *정량화*. 
- "편향이 측정되면 처음부터?" → **아니오**: steam.db는 append-only, CF아티팩트는 오프라인 재빌드(API 0). 보정=유저 증분추가 or 재가중(데이터 0) or 수용+보고. 재시작 강제는 스키마/필드 오류뿐(이미 닫음).
- "얼마나 필요한지 모름?" → **포화곡선으로 멈춤**(b-검증과 동일 방법: recall vs N, 기울기 평평→정지). 타깃 가능(과소커버 게임=유한 목록의 소유자만), 메터링(≤90k/day), 재가중은 데이터0, 또는 갭 작으면 그냥 보고(자기비판적 평가가 산출물). 곡선의 기울기를 *읽으며* 멈추는 것이지 총량을 추측하지 않음.
**시드 대안(기록)**: 랜덤 accountID(=76561197960265728+random) → GetPlayerSummaries 벌크100 스크리닝(communityvisibilitystate=3만 적재; persona/country 미저장) → 큐. 한계: state=3여도 "게임 세부" 별도 비공개 가능(최종판정 GetOwnedGames), 랜덤=균일인구라 휴면多·적중률↓·라이브러리 얇음(CF 신호밀도↓). 스노볼이 동질성으로 활성층 끌어올려 상쇄하나 스노볼 자체는 연결성분 편향. → 시드고갈/대표성 필요 시 꺼낼 카드.

## (Pillar 2 검증) 큐 순서 버그 발견·수정 + 실데이터 end-to-end 확인
**왜 적나**: 위 스키마 항목이 "확인 중"에서 멈춰 있어, 검증 중 실제로 발견·수정한 버그와 최종 결과를 기록(행동마다 이유).
**버그 발견**: 단기 라이브크롤에서 첫 유저 5명이 전부 playtime 0 / 4명 비공개로 나옴 → 의심. 진단(GetOwnedGames 직접 호출)으로 **파싱 버그 아님** 확인(include_appinfo 0/1 결과 동일). 진짜 원인 = **시드 순서**: `user_queue(steamid INTEGER PRIMARY KEY)`가 steamid를 rowid 별칭으로 만들어 `ORDER BY rowid`가 **steamid 오름차순(=가장 오래된/비공개 많은 계정 먼저)** 으로 크롤되고 있었음.
**수정**: `seq INTEGER PRIMARY KEY AUTOINCREMENT`로 삽입순서를 steamid와 분리 + 부트스트랩 **시드 셔플 복원**(리뷰 CSV는 게임별로 묶여 편향 → 셔플로 대표성↑). 재크롤 시 첫 유저가 정상 활성계정(level 32, max playtime 21,250)으로 바뀌고 첫 유저부터 업적 발화.
**최종 검증(실데이터)**: lossless 3중 조인으로 "유저→게임명→업적명/조건/희귀도/시점" 재구성 성공(예: DEFCON의 'Diplomat', 글로벌 1.4%, unlocktime). player_game_ach의 "0해금"(이탈) 행 포착, has_stats 게이팅 동작(업적없는 게임 스킵), throttle_hits=0 @ ~0.7s. db.py 17테이블 스모크 통과(reserve 5/5, 인터닝, lossless join).

## (Pillar 2 후반 결정 묶음) 스노볼·업적·ETA·포워드 로드맵·핸드오프 — 누락분 보강
*세션 후반에 즉시 안 적은 결정들을 한 번에 기록(always-log 원칙 위반 교정).*

**스노볼 cadence = A(휴면) 채택**: 친구는 크롤 시 user_queue에 depth+1로 enqueue되나, `next_pending_users`가 depth 오름차순이라 **depth0(CSV 171k)을 다 끝낸 뒤에야 친구 차례**. 목표 10k는 CSV 안에서 채워지므로 **스프린트 내 스노볼 미발동**. 친구 *관계* 데이터는 저장됨. CSV(171k 리뷰작성자, 44k 게임 다양)로 충분 + 스노볼은 connected-sample 편향 추가 → 휴면이 맞고, 다양성/편향은 P6의 랜덤 OOD로 측정. 인터리브(B)는 시드 고갈/연결망 확장 필요 시.

**업적 무조건 크롤 ON (사용자 결정) + 이유**: 스팀은 평점 점수 없음(추천/비추천) + 리뷰 드롭 → liked/선호를 행동으로 정의해야 하는데 **playtime만으론 무딤**(고수-빠른클리어 / AFK-방치 / 사놓고-안함 구분 불가). 업적(완료율·희귀도)이 그 점수 공백을 메우는 유일한 추가 신호 → 선택 아니라 필수. 캡 안 함(짧은-playtime이 업적이 가장 값진 구간이라 top-N 캡은 그 신호를 잃음).

**콜 경제·ETA 정직 정정**: owned=유저당 **1콜**(벌크), 업적만 게임당 1콜인데 **플레이≥10분 & has_stats 게임만**(287개 보유 유저도 안 한 107개는 스킵). 실측 헤비유저 1명 ≈ **154콜**(57은 크롤 도중 스냅샷). 내 초기 "유효유저당 ~45콜→10k 5일"은 **낙관적 오류** → 실제 ~150콜/헤비유저면 90k/day ÷ ~150 ≈ ~600/day → **10k ETA ~10–16일**(며칠 아님). 측정값(2026-06-26 ~36명)으로 갱신. → `--stop-at-users` 게이트(최소 5k=빌드밀도+검정력 / 권장 10k)로 무한 크롤 방지.

**데이터 전환 → 추천 "방식" 재배선 필연(포워드 로드맵)**: 구 스택은 리뷰점수(`s_round10_rec`)에 묶임. 새 데이터엔 점수 없음 → CF "liked"·품질 게이트 출처·카탈로그/태그/인기/제목을 전부 steam.db에서 재유도해야 함. **CF 수식(공출현 conditional-cosine + 플레이타임 가중)은 유지.** 로드맵: P4 행동 liked 정의(게이트, 구 리뷰-CF recall 재현/상회 사전등록 검증)→P5 빌더 재배선+아티팩트 재생성→P6 평가 재실행+랜덤 OOD 편향(포화곡선 정지)→P7 업적 가중모델(사전등록, 할지 포함)→P8 서빙 갱신. 상세는 `docs/ROADMAP.md`.

**작업 모델(사용자 지적)**: 각 Pillar가 독립 플랜 규모 → **한 로드맵 파일에 세부 결정 욱여넣지 말고, Pillar마다 착수 시 전용 상세 플랜(리서치→선택지→사용자와 결정→실행).** 상위 플랜은 순서·목표·의존·"결정할 것"만.

**코호트 편향 후속(보강)**: "편향 측정되면 처음부터?" → 아니오. steam.db append-only + 아티팩트 오프라인 재빌드라 **증분 보정**(유저 추가 or 재가중(데이터0) or 수용+보고). "얼마나 필요?" → 모르니 **포화곡선으로 멈춤**(recall vs N 기울기 평평). 재시작 강제는 스키마 오류뿐(이미 닫음).

**세션 핸드오프 + 새 행동규칙**: 컨텍스트만 리셋하고 이어가게 `docs/ROADMAP.md`(시작점) + README 현행화 + 메모리 정리. **새 최우선 행동규칙 추가**: 방식 추천 시 항상 최악경우·단점·놓칠점·대안 약점을 깊이 고민하고 그래도 나은 이유까지 제시(아니면 추천 변경). 행동규칙을 메모리 최우선 그룹으로.


## (정정) steering_large 신장르 유저 수 n=102 → n=153
- 위 "(신기능 F) 방향성 스티어링" 절(:182, :186)의 "n=102 신장르유저"는 **오기**. 참값 **n=153**.
- 근거: steering_large/aggregate.json(`n_newgenre_users:153`, 모든 newgenre·diff stat `"n":153`), egistry.jsonl, 코드 pipeline/orchestration/steering_eval.py:138(n_newgenre_users 카운트) 및 자동생성 steering_large/report.md("153 have >=1 NEW-genre")·이 로그 자동엔트리(:176 "153명 신장르 holdout") — 전부 153.
- 오기 추정 원인: cf 신장르 recall = 0.00980392 = 1.5/153 인데 우연히 1/102 와 동일 → recall 에서 n 을 1/recall 로 역산하다 102 로 기재. recall·CI·판정·결론은 영향 없음(전부 153 기반).
- 함께 정정(in-place): experiments/05_personalization/steering_judge_report.md, docs/technical_reference.html(2곳). append-only 원칙상 본문 :182/:186 은 보존하고 여기에 정정 기록.

## (2026-06-30) 행동 방식의 신호밀도 측정 — P4는 현재 ~1.2k 유저로도 착수 가능 + 풀/P7 확정 + 문서 현행화
**왜 적나**: 크롤 작업 정리 중 내가 "1,166명은 10k 목표 대비 초기라 P4 이르다"로 프레이밍하자 사용자가 반박 — (1) 새 행동 크롤은 옛 리뷰 방식과 *방식이 달라* ~1,000명으로도 P4 이상 분석이 유의하다, (2) 풀은 무조건 확장, (3) P7도 무조건 한다(업적까지 긁는 이유). 측정으로 검증하고 결정·정본 문서에 반영.

**측정(steam.db, 06-30)**: 공개유저 ~1,210에서 owned/유저 **중앙값 214**(p90 910·mean 412·max 8,543), playtime>0 중앙값 134, **playtime≥120분(=liked 후보) 중앙값 89/유저**(mean 147.6), 업적 보유 유저 1,079. 결정타 — **co-play 쌍 관측치 ≈ 9,180만**(Σ C(played,2)). 옛 리뷰 방식(유저당 ~10건)이면 같은 1,200명에서 co-play 쌍 ~5만 → **동일 인원에서 ~1,700배 신호밀도**. ∴ CF/P4의 분석단위는 *유저 수*가 아니라 *co-play 쌍·(유저,게임,playtime,업적) 행*이며 그 행은 이미 풍부.

**결정1 — P4 게이트 충족, 본분석 착수 가능**: ROADMAP P4 의존 "수천+"는 이미 충족. 개인화 moat도 78 테스트유저(얇은 프로파일)에서 SIG였으므로 조밀한 ~1.2k면 leave-user-out CF 본분석 검정력 충분. 5k/10k 목표는 *꼬리(long-tail) 커버·OOD 검정력*용이지 P4 주효과용이 아님 → 크롤은 P9로 계속(꼬리커버 + 나중 OOD 표본 확보).

**결정2 — 코호트 편향은 인원수와 직교(중요)**: 같은 시드(리뷰작성자 + 공개프로필only + has_stats 게이트)에서 *더 많이/더 조밀하게* 긁어도 편향은 그대로 — 편향은 **다르게 표집**(랜덤 accountID OOD hold-out, 이미 P6 계획 :239)으로만 해소되지 인원수·풍부도로는 안 됨. 함의: P4 liked 임계는 몰입코호트 skew에 강건하도록 **유저상대(median비율/백분위) > 절대시간**.

**문서 반영(사용자 상시 규칙 "대화하며 문서 항상 업데이트, 절대적으로 따라")**: ROADMAP — `[P7]`→`P7`·"할지 포함"→"필수"(수행 확정, 학습형 vs 고정 비교만 오픈), "풀 9956 유지 vs 확장"→"확장 확정(현 ~30.6k)", 크롤 현황 ~29명/ETA10–16일 → ~1,166/ETA 3–5주 + ops 경고(`--stop-at-users` 미설정·워치독 없음 20h 무가동). 새 행동규칙 메모리 [[keep-docs-current]] 추가. 참고: 업적=필수·OOD 계획은 본 로그·메모리엔 이미 있었으나 ROADMAP 상위표기로 전파 안 돼 있었던 게 갭의 원인.

## (2026-07-02) 크롤 2번째 무가동(~32h) 발견 → 재기동 + games(희소 메타) 백로그 측정
**왜 적나**: 사용자 "게임 크롤 희소한거 채우는 거 돌리고 있어봐" → 생존 점검하니 크롤이 죽어 있었음. 재기동 경위·백로그 수치·로그 인코딩 함정을 기록.
- **무가동**: 마지막 로그 = 07-01 08:23 "BUDGET EXHAUSTED today (spent=90000)" 후 침묵 + python 프로세스 0 → **~32h 다운**(06-28~29 ~20h에 이어 2회째). `--forever`면 UTC 자정 예산 리셋 후 재개 로그가 있어야 하므로 프로세스 자체가 죽은 것(원인 미상 — 재부팅/절전 추정). 워치독 부재 리스크 재확인(ROADMAP ⚠️ 그대로 유효).
- **재기동**: `scripts\daily_crawl.bat`를 detached로 실행(문서된 재개 절차, steam.db에서 이어받아 손실 0). 07-02 16:21 기동 로그 확인 — phases=['users','games'], pending=234,658, today_spent=0.
- **"희소 채우기" = games 페이즈**: distinct owned appid 40,611 중 games 차원(appdetails·SteamSpy·업적스키마·글로벌희귀도·CCU) 방문 11,775, **백로그 28,836(71%)**. 별도 games-only 런이 아니라 통합 크롤의 라운드로빈(users 20 : games 60/사이클)으로 채워짐 — users 진행(1,669/10k)도 같이 감. 관측 페이스 ~2.3k게임/일 → 백로그 소진 대략 1~2주(신규 유저가 새 appid를 계속 추가하므로 완전 0은 아님). 더 빨리 비우려면 `--phases games` 전용 런(하루 예산 전부 games, ~1일 소진)이 카드지만 그날 users가 멈추므로 기본값으로 안 함.
- **로그 인코딩 함정(기록용)**: `crawl_daily.log` 앞부분이 과거 PowerShell 리다이렉트로 UTF-16(BOM)이 됐고, 이후 cmd가 UTF-8로 append한 구간은 뷰어에서 바이트-스왑 mojibake로 보임. **데이터는 정상**(구간별 utf-16/utf-8로 디코딩 가능) — 파일 손상 아님, 읽기 문제.

**후속(같은 날 16:49) — 사용자 결정으로 games-only 전환**: "게임이 너무 희소해서 실험 불가 → 일단 게임만 다 채워라"(명시 OK로 기존 런 중지 승인). 라운드로빈(1~2주 소요) 대신 **`--phases games` 전용 런**으로 전환 — 하루 예산 전부 games에 투입. 산수: 백로그 28,836 × 게임당 ≤5콜 ≈ ~144k콜; 오늘 잔여 ~88.6k + UTC 자정(KST 09시) 리셋 후 ~55k → **ETA ~07-03 밤**(쓰로틀 감안 07-04 새벽). 전환은 재개형이라 손실 0(games.fetched_at 마지막 스탬프 = 중단분 자동 재시도). 유저 크롤(1,669/10k)은 그동안 일시정지 — 트레이드오프 사용자 인지. 소진 후 `daily_crawl.bat` 복귀 예정. 세션에 프로세스 워치독 + 백로그-0 알림 걸어둠. 맥락: 이 백로그가 실험을 막는 이유 = P5 재배선의 카탈로그/태그/품질(games·steamspy 테이블)이 games 차원에서 나오는데 71%가 미수집이라 행동-CF 실험(P4)에 붙일 메타가 없음.

## (P4 플랜 확정 — 2026-07-03) 행동 선호 shortlisting 진화 탐색: 결정 요약 + 자율 운행 개시
*플랜모드 왕복(07-01~03)에서 확정한 것들의 서사 증류. 상세 = 플랜파일(recursive-dreaming-moore.md), 실행 저널 = `experiments/p4_sweep/JOURNAL.md`(신설).*

**성격 재정의(사용자)**: P4 = "최종 선택"이 아니라 **shortlisting** — 편향 코호트(1,669 리뷰작성자)에서 유망 후보를 추리고 최종 확정은 de-biased(랜덤-accountID OOD, P6) 재실험에서. winner's curse는 그 재실험이 confirmation → 무거운 사전등록 불필요. 방법 고정 없이 **진화 탐색**(순위→"왜 이겼나"→특성 살린 새 후보; LLM이 목록 밖 생성·DL/통계/FE 하이브리드), **진 후보 전량 상세 기록**(후보별 식·가설·사망사유 / 라운드별 판단기준·"안 판 방향" — 사용자 감사·부활 가능 수준).

**적합도(유일 고정) 논쟁·결정**: held-out + graded NDCG@20 + IPS/SNIPS 인기-debias. ① 정답지 = 후보식과 무관한 **중립 신호**(각 후보가 자기 liked로 채점받으면 순환 → 비교 불성립) ② relevance = raw playtime ✗, **per-game 오너 백분위**(사용자: "스토리 게임은 사랑해도 다회차 안 함" → raw면 MMO 상시 우위 장르 confound; 명시적 게임타입 분기는 기각 — per-game 분포가 타입을 자동 흡수, 통일 원리 "게임 간 차이는 per-game 정규화가 흡수") ③ **RMSE 기각**(평점예측 지표) ④ masked-engagement 보조축(타깃=중립 백분위 — 자기-s 예측이면 상수 s 만점 함정) ⑤ **wishlist 2차 fitness 채택**(date_added 시간분할; 안 가진 게임 = 발굴 사각의 유일 실데이터; 욕망≠즐김 캐비앗) ⑥ 발굴 정답의 내부 합성 시도 전부 기각 — 태그취향벡터(콘텐츠 순환·통째 폐기), 유저 1:K 매칭(CF로 CF 채점), 겹침·빈도가중(순환+인기증폭) — 비순환 발굴검증은 외부 judge(+online)뿐 ⑦ 인과 프레임(MNAR): IPS = "노출 균등했다면" 근사, 한계 명시.

**의도/부정(사용자 캘리브레이션)**: owned 0~10분 = **약한 긍정**(돈 낸 의도 > wishlist), 진짜 부정 = **"즐기다 버림"**(trial 초과 ∧ per-game 하위 백분위 ∧ 완주궤적 없음 ∧ stale — **일괄 2h 금지**: 1~2h 인디 완주 반례), 환불 제외(데이터 진입 전 소멸). 의도 tier 학습 투입 = **기본 제외 + 입증책임 ablation 1개** — 실측 근거: 0분 그래프 top200 동일퍼블리셔 76%·동일시리즈 42%(팩 구조물; "스팀팩은 의도적"[사용자]과 양립 — 문제는 appid 구조), 호더 구배 13%→50%. **부수 발견: played 그래프도 카드-파밍 쇼벨웨어 군집 오염**(오너 완주 중앙값 0.00·2.5~3.5h 균일; 초기 "업적스팸" 추정은 실측 정정) → per-game 코호트 업적통계로 소스 게임 감지[사용자 제안 검증] + per-user 캡 병용.

**업적(fan-out 35후보 + 실측)**: "0-unlock=AFK" 오류(중앙 148분=짧은 체험); 진짜 AFK = 고pt∧0진행 JOINT. 완료율·개수·unlocktime 이미 dense — **크롤 필요한 건 희귀도(global_pct)뿐**(유일한 코호트-독립 축). 6갈래+wrapper `s=s_pt×shrink(κ,calibrate(gate(channel)))`, per-game 업적통계 3용도(파밍감지·난이도·정보량κ) games-크롤 후 전부 실행(사용자 확정).

**탐색 구조**: 선호/랭커 분리(사용자 제안) — Stage A 깔때기(보수적 내재 사전필터 → **CF+RP3β 이중 소패널**[CF가 홀대한 선호의 관문 사망 방지 — 사용자 false-negative 지적] → dev full → top RP3β) / B 랭커 8종 1회전(**EASE = Woodbury 유저수³ = 초 단위, "비싸다" 정정**) / C 소교차. **패자부활전**(내재↑·CF↓ 탈락자를 R*로 재평가) + **재량 랭커 재확인 허용(사용자)**. 매몰 방지(사용자 경고): 탐험 쿼터(15 중 ≥3 타 family)·반대 라운드·"안 판 방향" 강제 기록. F1 dev/private 패널 2중화, F2 앵커 3종(ORACLE/RANDOM-s/POP), F5 소셜 신호 씨앗(friends 46.7k·groups). judge = **Sonnet 서브에이전트**(탐색; Fable 토큰은 루프에 보존) + 결선 Fable 재판정 옵션 + Gemini는 복귀 후만. "누락 가능성 배제 불가"를 정직 인정 — 목표 = 싸게 줄이고(이중관문·부활전·쿼터) 복구 가능하게(탈락자 전량 registry 보존) 잔여 위험 보고 명시.

**풀·크롤·기타(사용자 확정)**: 평가풀 = `type='game'`+미출시 제외+오너 하한 없음(a안). P5 = 최종 확정까지 대기. 유저 크롤 = 백그라운드 필러(P4 분석은 현 1,669명 풀). **rtime 진단 종결: Valve가 3rd-party 키에 rtime_last_played 미반환(파라미터 3종 실증 — 크롤 NULL의 진범, 파싱버그 아님) → 복구 불가, fallback 무작위 70/30(구 프로토콜과 일치 = 비교 일관성↑), recency는 2weeks/recently, 백필 스킵(1.7k콜 절약).**

**자율 운행 개시(사용자 지시)**: 데탑 이전 완료(git main 최신화 — feat는 PR#1 머지·삭제 = **정본 브랜치 main**; venv 3.11.9 재구성 pip check clean; bat 머신-무관화; games-only 크롤 데탑 가동). **사용자가 멈출 때까지(최대 7일 ~07-10) 질문 금지·정지 금지·전 예외 무중단**: ScheduleWakeup 주 루프 + 매시 크론 하트비트(rate-limit 재진입) + 틱 워치독(크롤러 재시작; CAUGHT UP 시 daily_crawl 복귀) + RUNSTATE/저널 = 파일 기억. 절전 차단(powercfg). 월 07-06 정오 = 체크포인트 보고(종료 아님).