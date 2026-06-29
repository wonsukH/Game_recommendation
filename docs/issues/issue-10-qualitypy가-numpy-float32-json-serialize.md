# Issue #10: `quality.py`가 numpy float32 JSON serialize 실패

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md)


## Symptom

build_offline 마지막 stage `pipeline.game_rec.evaluation.quality`에서:

```
TypeError: Object of type float32 is not JSON serializable
File "pipeline/game_rec/io.py", line 63 in save_stats:
    json.dump(stats, f, ensure_ascii=False, indent=2)
```

## Diagnosis

1. weighted X 도입 (Issue #4) 후 `quality.py`가 산출하는 통계 dict에 `numpy.float32` 값 포함됨.
2. python의 기본 `json.dump`는 numpy scalar를 모름.
3. `pipeline/game_rec/io.py:58` `save_stats`에 `default=` 인자 없음.

## Root Cause

`pipeline/game_rec/io.py:58` `save_stats`:
```python
def save_stats(stats, path):
    ...
    json.dump(stats, f, ensure_ascii=False, indent=2)   # default 인자 없음
```

다른 stage들은 numpy → python float casting을 명시적으로 했지만, quality.py는 numpy 값 그대로 dict에 넣음.

## Fix

`save_stats`에 numpy default callback 추가:

```python
def _json_default(o):
    """JSON encoder fallback for numpy scalars (float32, int64, etc.)."""
    if hasattr(o, "item"):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def save_stats(stats, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=_json_default)
```

전역 적용 → 다른 stats 파일도 자동으로 numpy 처리됨.

## Verification

```powershell
python -m pipeline.game_rec.evaluation.quality
# 정상 종료, outputs/quality_report.json 생성

python scripts/sync_data.py
```

## Lesson

- 모든 JSON serialization에서 numpy 타입 호환 default callback 두는 게 안전.
- numpy의 `.item()` 메서드는 모든 scalar 타입 (float32, int64, bool_, etc.)을 Python native로 변환.
- 단일 위치(`io.py:save_stats`)에서 처리 → 모든 stage가 자동 혜택.

---
