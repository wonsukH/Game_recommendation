# Issue #5: faiss_index가 옛 vector로 build되어 추천 결과 noise

> **유형**: bug-log · **상태**: deprecated · **갱신**: 2026-06-29
> 상위: [ISSUES.md](../ISSUES.md)


## Symptom

weighted X PPMI 재학습 후 streamlit에서 `"다크 소울 시리즈 말고"` 쿼리 → 후보 200개에 **Cookie Clicker, Poop Clicker, Mini Metro, Insaniquarium, AdVenture Capitalist** 같은 idle/clicker 게임 등장. 새 vector 기준이면 절대 들어올 수 없는 게임들.

## Diagnosis

1. `outputs/`와 `serving/data/`의 `game_vecs.npy` MD5 hash 비교 → **일치** (sync OK).
2. 후보 게임의 새 game_vec cosine 측정:
   - Cookie Clicker ↔ DS II = 0.752 (rank 7349/9955)
   - Poop Clicker ↔ DS II = 0.793 (rank 4950/9955)
   - top 200 cutoff cosine = 0.894 → 이 게임들 절대 들어올 수 없음
3. 그런데 streamlit이 그것을 후보로 보고 있음 → **faiss_index가 새 게임 vector를 가지고 있지 않음**.
4. faiss는 자체적으로 vector copy를 가짐. search 시 그 vector 기준 nearest neighbors 반환.

## Root Cause

`pipeline/game_rec/index/faiss_index.py:28` (이전):

```python
DEFAULT_DATA_DIR = REPO_ROOT / "serving" / "data"
parser.add_argument("--vectors", default=DEFAULT_DATA_DIR / "game_vecs.npy")
parser.add_argument("--output", default=DEFAULT_DATA_DIR / "faiss_index.faiss")
```

build_offline stage 순서:
```
1. tag_embeddings   → outputs/tag_vecs.npy (새)
2. game_vectors     → outputs/game_vecs.npy (새)
3. text_alignment   → outputs/W_align.npy (새)
4. faiss_index      → serving/data/game_vecs.npy 읽음 (옛!) → serving/data/faiss_index.faiss 씀 (옛 vector로)
5. tag_projection
6. quality
   (sync_data 없음 — build_offline 밖)
```

→ Stage 4 시점에 `serving/data/game_vecs.npy`는 아직 옛 binary-X 시절. 옛 vector로 faiss build. 이후 sync_data로 `game_vecs.npy`만 새 거로 덮어쓰고 faiss는 옛 거 그대로 → mismatch.

## Fix

**(a) default 경로 변경** (`faiss_index.py:31`):
```python
DEFAULT_DATA_DIR = REPO_ROOT / "outputs"
```

**(b) build_offline 마지막 stage에 sync_data 자동 추가** (`build_offline.py`):
```python
STAGES = (
    # ... existing stages ...
    Stage("scripts.sync_data", "sync outputs/ -> serving/data/"),
)

def run_stage(stage, extra_args):
    if stage.module == "scripts.sync_data":
        cmd = [sys.executable, str(REPO_ROOT / "scripts" / "sync_data.py"), *stage.args, *extra_args]
    else:
        cmd = [sys.executable, "-m", stage.module, *stage.args, *extra_args]
    ...
```

`scripts.sync_data`는 module이 아니라 script라 `-m`으로 호출 불가 → run_stage에 분기 추가.

## Verification

```powershell
python -m pipeline.game_rec.index.faiss_index   # default = outputs/
python scripts\sync_data.py
```

`outputs/faiss_index.faiss`와 `serving/data/faiss_index.faiss` hash 일치 + 새 game_vecs 기반. streamlit 재시작 후 같은 쿼리 → Lords of the Fallen, Lies of P, Dragon's Dogma 같은 정통 후보 등장 (Cookie Clicker 류 사라짐).

## Lesson

- 학습 stage(`outputs/`)와 서빙 stage(`serving/data/`) 사이의 경계가 어디인지 명시적이어야. 학습은 outputs/만 건드리고 sync_data만 serving/data로 promote.
- 새 stage 추가 시 입력 경로가 어디인지 확인. default 경로가 옛 데이터를 가리키면 silent mismatch.
- "동일한 파일명이 두 디렉토리에 있을 때, 어느 것이 source of truth인지" 명확해야.

---
