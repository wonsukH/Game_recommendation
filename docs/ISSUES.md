# ISSUES.md — 발견된 파이프라인 이슈 + 진단 + 해결

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29

> ⚠️ **[폐기·이력] *피벗 이전* 태그-유사도/FAISS 파이프라인의 디버깅 기록이다(현재 코드 아님).** 그 스택(PPMI·SVD·W_align·Item2Vec·FAISS·serving/main.py·similar/vibe/hybrid 모드)은 삭제됨. 현재 시스템은 개인화 CF + LangGraph agent + 행동 SQLite — [`../README.md`](../README.md)·[`ROADMAP.md`](ROADMAP.md) 참조. 본문 수치(Genre Precision 90.7%[순환으로 강등]·9,956게임·55테스트 등)는 당시 값으로, 현재 무효.

본 문서는 후속 연구 진행 중 발견된 **파이프라인 관련 이슈 14건**의 진단/해결 기록.
시각화/UI 관련 이슈(streamlit-agraph physics tuning, plotly hover 보강 등)는 본 문서에서 제외.

각 이슈는 6 섹션:
- **Symptom** — 사용자가 본 현상 / 에러 메시지
- **Diagnosis** — 어떻게 좁혀나갔나 (로그, 측정, 실험)
- **Root Cause** — 진짜 원인 + 코드 위치
- **Fix** — 해결 방법
- **Verification** — fix가 작동함을 어떻게 확인
- **Lesson** — 재발 방지 / 패턴 / 더 일반적 교훈

---


## 모듈 문서 (분할)

- [Issue #1: 새 venv에서 의존성 충돌 (`tokenizers` strict constraint)](issues/issue-01-새-venv에서-의존성-충돌-tokenizers-strict-constr.md)
- [Issue #2: Upstage API 키 정지 → 시스템 전체 마비](issues/issue-02-upstage-api-키-정지-시스템-전체-마비.md)
- [Issue #3: Normalizer가 "Dark Souls 3"를 "DARK SOULS II"로 잘못 매핑](issues/issue-03-normalizer가-dark-souls-3를-dark-souls-ii로.md)
- [Issue #4: PPMI 학습이 binary X 사용 → 매크로 분류 오류](issues/issue-04-ppmi-학습이-binary-x-사용-매크로-분류-오류.md)
- [Issue #5: faiss_index가 옛 vector로 build되어 추천 결과 noise](issues/issue-05-faiss-index가-옛-vector로-build되어-추천-결과-noi.md)
- [Issue #6: "X 시리즈 말고" 쿼리에서 응답 1개만 등장](issues/issue-06-x-시리즈-말고-쿼리에서-응답-1개만-등장.md)
- [Issue #7: Rerank novelty 슬라이더가 작은 값에서도 유명 게임 과도하게 죽임](issues/issue-07-rerank-novelty-슬라이더가-작은-값에서도-유명-게임-과도하게.md)
- [Issue #8: LLM이 rerank top 5 중 3개만 응답에 mention](issues/issue-08-llm이-rerank-top-5-중-3개만-응답에-mention.md)
- [Issue #9: `steam_games_tags.csv` 1031 rows vs 새 9956 게임 → KeyError 2855](issues/issue-09-steam-games-tagscsv-1031-rows-vs-새-9956.md)
- [Issue #10: `quality.py`가 numpy float32 JSON serialize 실패](issues/issue-10-qualitypy가-numpy-float32-json-serialize.md)
- [Issue #11: `langchain-google-genai 4.x` 설치 시 다른 langchain 패키지 4개와 충돌](issues/issue-11-langchain-google-genai-4x-설치-시-다른-langch.md)
- [Issue #12: `text-embedding-004` 모델이 deprecated → 404](issues/issue-12-text-embedding-004-모델이-deprecated-404.md)
- [Issue #13: Streamlit `cache_resource`가 .npy 갱신 시 자동 reload 안 됨](issues/issue-13-streamlit-cache-resource가-npy-갱신-시-자동-re.md)
- [Issue #14: Vibe 모드 niche cluster bias (M9.A 시도 → revert → M9.C로 해소)](issues/issue-14-vibe-모드-niche-cluster-bias-m9a-시도-revert.md)
- [Issue #15: Serendipity slider redundancy (M11에서 제거)](issues/issue-15-serendipity-slider-redundancy-m11에서-제거.md)
- [Issue #16: 추론 시 신호 결합 — Hybrid 가중 합산 + Parser lock + Tag alias](issues/issue-16-추론-시-신호-결합-hybrid-가중-합산-parser-lock-tag.md)
- [정리 — 발견 패턴](issues/16-정리-발견-패턴.md)
