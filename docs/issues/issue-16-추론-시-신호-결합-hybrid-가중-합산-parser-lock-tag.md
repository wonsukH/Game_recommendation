# Issue #16: 추론 시 신호 결합 — Hybrid 가중 합산 + Parser lock + Tag alias

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md)


## Symptom

- "아이작의 번제처럼 어두운 스토리 게임" hybrid 쿼리 → narrative-adventure 게임 5개 추천. roguelike 정체성 사라짐.
- "한 판 한 판 짧게 즐길 수 있는 로그라이크" vibe 쿼리 → puzzle 게임 5개 추천 (klocki, Perspective). 명시 장르 무시.
- Genre Precision 측정 시 `vibe-roguelike` 카테고리 0%.

## Diagnosis

세 원인이 layered:

1. **Hybrid `recommend_hybrid` 가중 합산 (`α·seed + β·vibe`)** — vibe vector magnitude가 크면 (W_align이 narrative-adventure cluster로 매핑) seed(Isaac) 정체성 압도.
2. **`_create_query_vector`에서 명시 target_tag weight가 expand 5개 sum에 묻힘** — parser가 `rogue-like` weight 1.0 출력해도 expand 5개 (각 cosine sim ~0.5) sum이 더 큼.
3. **Parser 출력 vs vocab mismatch** — Parser가 `rogue-like` (하이픈) 출력, vocab은 `roguelike` (하이픈 X). `tag_to_idx['rogue-like']` lookup 실패 → lock 무시. q05의 추천이 lock 적용 후에도 변하지 않은 진짜 원인.

검증:
- Parser 출력 디버깅: q05 던져서 `target_tags`에 `rogue-like` (locked: true) 잘 포함 확인 → Parser는 OK
- Vocab 확인: `tag_vocab.json`에 `roguelike` 매칭, `rogue-like` 매칭 X
- 시스템 추천 niche game 5개를 LLM에 직접 물어봄 → 2개 unknown, 1개 부분 인지 → 시스템 추천 quality는 정확하지만 LLM-as-Judge가 mainstream bias로 unfair (별도 metric 제외 결정)

## Root Cause

- **C1**: `pipeline/game_rec/agent/retriever.py:recommend_hybrid` — 두 벡터 단순 가중 합 + magnitude 정규화 없음
- **C2**: 같은 파일 `_create_query_vector` — normalize 없이 `vec * weight` 합산 → magnitude 큰 expand cluster가 dominant
- **C3**: 같은 파일 `expand_query_tags` — `tag_to_idx[name]` 직접 조회, format drift 처리 없음

## Fix

3 단계 변경 + 각 단계 평가 재실행으로 효과 검증:

**Step 1 — Hybrid 2-stage retrieval**:
- Stage 1: seed로 FAISS coarse search → Isaac 근처 200 후보 (시리즈 자동 제외 포함)
- Stage 2: rerank 단계 `rel = min(cos_seed, cos_vibe)` (vibe는 추가 signal)
- → Seed 정체성을 pool로 한정

**Step 2 — 동적 lock weight + L2 normalize**:
- 모든 tag vector L2 normalize 후 weight 곱
- `locked: true` flag 분리
- 동적: `per_lock_weight = max(non_lock_sum × 2.0, 2.0)` → 비율 일정
- Parser prompt: `target_tags`에 `"locked": true` flag만 (weight는 retriever 계산)

**Step 3 — Normalizer 노드의 책임 확장 (parser ↔ vocab format drift)**:
- 기존 `game_name_normalizer_node`는 **게임명만** canonical 매핑 ("Dark Souls 3" → "DARK SOULS III"), 태그명은 미처리
- 그 결과 Parser가 `rogue-like` 출력, vocab은 `roguelike` → `tag_to_idx` lookup silent fail → lock 무시
- 해결: normalizer 노드의 책임을 entity 전체로 확장. `target_tags`·`avoid_tags`도 normalize. `_resolve_tag` helper(하이픈/언더스코어 normalize 후 vocab 매칭)를 normalizer에서 호출
- 이후 router/recommender는 "이미 canonical entity만 들어온다"는 contract에 의존 가능
- 교훈: **Agent flow의 entity normalize는 한 노드에서 일관 처리**. 책임 범위가 좁으면 다른 entity의 format drift가 silent fail로 누적됨

## Verification

3 fix 누적 효과 (Genre Precision, Steam vote 기반 객관 측정):

| | 처음 | Step 1+2 | + Step 3 |
|---|---|---|---|
| Genre Precision (전체) | 76.7% | 87.3% | **90.7%** |
| vibe-roguelike | 0% | 0% | **100%** |
| vibe-stealth | 0% | 100% | 100% |
| vibe-pixel-rpg | 20% | 100% | 100% |

q05 추천 변화 (alias fix 후):
- 옛: The Cat and the Coup, Trauma, Through Abandoned, The White Door, Ramify (puzzle/narrative)
- 새: Unalive, Fancy Skulls, Not The Robots, Star Chronicles, Never Split the Party (정통 roguelike, Steam 태그 100% rogue-like 보유 확인)

## Lesson

- **추론 시 query vector 결합도 학습 시 신호 강도 통제와 같은 원리.** 두 신호 단순 합산은 magnitude 큰 쪽이 압도. 의도 명확한 신호(seed game, 명시 장르)는 약한 vibe 신호에 묻히지 않도록 구조적 보장 필요.
- **고정 weight (예: lock=2.0)는 깨지기 쉬움.** 다른 태그 개수가 늘면 다시 묻힘. **비율 보존 (lock = non_lock_sum × ratio)** 이 robust.
- **Parser 출력과 vocab 사이의 format drift는 silent failure.** Parser가 lock을 잡았다고 보고해도 vocab과 매칭 안 되면 무시됨. **fuzzy alias 매핑이 안전망.**
- **시스템 추천 객관 검증 (Steam vote 기반 태그)이 LLM-as-Judge보다 더 fair.** LLM-as-Judge는 niche indie game을 LLM이 모를 때 unfair → 별도 metric으로 제외 결정 (portfolio_content.md에 자기 검증 사례로 명시).

## Fix

`pipeline/game_rec/agent/retriever.py:rerank_candidates`에서 Serendipity 계산 부분 제거:
- `ser_raw / ser / ser_centered / ser_mod` 변수 제거
- `base = rel_contrib + 0.5 × nov_mod × nov_centered + 0.5 × ser_mod × ser_centered` → `0.5 × nov_mod × nov_centered`만 남김

UI/config/평가 코드 3축으로:
- `serving/ui.py`: 4 slider → 3
- `config/default.yaml`: presets 3축
- `pipeline/orchestration/llm_vs_system.py` PRESETS: 3축
- `pipeline/game_rec/evaluation/metrics.py`: Serendipity@K 함수 **유지** (측정용)

또 입문자 프리셋 `novelty: 2 → 1` 보정 (Serendipity 1 (음수 modifier)이 제공하던 popular boost를 nov로 약간 보강).

## Verification

label-free 30 query 평가 (`outputs/llm_vs_system_final3.csv`):

| 메트릭 | 4-axis (final) | 3-axis (final3) | pre_m9a (baseline) |
|---|---|---|---|
| overlap@5 | 0.087 | 0.067 | 0.060 |
| vibe_overlap@5 | 0.093 | 0.080 | 0.040 |
| vibe_our_avg_pop | 9.58M | 7.38M | 7.19M |

3-axis가 4-axis 대비 약간 부진 (Serendipity가 popular boost에 기여하고 있었음). 그래도 baseline 대비 명확 우세 (vibe_overlap +100%).

## Lesson

- **measurement metric ≠ user control axis**. 측정에 유용한 metric 4개라고 해서 user에게 4개 slider 줄 필요 X. control axis 설계 시 신호 간 redundancy 검토 필요.
- 학계 표준 follow하는 게 일반적으로 안전. 단 정량 측정으로 검증.
- 정량 vs UX 트레이드오프: 4-axis가 정량 best였지만 UX/학계 표준은 3-axis. 사용자/팀의 우선순위에 따라 결정. 본 시스템은 **simplicity + standard** 우선 → 3-axis.

---
