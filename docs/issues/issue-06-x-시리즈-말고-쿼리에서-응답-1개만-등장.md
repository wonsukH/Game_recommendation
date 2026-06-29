# Issue #6: "X 시리즈 말고" 쿼리에서 응답 1개만 등장

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md) · 정본: [README.md](../../README.md) · [ROADMAP.md](../ROADMAP.md)


## Symptom

사용자가 "다크 소울 시리즈 말고 비슷한 거 추천해줘" 입력 → LLM 응답에 게임 **1개만** 등장 (예: "Outbreak: The Nightmare Chronicles"). rerank top 5 다 있어야 하는데.

## Diagnosis

1. UI의 rerank_node expander 펼침 → DataFrame 보임 → 5개 게임 있음 (Prepare to Die, Remastered, Lords of the Fallen, DS III, Scholar of the First Sin)
2. 그런데 response_generator의 응답은 1개만.
3. response prompt 확인: "Do not mention any other games" 명시. 5개 중 시리즈 4개(Prepare, Remastered, III, Scholar)는 사용자가 "시리즈 말고" 했으니 LLM이 빼버린 것 → 1개(Lords of the Fallen)만 남음.
4. parser가 게임명 1개만 추출(`["Dark Souls"]`). normalizer가 DS II로 매핑. similar_node가 seed_appids = {DS II} 1개만 제외 → 다른 DS 시리즈는 후보 200개에 포함.

## Root Cause

`pipeline/game_rec/agent/retriever.py`의 `recommend_similar`가 seed_appids 1개만 candidate에서 제외. **"시리즈 전체"라는 개념을 모름**. seed의 변형(Prepare to Die, Remastered, Scholar 등)이 후보에 그대로 들어가서 rerank top에 차지. LLM이 후처리로 시리즈 제거 → 응답 1개.

## Fix

`recommend_similar`에서 seed 게임의 **title prefix**를 추출해 후보 단계에서 자동 제외:

```python
_SERIES_SUFFIX_RE = re.compile(r"\s+(?:[ivx]+|\d+)(?:\s|:|$)|\s*:\s*")

def _series_prefix(title):
    """'DARK SOULS II' -> 'dark souls'"""
    t = str(title).lower().strip()
    parts = _SERIES_SUFFIX_RE.split(t, maxsplit=1)
    return parts[0].strip()

# recommend_similar 안:
canonical_titles = [...]  # seed의 정규화된 title
prefixes = {p for p in (_series_prefix(t) for t in canonical_titles) if len(p) >= 4}

excluded = set(seed_appids)
if prefixes:
    title_lower = self.games_df['game_title'].astype(str).str.lower()
    mask = pd.Series(False, index=self.games_df.index)
    for p in prefixes:
        mask |= title_lower.str.contains(p, na=False, regex=False)
    excluded |= set(self.games_df.index[mask].tolist())

distances, indices = self.faiss_index.search(query_vector, top_k + len(excluded))
candidate_appids = [self.idx_to_appid[i] for i in indices[0] if self.idx_to_appid[i] not in excluded]
```

길이 4 이상 prefix만 사용 (너무 짧은 generic prefix 방지).

## Verification

같은 쿼리 → rerank top 5:
```
ELDEN RING
Monster Hunter: World
Sekiro: Shadows Die Twice - GOTY Edition
Black Myth: Wukong
The Witcher 3: Wild Hunt
```

DS 시리즈 5개 모두 후보 200에서 빠지고 정통 비-시리즈 후계작이 진입. LLM이 5개 다 응답에 사용 (Issue #8 fix와 결합).

## Lesson

- LLM에 의존하는 부분(post-hoc filtering)은 fragile. **결정론적 logic으로 candidate 단계에서 제외**가 더 안정적.
- "시리즈" 개념은 데이터에 없지만 title의 prefix로 추론 가능. heuristic이 명확한 효과.
- 사용자 의도("X 시리즈 말고")가 명시적이면 그것을 시스템 차원에서 명시적으로 처리.

---
