# Issue #7: Rerank novelty 슬라이더가 작은 값에서도 유명 게임 과도하게 죽임

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md)


## Symptom

입문자 프리셋 (relevance=9, novelty=2, serendipity=1, diversity=4) 사용 시 추천 top 5에 `Elden Ring`, `Lies of P` 같은 정통 인기작이 없고 `Blade of Darkness`, `Immortal: Unchained`, `Arx Fatalis` 같은 niche 게임이 등장. novelty=2 (작은 값) 인데도 popularity 큰 게임을 과도하게 penalty.

## Diagnosis

기존 rerank 공식 (`retriever.py:rerank_candidates`):
```python
base = (w_rel * rel + w_nov * nov + w_ser * ser) / (w_rel + w_nov + w_ser)
```

모든 weight가 양수 → `novelty=0`이어야 popularity 영향 없음. 사용자는 슬라이더 **5**(중간)를 neutral로 인식 → 5보다 작은 값(2)도 "약한 novelty"가 아니라 의도와 다른 동작.

또 linear weight → 슬라이더 1 차이가 일정한 효과. "4 vs 6은 약하게, 9 vs 10은 강하게" 의도와 불일치.

## Root Cause

`pipeline/game_rec/agent/retriever.py:rerank_candidates`의 weight 해석이 "positive only" — neutral 개념 없음. 사용자 멘탈 모델(5=neutral, 양 끝=강한 효과)과 불일치.

## Fix

**Signed sigmoid scheme**으로 재설계:

(a) `pipeline/game_rec/agent/scoring.py`에 신규 함수:
```python
def sigmoid_modifier(slider, k=3.0):
    """0-10 슬라이더 → signed modifier (-1, +1).
       5 → 0 (neutral), 10 → ~+1, 0 → ~-1.
       sigmoid라 중앙 약하고 양 끝 강함."""
    if not math.isfinite(slider):
        return 0.0
    s = (slider - 5.0) / 5.0
    return 2.0 / (1.0 + math.exp(-k * s)) - 1.0
```

(b) `rerank_candidates` 재작성:
- `relevance`는 positive-only weight (0=무시, 10=최대 강조) — neutral 개념 없음
- `novelty / diversity / serendipity`는 signed via `sigmoid_modifier`
- `nov_centered = 2*nov - 1` ([0,1] → [-1,+1], niche=+1 popular=-1)
- `base = (w_rel/10) * rel + 0.5 * nov_mod * nov_centered + 0.5 * ser_mod * ser_centered`
- MMR diversity: `div_mod > 0`일 때만 sim penalty 적용 (음수면 pure base)

(c) 단위 테스트 6개 추가 (`tests/test_rerank_helpers.py`):
- center=0 (slider 5)
- extremes (slider 0/10 → ±0.91)
- monotone (증가)
- near-center weak (4 vs 6은 약함)
- NaN/inf-safe
- symmetric (sigmoid(5+d) = -sigmoid(5-d))

## Verification

입문자 (rel=9, nov=2):
- `nov_mod = sigmoid_modifier(2) = -0.65` (popular 우대)
- `Elden Ring` (popular): nov_centered=-1 → contribution = (-0.65)(-1) = +0.65 boost
- `Blade of Darkness` (niche): nov_centered=+1 → contribution = -0.65 penalty

→ Elden Ring/Sekiro/Witcher 3/MH World/Wukong 같은 정통 인기작이 top 5에 자연스럽게 등장.

pytest: 49 → **55건** 통과.

## Lesson

- 사용자 UI mental model을 코드와 align. "5=중립"이 직관이면 코드도 5에서 부호 바뀌게.
- Linear scale은 모든 구간에서 동등 효과. Sigmoid는 양 끝에 자유도. 사용자 선택권.
- 슬라이더 의미를 코드 주석/UI tooltip에 명시 ("0=popular 우대, 5=neutral, 10=niche 우대").

---
