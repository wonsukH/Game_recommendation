# 4. 온라인 에이전트 — 왜 LangGraph?

> **유형**: design-spec · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [INTENT.md](../INTENT.md) · 정본: [README.md](../../README.md) · [ROADMAP.md](../ROADMAP.md)


## Pipeline 구조

```
parser → normalizer → mode-specific node → rerank → response
```

각 노드를 분리한 이유:
- **parser**: LLM이 자연어 → JSON 변환. 어떤 LLM이든 substitute 가능
- **normalizer**: "Dark Souls 3" 같은 사용자 표현을 데이터셋의 canonical title ("DARK SOULS III")에 매핑
- **mode 분기**: similar (게임명) / vibe (자연어만) / hybrid (둘 다) — 각각 다른 query vector 구성
- **rerank**: 사용자 선호 슬라이더 반영
- **response**: LLM이 자연어 답변 생성

LangGraph는 이 흐름을 명시적으로 표현. 디버깅도 쉬움 (각 노드 expander로 확인).

## Normalizer의 Roman ↔ Arabic Fix

사용자가 "Dark Souls 3"라고 하면 데이터셋은 "DARK SOULS III"로 저장됨. Jaccard bigram similarity로 매칭하는데:
- "Dark Souls 3" vs "DARK SOULS II" = 0.77
- "Dark Souls 3" vs "DARK SOULS III" = 0.77 (동점!)

"II"와 "III"의 차이가 bigram set에서 사라지기 때문. **해결**: 매칭 전에 "III" → "3"로 변환해서 정확히 일치하게.

**의도**: 사용자가 한국어로 "다크 소울 3"라고 해도 정확히 3편을 찾게.

## Series 자동 필터

사용자: "다크 소울 시리즈 말고 비슷한 거"
- 옛 방식: parser가 "Dark Souls" 1개 추출 → DS II 1개만 candidate에서 제외 → 결과에 DS Prepare, Remastered, III 등 포함 → LLM이 후처리로 제거하다 1개만 남음
- 새 방식: seed title의 prefix ("dark souls") 추출 → 전 시리즈 5개 다 candidate에서 자동 제외 → 비-시리즈 정통 후계만 top 5

**의도**: "X 시리즈 말고"를 의도대로 작동시키기.

## Rerank — Signed Sigmoid

사용자가 사이드바 슬라이더로 추천 성향 조정:
- Relevance (쿼리 일치): 0=무시, 10=최대 강조
- Diversity (다양성): 5=중립, 10=다양, 0=비슷한 류
- Novelty (새로움): 5=중립, 10=niche, 0=유명 게임 우대
- Serendipity (의외성): 같음

**왜 5가 중립?**
- 사용자가 "값을 안 건드리면 영향 없음"을 직관적으로 기대
- 옛 방식: 모든 값이 양수 weight → 5도 영향이 있음 (less popular 게임 boost) → 입문자 프리셋(nov=2)에서도 유명 게임이 너무 약하게 됨
- 새 방식: 5=neutral, >5=niche 강조, <5=popular 강조 → 직관적

**왜 sigmoid?**
- linear 변환이면 4 vs 6의 효과가 9 vs 10과 비슷 → 사용자가 "값을 살짝 바꿀 때 너무 큰 변화"
- sigmoid는 중앙(5) 근처는 약하고 양 끝(0, 10)에서 강함 → "값을 결단력 있게 양 끝으로 가야 명확한 효과"

**의도**: 슬라이더가 직관적으로 작동.

## MMR (Maximal Marginal Relevance)

후보 200개에서 top 5 뽑을 때 단순히 cosine top 5만 뽑으면 **다 비슷한 게임**.

예: DS II 시드 → top 5가 모두 DS 시리즈 변형. 사용자는 "비슷한데 다른 거"를 원함.

**MMR**: greedy로 첫 번째는 가장 cosine 높은 거. 두 번째부터는 "cosine 높지만 이미 뽑힌 게임들과 다른 거"를 선택. 즉:

```
score = (1 - λ) × cosine - λ × max(이미 뽑힌 게임과의 유사도)
```

λ는 diversity 슬라이더에서 결정. **의도**: 결과가 단조롭지 않게.

## Response Generator Prompt 강화

LLM이 5개 다 받았는데 3개만 응답에 등장하던 문제 → prompt에 명시적으로 "5개 다 mention", temperature=0.2로 deterministic.

---
