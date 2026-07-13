# 설계 의도 — 왜 이렇게 만들었는가

> **유형**: design-spec · **상태**: deprecated · **갱신**: 2026-06-29

> ⚠️ **[폐기·이력] 이 문서는 *피벗 이전*(태그-유사도/PPMI·SVD/W_align/FAISS/Item2Vec, similar·vibe·hybrid 모드) 시스템 기준이라 현재 아키텍처와 불일치한다.** 현재 시스템(개인화 CF moat + LangGraph agent[library/seed/multi_entity/explore/anonymous] + 행동 SQLite `steam.db`)은 [`../README.md`](../README.md)·[`ROADMAP.md`](ROADMAP.md) 참조. 이 파일은 당시 설계의도의 *역사적 기록*으로만 보존(전면 갱신은 데이터층 재구축 P8 이후).

이 문서는 본 프로젝트의 **모든 결정의 이유**를 처음 보는 사람도 이해할 수 있게 풀어쓴 글이다. 수식이나 코드 디테일은 [README_PIPELINE.md](README_PIPELINE.md)에 있다. 여기서는 **"왜"**와 **"어떤 동작을 의도했는가"**에 집중.

---


## 모듈 문서 (분할)

- [0. 한 문장 요약](intent/00-한-문장-요약.md)
- [1. 왜 이 문제를 푸나](intent/01-왜-이-문제를-푸나.md)
- [2. 큰 그림 — 시스템이 어떻게 작동하나](intent/02-큰-그림-시스템이-어떻게-작동하나.md)
- [3. 단계별 의도](intent/03-단계별-의도.md)
- [4. 온라인 에이전트 — 왜 LangGraph?](intent/04-온라인-에이전트-왜-langgraph.md)
- [5. 평가 — 왜 LLM 비교?](intent/05-평가-왜-llm-비교.md)
- [6. M9 — Vibe 약점 풀기 시도 + 결과](intent/06-m9-vibe-약점-풀기-시도-결과.md)
- [7. 다음 방향 (이번 plan 범위 밖)](intent/07-다음-방향-이번-plan-범위-밖.md)
- [7. 면접 / 포트폴리오 관점](intent/08-면접-포트폴리오-관점.md)
- [부록: 용어 사전](intent/09-용어-사전.md)
