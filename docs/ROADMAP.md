# ROADMAP & HANDOFF — 여기부터 보면 됨 (세션 리셋용)

> **유형**: roadmap · **상태**: active · **갱신**: 2026-07-02 · **브랜치**: `feat/personalization-agent-and-data-infra` · origin = github.com/wonsukH/Game_recommendation

> 컨텍스트가 리셋돼도 이 문서 + 메모리(`~/.claude/.../memory/`) + `experiments/DELIBERATION_LOG.md`만 보면 이어갈 수 있다.

## 한 줄 현황
태그-유사도(삭제됨, LLM에 ~96% 패배) → **개인화 CF moat + LangGraph 에이전트**로 피벗 완료. 지금은 **데이터 층을 리뷰-CSV → 행동-SQLite(`steam.db`)로 재구축** 중이며, 그 결과 추천 입력·"liked" 정의·품질신호·평가를 전부 재배선해야 한다(아래 P4~P9).

## 지금 돌아가는 것 (리셋 후 먼저 확인)
- **라이브 크롤**(`data_collection/crawl_unified.py --forever ... --stop-at-users 10000`). 목표 10k 공개유저, **2026-07-02 기준 1,669명**(owned 726k·업적 5.6M·distinct 게임 40.6k). games 차원(희소 메타) 채움 11,775 / **백로그 28,836**. 실측 유저 페이스 ~255명/일(다운타임·쓰로틀 포함) → **현실 ETA 3~5주**. ⚠️ `daily_crawl.bat`에 `--stop-at-users` 미지정(자동정지 안 함)·워치독 없음(06-28~29 ~20h, **07-01 08:23~07-02 16:21 ~32h 무가동 2회째** → 07-02 재기동) → 생존 점검 필수.
- **⚠️ 일시 모드(07-02 16:49~)**: 게임 메타가 너무 희소해 실험 불가(사용자) → **games-only 전용 런**(`--phases games --forever --limit 90000`, 임시 bat는 세션 스크래치패드)으로 백로그 28.8k 우선 소진 중. **유저 크롤은 그동안 일시정지.** 실측(07-02 17:35): 게임당 ~5콜·콜당 ~1.0s(RTT) → 분당 ~11.5개, **ETA ~07-04 오전**(예산 정지 없음 — 이 페이스면 90k/day 미달). **소진 후 `scripts\daily_crawl.bat`(users+games)로 복귀할 것.**
- **리셋되면 백그라운드 크롤이 죽을 수 있음** → 살아있는지 확인 후 없으면 재시작(재개형, steam.db에서 이어받음, 손실 0):
  ```
  scripts\daily_crawl.bat
  ```
- 진행 확인: `python -c "import sqlite3;print(sqlite3.connect('data_collection/steam.db').execute('SELECT COUNT(*) FROM users WHERE public=1 AND complete=1').fetchone())"`

## 어디에 무엇이 있나
- **데이터(로컬·gitignored)**: `data_collection/steam.db`(행동 17테이블) · `data_collection/export/*.csv`(10명 샘플 덤프).
- **크롤러/스토어**: `data_collection/db.py`(스키마·예산게이트·인터닝 헬퍼) · `data_collection/crawl_unified.py`(2-phase, 월클록 페이싱) · `scripts/daily_crawl.bat`.
- **추천 코드(현행)**: `pipeline/game_rec/agent/`(cf_recommender·content·hybrid·tools·build_quality·steam_library·baselines) · `serving/agent_graph.py`(LangGraph 라우팅) · `serving/main_agent.py`(Streamlit).
- **프로덕션 아티팩트**: `serving/data/`(cf/·index_maps.json·X_game_tag_csr.npz·game_popularity.npy·game_quality.json·tag_vocab.json) — **주의: 아직 구 리뷰데이터 기반. P5에서 steam.db로 재생성 예정.**
- **평가/오케스트레이션**: `pipeline/orchestration/`(ranker_benchmark·personalization_experiment·steering_eval·library_richness(_live)·coldstart_eval·shrinkage_eval·agentic_eval·data_scaling).
- **로그/증거**: `experiments/DELIBERATION_LOG.md`(고민·결정의 서사, append-only) · `experiments/registry.jsonl`(run 수치) · `experiments/INDEX.md`.
- **문서**: `docs/`(INTENT·ISSUES·README_PIPELINE·technical_reference.html·runbook). 이 로드맵 = `docs/ROADMAP.md`.
- **상위 플랜 원본**: `C:\Users\hwons\.claude\plans\jiggly-meandering-whale.md`.
- **메모리(세션 간 자동 로드)**: `~/.claude/projects/D--YBIGTA-Newbie-project-Game-recommendation/memory/` — 행동규칙·역할·평가원칙·현황. (구 경로 `…/D--YBIGTA-Newbie-project/memory/`에도 백업 사본 있음; **반드시 프로젝트 루트 `Game_recommendation\`에서 실행**해야 이 메모리가 로드됨.)

## 핵심 검증 결과 (왜 이 방향인가)
- 개인화 **CF가 LLM-with-library 이김**: recall@20 0.293 vs 0.173, Δ+0.120 [+0.049,+0.192] 유의.
- **CF ≈ EASE 동률**(ranker bench: cf 0.203, ease 0.200 ns, als 0.174 ns, pop 0.078 SIG) → 단순 CF 정당.
- 익명/태그-유사도는 LLM에 ~96% 패배 → 폐기(이는 *익명/vibe 한정* 판정). **추천 성능 = 개인화 niche의 입증된 scoped moat**(CF>LLM-lib, ≈EASE), **자기비판적 평가 = 그 우위를 정직히 한정하는 보완 메타역량**(둘 다 — 성능 '대신' 아님). 메모리 [[game-rec-meaningfulness-verdict]].
- 스티어링(인접 노벨티)으로 CF 필터버블 깨고 신장르 발굴(blinded judge 1.0).

## CF moat 방식 (변하지 않는 코어)
`pipeline/game_rec/agent/cf_recommender.py`: 플레이타임 가중 item-item 공출현 conditional-cosine.
`sim(i,j)=C[i,j]/√(deg_i·deg_j)` (min_cooc≥3), `score(g)=Σ_{p∈lib} w_p·sim(g,p)`, `w_p=log(1+playtime_p/avg_p)`.
**데이터가 바뀌어도 이 수식은 유지**; 바뀌는 건 "liked" 정의·가중치·카탈로그·품질·평가(아래).

## 왜 추천 "방식"이 바뀌나 (데이터 전환의 파급)
구 스택은 **리뷰 점수**(`s_round10_rec`)에 묶임. 새 데이터엔 점수 없음(스팀=추천/비추천뿐, 리뷰 드롭). 그래서:
- CF "liked" = `s_round10_rec≥7` → **playtime+업적으로 재정의**.
- 품질 게이트 = 리뷰점수 집계 → **출처 사라짐(steamspy 긍부정+metacritic로 재정의)**.
- 카탈로그/태그/인기/제목 = `outputs/*.csv` → `games`/`steamspy` 테이블.
- 구 소스→신 테이블 매핑은 플랜 파일/아래 P5 참조.

---

## 포워드 로드맵 (각 Pillar = 착수 시 **전용 상세 플랜** 작성; 세부 결정은 그때 사용자와)
순서: 크롤(진행) → **P4(게이트)** → P5 → P6 → P7 → P8 ; P9 상시.

- **P4 — 행동 기반 "liked"/선호 정의 (게이트, 먼저)**: playtime(+업적)으로 liked 정의 → 행동-liked CF가 구 리뷰-liked CF recall 재현/상회하는지 사전등록 검증. 신규 `data/behavioral_scores.py`. *결정할 것*: 임계방식(median비율/백분위/절대 — 코호트 편향에 강건한 **유저상대(비율/백분위) 우선**), 업적보정, 통과기준. 의존: 크롤 데이터 충분(수천+) — **행동 방식은 리뷰 방식보다 유저당 신호가 조밀**(중앙값 214 owned·89 liked후보·~1.2k유저에서 co-play쌍 ~92M)이라 **현재 ~1.2k로도 P4 본분석 착수 가능**. 5k/10k 목표는 꼬리(long-tail) 커버·OOD 검정력용이고, 코호트 편향은 인원수가 아니라 P6 랜덤-OOD로 해소(인원/풍부도로는 편향 안 풀림).
- **P5 — 빌더 재배선(CSV→steam.db) + 아티팩트 재생성**: cf/coplay, tag_vocab/game_tag_matrix(→index_maps·X_game_tag), game_popularity, build_quality(출처교체), 제목, `tools.CatalogMeta`(런타임CSV 제거), steam_library.proxy_library. **풀 = 크롤 따라 확장(확정; 현재 games≈30.6k, 코드상 상한 없음)**. *결정*: 품질출처. 의존: P4.
- **P6 — 평가 재실행(풍부데이터) + OOD 편향**: ranker 재벤치(CF/EASE/ALS), CF vs LLM, 풍부 owned가 구 리뷰-CF 넘는지; **랜덤 accountID OOD hold-out**으로 코호트 편향 정량화 + 포화곡선으로 크롤 정지시점. 의존: P5.
- **P7 — 선호-가중 학습모델 (업적 회수처; 필수)**: 업적 크롤(비용의 ~96%)의 회수처이므로 **수행 자체는 확정**. `w_p=f(playtime,완료율,희귀도,recency)` 학습형 vs 고정 log식, 사전등록 비교(휴리스틱/GBM/NN) — 열린 건 *어느 쪽이 이기나*(학습형이 지면 음성결과로 고정식 유지). 의존: P5–6.
- **P8 — 서빙 갱신**: agent_graph/main_agent를 재생성 아티팩트로; 품질게이트·ContentLayer·CatalogMeta 새 소스; 5라우트 end-to-end + pytest. 의존: P5(–7).
- **P9 — 지속/모니터링(상시)**: 크롤 목표까지; 누적분으로 P5–6 주기 재실행; Pillar마다 커밋+push.

태스크: #44(P4) #45(P5) #46(P6) #47(P7) #48(P8) #49(크롤 모니터).

## 작업/행동 규칙 (메모리에도 있음, 필수)
- **변경 전 보고·명시적 OK**([[confirm-before-code-change]]) — 작은 fix 포함.
- **큰 일은 Pillar 단위로 항상 커밋+push**([[commit-per-pillar]]); 키·유저데이터(steam.db/export/.env) **절대 커밋 금지**(Steam ToU, 전부 gitignore됨).
- **모든 고민·결정을 `DELIBERATION_LOG.md`에 append**([[always-log-deliberation]]).
- **비판적·객관적 평가**: 지표부터 검증(meta-eval), 사전등록·CI·귀무/음성보고·OOD 적대적 재검([[critical-objective-evaluation]]).
- **돌아가는 작업 임의 중단 금지**(사용자 요청 시만).
- **큰 작업은 Pillar당 전용 플랜**(한 파일에 결정 욱여넣지 말 것; 갈림길은 Pillar마다 사용자와).
- 외부자료(포트폴리오)는 채용담당자 시각·결과중심·내부용어 금지([[user-role-and-portfolio]]).
