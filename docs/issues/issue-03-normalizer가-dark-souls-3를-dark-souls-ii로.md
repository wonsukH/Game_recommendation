# Issue #3: Normalizer가 "Dark Souls 3"를 "DARK SOULS II"로 잘못 매핑

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md)


## Symptom

사용자가 "다크 소울 시리즈 말고 비슷한 거 추천해줘" 입력 → parser가 정확히 `["Dark Souls", "Dark Souls 2", "Dark Souls 3"]` 추출. 하지만 normalizer가 **셋 다 "DARK SOULS II"로 매핑** → seed가 사실상 1개 → 결과가 빈약.

## Diagnosis

1. `normalizer.py:25`의 `find_best_match`는 Jaccard bigram similarity 사용.
2. 수동 측정:
   - `"Dark Souls 3"` vs `"DARK SOULS II"` Jaccard = 0.769
   - `"Dark Souls 3"` vs `"DARK SOULS III"` Jaccard = 0.769 (**동점**!)
3. bigram set에서 `"ii"`와 `"iii"`가 둘 다 1개 element (중복 제거). 차이가 사라짐.
4. tie-breaker가 first-come(코드 line 33의 `> best_score`, not `>=`). `canonical_titles` 순서에서 II가 III보다 앞 → 항상 II.

## Root Cause

`pipeline/game_rec/agent/nodes/normalizer.py:8-23`의 `jaccard_similarity`가 string을 그대로 bigram화. roman numeral과 arabic numeral의 차이를 bigram set이 못 잡음.

## Fix

매칭 전에 **canonicalize**: 모든 string을 lowercase + roman → arabic 변환:

```python
_ROMAN_TO_ARABIC = [
    (re.compile(r"\bviii\b"), "8"),
    (re.compile(r"\bvii\b"), "7"),
    (re.compile(r"\bvi\b"), "6"),
    (re.compile(r"\biv\b"), "4"),
    (re.compile(r"\biii\b"), "3"),    # 길이 desc 순서 — III를 II보다 먼저
    (re.compile(r"\bii\b"), "2"),
    (re.compile(r"\bix\b"), "9"),
    (re.compile(r"\bx\b"), "10"),
]

def _canonical_form(s):
    s = s.lower().strip()
    for pat, rep in _ROMAN_TO_ARABIC:
        s = pat.sub(rep, s)
    s = re.sub(r"[:\-™®©]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def jaccard_similarity(s1, s2):
    s1 = _canonical_form(s1)
    s2 = _canonical_form(s2)
    # 이후 기존 bigram Jaccard
```

**핵심**: III를 II보다 먼저 substitute (길이 desc). 안 그러면 "iii"가 "ii + i"로 부분 매칭되어 잘못된 변환.

## Verification

```
"Dark Souls 2" → DARK SOULS II  (Jaccard 1.0)
"Dark Souls 3" → DARK SOULS III (Jaccard 1.0)   ← 정확 매핑
```

streamlit에서 같은 쿼리 다시 → seed에 DS II + DS III 모두 매핑 (unique 2개) → series filter (Issue #6 fix와 결합)로 시리즈 전체 제외.

## Lesson

- 문자열 유사도 알고리즘 선택 시 도메인 특성 고려. 게임 title은 roman/arabic, ™ symbol, colon 등 노이즈 많음.
- Character bigram은 짧은 substring 차이를 못 잡음. canonical form preprocessing이 필수.
- 정규식 치환 순서: 긴 패턴 먼저 (III → II 전에).

---
