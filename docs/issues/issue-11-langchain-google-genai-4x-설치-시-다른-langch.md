# Issue #11: `langchain-google-genai 4.x` 설치 시 다른 langchain 패키지 4개와 충돌

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md)


## Symptom

처음 `pip install langchain-google-genai` 시도 → 4.2.2 설치되고 `langchain-core` 1.4.0으로 업그레이드됨. 그 후:

```
langchain 0.3.27 has requirement langchain-core<1.0.0,>=0.3.72
langchain-openai 0.3.31 has requirement langchain-core<1.0.0,>=0.3.74
langchain-text-splitters 0.3.9 has requirement langchain-core<1.0.0,>=0.3.72
langchain-upstage 0.7.3 has requirement langchain-core<0.4.0,>=0.3.29
```

## Diagnosis

- langchain-google-genai 4.x가 `langchain-core 1.x` 요구
- 다른 langchain 패키지들은 `langchain-core <1.0` 요구
- 호환 불가

## Root Cause

langchain ecosystem의 patch number 정책 차이. langchain-google-genai가 langchain-core 1.0 출시 후 빠르게 4.x로 jump했지만, 다른 langchain 패키지(langchain, langchain-openai, langchain-text-splitters, langchain-upstage)는 아직 0.3.x stable line 유지.

## Fix

langchain-google-genai를 2.x로 다운그레이드 (0.3.x langchain-core 호환):

```powershell
pip install "langchain-google-genai>=2,<3"
# 2.1.12 설치됨

pip install "langchain-core>=0.3.74,<0.4"
# 0.3.86 복원

pip check
# No broken requirements found
```

`pinned.txt`에 `langchain-google-genai>=2,<3` 추가.

## Verification

```powershell
python -c "from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI; print('ok')"
# ok

pip check
# No broken requirements found
```

## Lesson

- 단일 패키지 install이 transitive 의존성 (langchain-core)을 변경하면 다른 패키지에 영향. `pip check` 항상.
- 큰 ecosystem (langchain, huggingface, etc.) 안에서 한 패키지만 최신 버전 가는 건 위험.
- 호환 가능한 동일 라인 (예: langchain-core 0.3.x로 일관) 유지가 우선.

---
