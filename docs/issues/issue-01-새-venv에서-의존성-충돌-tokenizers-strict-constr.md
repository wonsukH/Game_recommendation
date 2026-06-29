# Issue #1: 새 venv에서 의존성 충돌 (`tokenizers` strict constraint)

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md)


## Symptom

옛 27기 팀 venv는 정상 동작. 새로 만든 `.venv`에서 `pip install -r pinned.txt` 시도 시 ResolutionImpossible 에러:

```
langchain-upstage 0.7.3 has requirement tokenizers<0.21.0,>=0.20.0
sentence-transformers 5.5.1 has requirement tokenizers>=0.21
```

## Diagnosis

1. `pip check`로 27기 venv 검사 → 같은 충돌이 이미 존재. 다만 27기는 strict resolver 적용 전 staged install로 받아들여진 broken state.
2. langchain-upstage 최신 0.7.7도 `tokenizers<0.21.0` 제약 그대로 → 패키지 메인테이너가 풀어주지 않음.
3. 새 venv는 pip 26.x strict resolver라 충돌 거부.

## Root Cause

`pinned.txt`의 `sentence-transformers==5.5.1`이 `tokenizers>=0.21` 요구. 같은 파일에 `langchain-upstage==0.7.3`은 `tokenizers<0.21` 요구. **두 패키지가 본질적으로 호환 불가**.

## Fix

`pinned.txt`에서 다음 3 라인을 relax:
- `sentence-transformers==5.5.1` → `sentence-transformers>=4.0,<5`
- `tokenizers==0.22.2` → `tokenizers<0.21`
- `transformers==5.9.0` → `transformers>=4.41,<5`
- 추가로 `huggingface_hub<1.0`, `safetensors<0.6` (transitive 호환)

sentence-transformers 4.x는 `tokenizers<0.21` 호환 → 두 패키지 화해.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip check
# "No broken requirements found"

.\.venv\Scripts\python.exe -c "from langchain_upstage import UpstageEmbeddings; from sentence_transformers import SentenceTransformer; print('ok')"
# "ok"

.\.venv\Scripts\python.exe -m pytest tests/
# 49 passed (이후 55 passed)
```

## Lesson

- "옛 venv가 작동한다"는 것이 의존성 그래프가 valid함을 의미하지 않음. broken state도 staged install로 들어오면 runtime OK.
- 다른 환경 재구성 시 `pip check`를 첫 검증으로.
- 두 패키지의 strict 제약이 충돌하면 둘 중 하나를 다운그레이드 (`langchain-upstage`가 메인테이너 정책상 제약 유지하니 sentence-transformers를 양보).

---
