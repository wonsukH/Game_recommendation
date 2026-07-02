# Issue #2: Upstage API 키 정지 → 시스템 전체 마비

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md) · 정본: [README.md](../../README.md) · [ROADMAP.md](../ROADMAP.md)


## Symptom

`text_alignment.py` 실행 중 다음 에러:

```
openai.PermissionDeniedError: Error code: 403
{'error': {'message': 'API key suspended due to insufficient credit.
  Register your payment method at https://console.upstage.ai/billing
  to continue.', 'code': 'api_key_is_not_allowed'}}
```

같은 키를 사용하는 `ChatUpstage` (parser, response_generator)도 동시 마비.

## Diagnosis

1. Upstage 결제 정보 정지로 API key 차단.
2. `text_alignment` (Solar embedding 호출) + `ChatUpstage` (parser/response 호출) 둘 다 같은 키 사용.
3. **시스템 전체가 단일 LLM 인프라에 결합**되어 있음.

## Root Cause

`UPSTAGE_API_KEY` 하나로 두 종류 호출(embedding + chat)을 모두 처리. 다른 LLM 제공자로의 fallback 분기 없음.

코드 위치:
- `pipeline/game_rec/models/text_alignment.py` (Solar embedding)
- `pipeline/game_rec/agent/retriever.py` (runtime Solar embedding for vibe phrase)
- `serving/main.py` (ChatUpstage init)

## Fix

전체 LLM 인프라를 Gemini로 전환:

1. **패키지 install**: `pip install "langchain-google-genai>=2,<3"` (4.x는 `langchain-core 1.x` 요구로 다른 langchain 패키지 충돌 → Issue #11)
2. **`.env` 갱신**:
   ```
   GEMINI_API_KEY=...
   GEMINI_EMBEDDING_MODEL=models/gemini-embedding-2
   GEMINI_CHAT_MODEL=gemini-2.5-pro
   ```
3. **코드 변경**:
   - `pipeline/game_rec/models/text_alignment.py`: `UpstageEmbeddings` → `GoogleGenerativeAIEmbeddings`, "solar" 분기 → "gemini" 분기
   - `pipeline/game_rec/agent/retriever.py`: `UpstageEmbeddings` → `GoogleGenerativeAIEmbeddings`, `os` import 추가
   - `serving/main.py`: `ChatUpstage` → `ChatGoogleGenerativeAI`, `GEMINI_API_KEY` 체크, `temperature=0.2`
   - `config/default.yaml`: `text_model: solar-embedding-1-large` → `models/gemini-embedding-2`

## Verification

- `python -m pipeline.game_rec.models.text_alignment` → exit 0, `W_align.npy` shape (3072, 128)
- Streamlit 실행 → parser/response 모두 Gemini로 동작
- pytest 55건 통과

## Lesson

- 외부 LLM API 의존 시 결제/quota 정지 가능성 항상 염두. fallback 경로 또는 모델 swap 용이성 설계 필요.
- "embedding"과 "chat" 두 호출 종류를 같은 인프라에 묶지 말기. 각각 다른 제공자 가능.
- `.env`에 모델명을 명시 (코드 hardcode X) → 모델 교체 시 `.env`만 변경.

---
