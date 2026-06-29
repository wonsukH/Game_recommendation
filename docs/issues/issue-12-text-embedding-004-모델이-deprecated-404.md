# Issue #12: `text-embedding-004` 모델이 deprecated → 404

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md) · 정본: [README.md](../../README.md) · [ROADMAP.md](../ROADMAP.md)


## Symptom

`text_alignment.py` 실행 중:

```
google.api_core.exceptions.NotFound: 404 models/text-embedding-004 is not found
  for API version v1beta, or is not supported for embedContent.
```

## Diagnosis

`langchain-google-genai 2.x`가 v1beta API 사용. `text-embedding-004`가 v1beta에서 사라짐.

사용 가능 embedding 모델 확인:
```python
import google.generativeai as genai
genai.configure(api_key=...)
for m in genai.list_models():
    if 'embedContent' in m.supported_generation_methods:
        print(m.name)
```

결과:
```
models/gemini-embedding-001
models/gemini-embedding-2-preview
models/gemini-embedding-2
```

## Root Cause

Google이 embedding 모델 라인을 `text-embedding-004` → `gemini-embedding-XXX`로 rebrand. 옛 모델 이름은 v1beta API에서 제거됨.

## Fix

`.env` + 코드의 embedding 모델명 변경:

`.env`:
```
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-2
```

`pipeline/game_rec/agent/retriever.py`:
```python
def __init__(self, data_path, embedding_model="models/gemini-embedding-2"):
    ...
```

`config/default.yaml`:
```yaml
models:
  text_alignment:
    text_model: models/gemini-embedding-2
```

## Verification

```powershell
python -m pipeline.game_rec.models.text_alignment
# Successfully embeds 447 tags
# W_align.npy shape (3072, 128) — gemini-embedding-2 차원
```

## Lesson

- LLM provider의 모델 lineup은 빠르게 변함. hardcode하지 말고 `.env` / config에서 갱신 가능하게.
- 새 환경 셋업 시 `list_models()` API로 사용 가능 모델 확인이 첫 단계.
- 모델 이름의 prefix(`models/`) 일관성 확인 — langchain wrapper가 가끔 prefix를 추가/제거.

---
