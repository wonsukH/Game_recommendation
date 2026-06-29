# Issue #13: Streamlit `cache_resource`가 .npy 갱신 시 자동 reload 안 됨

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md) · 정본: [README.md](../../README.md) · [ROADMAP.md](../ROADMAP.md)


## Symptom

파이프라인 재학습 후 streamlit 브라우저에서 R 키 누르거나 자동 reload → 결과가 옛 산출물 그대로. 새 weighted X 기반 vector가 반영 안 됨.

## Diagnosis

`serving/main.py`:
```python
@st.cache_resource
def init_recommender():
    return VectorBasedRecommender(data_path=..., embedding_model=...)
```

`@st.cache_resource`는 함수 **인자**를 hash해서 caching. `data_path` 같은 string은 hash되지만 그 경로의 **파일 내용** 변경은 추적 안 됨. 결과: streamlit process가 살아있는 동안 `VectorBasedRecommender` 인스턴스가 메모리에 남고, `__init__`에서 load한 .npy 데이터도 그대로.

## Root Cause

Streamlit cache_resource의 의도된 동작 (long-lived singleton). 파일 내용 변경 추적은 cache_resource의 책임 X. 명시적 invalidate가 필요.

## Fix

해결책 자체는 단순: **streamlit process 완전 재시작**.

```powershell
Ctrl+C    # streamlit 종료
streamlit run serving\main.py    # 다시 실행
```

브라우저 R 키 또는 auto-reload는 cache_resource를 invalidate하지 않음.

대안 (구현 안 함, future enhancement):
- `init_recommender`에 `_file_mtime` 인자 추가 (data_path/game_vecs.npy의 mtime을 hash 키로) → mtime 변경 시 cache miss
- 또는 `st.cache_resource(ttl=300)` 같은 TTL 설정

## Verification

파이프라인 재학습 + streamlit Ctrl+C → 다시 실행 → 새 산출물 반영 확인 (시각적으로 다른 추천 결과).

## Lesson

- 운영 시 산출물 갱신 → cache reset 명시적으로. 자동 reload는 불충분.
- `@st.cache_resource` vs `@st.cache_data` 선택 시: resource는 process-wide singleton (LLM, model 등), data는 input hash 기반 (DataFrame transform 등). 우리는 resource가 맞음 (recommender는 무거운 init).
- 향후 개선: data_path의 모든 file mtime을 함께 hash → 파일 변경 시 자동 cache invalidate.

---
