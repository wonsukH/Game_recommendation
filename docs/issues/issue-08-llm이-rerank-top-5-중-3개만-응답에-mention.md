# Issue #8: LLM이 rerank top 5 중 3개만 응답에 mention

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md) · 정본: [README.md](../../README.md) · [ROADMAP.md](../ROADMAP.md)


## Symptom

rerank top 5 = (Lords of the Fallen, Blade of Darkness, Dragon's Dogma, Immortal: Unchained, Arx Fatalis). 그런데 response_generator 응답은 첫 3개(Lords, Dragon, Blade)만 mention. 나머지 2개 누락.

## Diagnosis

1. `prompts/response_generator.txt` 확인:
   ```
   1. You MUST only explain and select from the games provided in the list below.
      Do not mention any other games.
   ```
2. **"5개 다 mention"은 강제하지 않음**. LLM이 임의로 일부 선택 가능.
3. Gemini default temperature ~1.0 → 응답 가변성 큼.

## Root Cause

- `prompts/response_generator.txt` rule이 "다른 게임 mention 금지"는 있지만 "주어진 모든 게임 mention" 강제는 없음.
- `serving/main.py`의 `ChatGoogleGenerativeAI` init이 temperature 명시 안 함 → default ~1.0 (gemini family).

## Fix

(a) `prompts/response_generator.txt` rule 강화:
```
1. You MUST mention EVERY SINGLE game in the list below. Do not skip any game.
   If 5 games are provided, your response must contain exactly 5 bullet points
   — one per game.
2. You MUST NOT mention any game not in the list. Do not invent or substitute
   games from your own knowledge.
3. Output one bullet point per game, in the same order they appear in the list.
4. For each game, provide a concise 1-2 line Korean explanation, persuasive but
   grounded in its matching score and key metadata.
5. Do NOT mention any features the user wanted to avoid ...
```

(b) `serving/main.py`:
```python
return ChatGoogleGenerativeAI(
    model=chat_model, google_api_key=GEMINI_API_KEY, temperature=0.2,
)
```

## Verification

같은 쿼리 재시도 → 5개 모두 응답에 등장:
- Elden Ring
- Monster Hunter World
- Sekiro
- Witcher 3
- Black Myth: Wukong

(Issue #6 fix와 결합된 결과)

## Lesson

- LLM 강제 사항은 prompt에 명시적으로. "Do not X"만으로는 "Must do Y"가 강제 안 됨.
- Temperature 낮추면 deterministic 응답. 정해진 list를 정확히 반환해야 할 때 (`temperature=0.2`).
- prompt rule 단위 테스트 가능: 5개 게임 → 5 bullet point인지 응답 파싱 검증.

---
