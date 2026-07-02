# 데이터 / 모델 파이프라인 상세 — Reproducible Specification

> **유형**: design-spec · **상태**: deprecated · **갱신**: 2026-06-29

> ⚠️ **[폐기·이력] 이 스펙은 *피벗 이전* 태그-유사도 파이프라인(PPMI+SVD 128d tag_vecs·Item2Vec·W_align·FAISS·MMR rerank·similar/vibe/hybrid/general·serving/main.py)을 기술하며 현재 시스템이 아니다.** 그 스택은 삭제됨. 현재 = 개인화 CF(`cf_recommender.py`) + LangGraph agent(`serving/agent_graph.py`, routes library/seed/multi_entity/explore/anonymous, entry `main_agent.py`) + content/hybrid 스티어링 + 행동 SQLite `steam.db`. 정본은 [`../README.md`](../README.md)·[`ROADMAP.md`](ROADMAP.md). 데이터층 재구축 후(P8) 전면 재작성 예정. (Genre Precision 90.7%·Pool Coverage Miss·9,956게임/447태그·55테스트는 폐기/강등 수치.)

이 문서는 본 시스템을 **밑바닥부터 동일하게 재현할 수 있는 수준**으로 모든 단계를 기술한다. 각 단계의 입력 / 출력 / 알고리즘 / 수식 / 하이퍼파라미터 / 실행 명령 / 트러블슈팅을 다 포함.

목차:
1. [시스템 가설](#0-시스템-가설)
2. [데이터 수집 (Crawling)](#1-데이터-수집-crawling)
3. [데이터 처리 (`pipeline/game_rec/data/`)](#2-데이터-처리)
4. [임베딩 (`pipeline/game_rec/models/`)](#3-임베딩)
5. [인덱스 (`pipeline/game_rec/index/`)](#4-인덱스)
6. [평가 (`pipeline/game_rec/evaluation/`, `pipeline/orchestration/`)](#5-평가)
7. [에이전트 (`pipeline/game_rec/agent/`)](#6-온라인-에이전트)
8. [서빙 UI (`serving/`)](#7-서빙-ui)
9. [전체 하이퍼파라미터](#8-하이퍼파라미터-전체)
10. [실행 명령 모음](#9-실행-명령-모음)
11. [트러블슈팅](#10-트러블슈팅)

---


## 모듈 문서 (분할)

- [0. 시스템 가설](pipeline/00-시스템-가설.md)
- [1. 데이터 수집 (Crawling)](pipeline/01-데이터-수집-crawling.md)
- [2. 데이터 처리](pipeline/02-데이터-처리.md)
- [3. 임베딩](pipeline/03-임베딩.md)
- [4. 인덱스](pipeline/04-인덱스.md)
- [5. 평가](pipeline/05-평가.md)
- [6. 온라인 에이전트](pipeline/06-온라인-에이전트.md)
- [7. 서빙 UI](pipeline/07-서빙-ui.md)
- [8. 하이퍼파라미터 전체](pipeline/08-하이퍼파라미터-전체.md)
- [9. 실행 명령 모음](pipeline/09-실행-명령-모음.md)
- [10. 트러블슈팅](pipeline/10-트러블슈팅.md)
- [부록 A. 알려진 한계](pipeline/11-알려진-한계.md)
- [부록 B. 디렉토리 트리](pipeline/12-디렉토리-트리.md)
