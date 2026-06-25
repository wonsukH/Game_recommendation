# ISSUES.md — 발견된 파이프라인 이슈 + 진단 + 해결

본 문서는 후속 연구 진행 중 발견된 **파이프라인 관련 이슈 14건**의 진단/해결 기록.
시각화/UI 관련 이슈(streamlit-agraph physics tuning, plotly hover 보강 등)는 본 문서에서 제외.

각 이슈는 6 섹션:
- **Symptom** — 사용자가 본 현상 / 에러 메시지
- **Diagnosis** — 어떻게 좁혀나갔나 (로그, 측정, 실험)
- **Root Cause** — 진짜 원인 + 코드 위치
- **Fix** — 해결 방법
- **Verification** — fix가 작동함을 어떻게 확인
- **Lesson** — 재발 방지 / 패턴 / 더 일반적 교훈

---

## Issue #1: 새 venv에서 의존성 충돌 (`tokenizers` strict constraint)

### Symptom

옛 27기 팀 venv는 정상 동작. 새로 만든 `.venv`에서 `pip install -r pinned.txt` 시도 시 ResolutionImpossible 에러:

```
langchain-upstage 0.7.3 has requirement tokenizers<0.21.0,>=0.20.0
sentence-transformers 5.5.1 has requirement tokenizers>=0.21
```

### Diagnosis

1. `pip check`로 27기 venv 검사 → 같은 충돌이 이미 존재. 다만 27기는 strict resolver 적용 전 staged install로 받아들여진 broken state.
2. langchain-upstage 최신 0.7.7도 `tokenizers<0.21.0` 제약 그대로 → 패키지 메인테이너가 풀어주지 않음.
3. 새 venv는 pip 26.x strict resolver라 충돌 거부.

### Root Cause

`pinned.txt`의 `sentence-transformers==5.5.1`이 `tokenizers>=0.21` 요구. 같은 파일에 `langchain-upstage==0.7.3`은 `tokenizers<0.21` 요구. **두 패키지가 본질적으로 호환 불가**.

### Fix

`pinned.txt`에서 다음 3 라인을 relax:
- `sentence-transformers==5.5.1` → `sentence-transformers>=4.0,<5`
- `tokenizers==0.22.2` → `tokenizers<0.21`
- `transformers==5.9.0` → `transformers>=4.41,<5`
- 추가로 `huggingface_hub<1.0`, `safetensors<0.6` (transitive 호환)

sentence-transformers 4.x는 `tokenizers<0.21` 호환 → 두 패키지 화해.

### Verification

```powershell
.\.venv\Scripts\python.exe -m pip check
# "No broken requirements found"

.\.venv\Scripts\python.exe -c "from langchain_upstage import UpstageEmbeddings; from sentence_transformers import SentenceTransformer; print('ok')"
# "ok"

.\.venv\Scripts\python.exe -m pytest tests/
# 49 passed (이후 55 passed)
```

### Lesson

- "옛 venv가 작동한다"는 것이 의존성 그래프가 valid함을 의미하지 않음. broken state도 staged install로 들어오면 runtime OK.
- 다른 환경 재구성 시 `pip check`를 첫 검증으로.
- 두 패키지의 strict 제약이 충돌하면 둘 중 하나를 다운그레이드 (`langchain-upstage`가 메인테이너 정책상 제약 유지하니 sentence-transformers를 양보).

---

## Issue #2: Upstage API 키 정지 → 시스템 전체 마비

### Symptom

`text_alignment.py` 실행 중 다음 에러:

```
openai.PermissionDeniedError: Error code: 403
{'error': {'message': 'API key suspended due to insufficient credit.
  Register your payment method at https://console.upstage.ai/billing
  to continue.', 'code': 'api_key_is_not_allowed'}}
```

같은 키를 사용하는 `ChatUpstage` (parser, response_generator)도 동시 마비.

### Diagnosis

1. Upstage 결제 정보 정지로 API key 차단.
2. `text_alignment` (Solar embedding 호출) + `ChatUpstage` (parser/response 호출) 둘 다 같은 키 사용.
3. **시스템 전체가 단일 LLM 인프라에 결합**되어 있음.

### Root Cause

`UPSTAGE_API_KEY` 하나로 두 종류 호출(embedding + chat)을 모두 처리. 다른 LLM 제공자로의 fallback 분기 없음.

코드 위치:
- `pipeline/game_rec/models/text_alignment.py` (Solar embedding)
- `pipeline/game_rec/agent/retriever.py` (runtime Solar embedding for vibe phrase)
- `serving/main.py` (ChatUpstage init)

### Fix

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

### Verification

- `python -m pipeline.game_rec.models.text_alignment` → exit 0, `W_align.npy` shape (3072, 128)
- Streamlit 실행 → parser/response 모두 Gemini로 동작
- pytest 55건 통과

### Lesson

- 외부 LLM API 의존 시 결제/quota 정지 가능성 항상 염두. fallback 경로 또는 모델 swap 용이성 설계 필요.
- "embedding"과 "chat" 두 호출 종류를 같은 인프라에 묶지 말기. 각각 다른 제공자 가능.
- `.env`에 모델명을 명시 (코드 hardcode X) → 모델 교체 시 `.env`만 변경.

---

## Issue #3: Normalizer가 "Dark Souls 3"를 "DARK SOULS II"로 잘못 매핑

### Symptom

사용자가 "다크 소울 시리즈 말고 비슷한 거 추천해줘" 입력 → parser가 정확히 `["Dark Souls", "Dark Souls 2", "Dark Souls 3"]` 추출. 하지만 normalizer가 **셋 다 "DARK SOULS II"로 매핑** → seed가 사실상 1개 → 결과가 빈약.

### Diagnosis

1. `normalizer.py:25`의 `find_best_match`는 Jaccard bigram similarity 사용.
2. 수동 측정:
   - `"Dark Souls 3"` vs `"DARK SOULS II"` Jaccard = 0.769
   - `"Dark Souls 3"` vs `"DARK SOULS III"` Jaccard = 0.769 (**동점**!)
3. bigram set에서 `"ii"`와 `"iii"`가 둘 다 1개 element (중복 제거). 차이가 사라짐.
4. tie-breaker가 first-come(코드 line 33의 `> best_score`, not `>=`). `canonical_titles` 순서에서 II가 III보다 앞 → 항상 II.

### Root Cause

`pipeline/game_rec/agent/nodes/normalizer.py:8-23`의 `jaccard_similarity`가 string을 그대로 bigram화. roman numeral과 arabic numeral의 차이를 bigram set이 못 잡음.

### Fix

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

### Verification

```
"Dark Souls 2" → DARK SOULS II  (Jaccard 1.0)
"Dark Souls 3" → DARK SOULS III (Jaccard 1.0)   ← 정확 매핑
```

streamlit에서 같은 쿼리 다시 → seed에 DS II + DS III 모두 매핑 (unique 2개) → series filter (Issue #6 fix와 결합)로 시리즈 전체 제외.

### Lesson

- 문자열 유사도 알고리즘 선택 시 도메인 특성 고려. 게임 title은 roman/arabic, ™ symbol, colon 등 노이즈 많음.
- Character bigram은 짧은 substring 차이를 못 잡음. canonical form preprocessing이 필수.
- 정규식 치환 순서: 긴 패턴 먼저 (III → II 전에).

---

## Issue #4: PPMI 학습이 binary X 사용 → 매크로 분류 오류

### Symptom

DS II 기준 cosine top 10에 **`Outbreak: The Nightmare Chronicles`** (좀비 horror co-op)가 등장. cosine 0.918, rank 8/9955. 정통 후계 `Elden Ring`은 cosine 0.916 (rank 12)로 더 낮음. 사용자 직관: "Outbreak이 Elden Ring보다 다크 소울에 가깝다고?"

### Diagnosis

1. 코드 확인: `pipeline/game_rec/models/tag_embeddings.py:19`의 `--matrix` default가 `outputs/X_game_tag_csr.npz` (binary).
2. `outputs/X_game_tag_weighted.npz` (vote-count weighted)는 만들어져 있지만 학습에서 미사용.
3. binary X는 element가 0 또는 1. `Outbreak`이 "Souls-like" 태그를 1표 받았든 50000표 받았든 둘 다 1로 처리.
4. PPMI 계산 시 메인 태그와 곁다리 태그 구분 X → "Souls-like" 태그가 약하게 voted된 niche 게임이 강하게 voted된 main 게임과 같은 카테고리로 묶임.

### Root Cause

`pipeline/game_rec/models/tag_embeddings.py:19`, `pipeline/game_rec/models/game_vectors.py:22`의 default 경로가 binary X (`X_game_tag_csr.npz`). weighted X는 만들어 두고 사용 안 함.

### Fix

두 파일의 default를 weighted matrix로 변경:

```python
# tag_embeddings.py:19, game_vectors.py:22
parser.add_argument(
    "--matrix", type=str,
    default=str(Path("outputs/X_game_tag_weighted.npz")),
    help="Input CSR matrix path. Default uses vote-count weighted X ..."
)
```

`compute_ppmi_matrix(X, game_weights)` 함수 자체는 변경 0 (sparse matmul `X.T @ X`는 dtype 무관).

### Verification

DS II cosine 측정 (전후):

| 게임 | Before (binary) | After (weighted) | 변화 |
|---|---|---|---|
| DS II ↔ DS III | 0.960 | **0.971** | ↑ |
| DS II ↔ Elden Ring | 0.916 | **0.932** | ↑ (top-10 진입) |
| DS II ↔ Outbreak | 0.918 (rank 8) | **0.846** | ↓ (top-10에서 빠짐) |
| DS II ↔ Lies of P | rank 외 | **0.933 (top-10)** | ✅ |
| DS II ↔ Dragon's Dogma | rank 외 | **0.943 (top-10)** | ✅ |

매크로 카테고리 오류 해소.

### Lesson

- 데이터를 만들어 두고 학습에서 사용하지 않으면 dead asset. M3.1에서 weighted X를 만들었지만 학습 코드 갱신을 잊음.
- vote count weight는 "메인 태그 vs 곁다리 태그" 신호로 매우 강력. binary는 모든 태그를 동등 처리 → 매크로 분류 오류 위험.
- Spot check (cosine top-10)로 정량 진단 가능. 사용자가 잘 알 만한 게임 시드로 점검하는 게 효과적.

---

## Issue #5: faiss_index가 옛 vector로 build되어 추천 결과 noise

### Symptom

weighted X PPMI 재학습 후 streamlit에서 `"다크 소울 시리즈 말고"` 쿼리 → 후보 200개에 **Cookie Clicker, Poop Clicker, Mini Metro, Insaniquarium, AdVenture Capitalist** 같은 idle/clicker 게임 등장. 새 vector 기준이면 절대 들어올 수 없는 게임들.

### Diagnosis

1. `outputs/`와 `serving/data/`의 `game_vecs.npy` MD5 hash 비교 → **일치** (sync OK).
2. 후보 게임의 새 game_vec cosine 측정:
   - Cookie Clicker ↔ DS II = 0.752 (rank 7349/9955)
   - Poop Clicker ↔ DS II = 0.793 (rank 4950/9955)
   - top 200 cutoff cosine = 0.894 → 이 게임들 절대 들어올 수 없음
3. 그런데 streamlit이 그것을 후보로 보고 있음 → **faiss_index가 새 게임 vector를 가지고 있지 않음**.
4. faiss는 자체적으로 vector copy를 가짐. search 시 그 vector 기준 nearest neighbors 반환.

### Root Cause

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

### Fix

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

### Verification

```powershell
python -m pipeline.game_rec.index.faiss_index   # default = outputs/
python scripts\sync_data.py
```

`outputs/faiss_index.faiss`와 `serving/data/faiss_index.faiss` hash 일치 + 새 game_vecs 기반. streamlit 재시작 후 같은 쿼리 → Lords of the Fallen, Lies of P, Dragon's Dogma 같은 정통 후보 등장 (Cookie Clicker 류 사라짐).

### Lesson

- 학습 stage(`outputs/`)와 서빙 stage(`serving/data/`) 사이의 경계가 어디인지 명시적이어야. 학습은 outputs/만 건드리고 sync_data만 serving/data로 promote.
- 새 stage 추가 시 입력 경로가 어디인지 확인. default 경로가 옛 데이터를 가리키면 silent mismatch.
- "동일한 파일명이 두 디렉토리에 있을 때, 어느 것이 source of truth인지" 명확해야.

---

## Issue #6: "X 시리즈 말고" 쿼리에서 응답 1개만 등장

### Symptom

사용자가 "다크 소울 시리즈 말고 비슷한 거 추천해줘" 입력 → LLM 응답에 게임 **1개만** 등장 (예: "Outbreak: The Nightmare Chronicles"). rerank top 5 다 있어야 하는데.

### Diagnosis

1. UI의 rerank_node expander 펼침 → DataFrame 보임 → 5개 게임 있음 (Prepare to Die, Remastered, Lords of the Fallen, DS III, Scholar of the First Sin)
2. 그런데 response_generator의 응답은 1개만.
3. response prompt 확인: "Do not mention any other games" 명시. 5개 중 시리즈 4개(Prepare, Remastered, III, Scholar)는 사용자가 "시리즈 말고" 했으니 LLM이 빼버린 것 → 1개(Lords of the Fallen)만 남음.
4. parser가 게임명 1개만 추출(`["Dark Souls"]`). normalizer가 DS II로 매핑. similar_node가 seed_appids = {DS II} 1개만 제외 → 다른 DS 시리즈는 후보 200개에 포함.

### Root Cause

`pipeline/game_rec/agent/retriever.py`의 `recommend_similar`가 seed_appids 1개만 candidate에서 제외. **"시리즈 전체"라는 개념을 모름**. seed의 변형(Prepare to Die, Remastered, Scholar 등)이 후보에 그대로 들어가서 rerank top에 차지. LLM이 후처리로 시리즈 제거 → 응답 1개.

### Fix

`recommend_similar`에서 seed 게임의 **title prefix**를 추출해 후보 단계에서 자동 제외:

```python
_SERIES_SUFFIX_RE = re.compile(r"\s+(?:[ivx]+|\d+)(?:\s|:|$)|\s*:\s*")

def _series_prefix(title):
    """'DARK SOULS II' -> 'dark souls'"""
    t = str(title).lower().strip()
    parts = _SERIES_SUFFIX_RE.split(t, maxsplit=1)
    return parts[0].strip()

# recommend_similar 안:
canonical_titles = [...]  # seed의 정규화된 title
prefixes = {p for p in (_series_prefix(t) for t in canonical_titles) if len(p) >= 4}

excluded = set(seed_appids)
if prefixes:
    title_lower = self.games_df['game_title'].astype(str).str.lower()
    mask = pd.Series(False, index=self.games_df.index)
    for p in prefixes:
        mask |= title_lower.str.contains(p, na=False, regex=False)
    excluded |= set(self.games_df.index[mask].tolist())

distances, indices = self.faiss_index.search(query_vector, top_k + len(excluded))
candidate_appids = [self.idx_to_appid[i] for i in indices[0] if self.idx_to_appid[i] not in excluded]
```

길이 4 이상 prefix만 사용 (너무 짧은 generic prefix 방지).

### Verification

같은 쿼리 → rerank top 5:
```
ELDEN RING
Monster Hunter: World
Sekiro: Shadows Die Twice - GOTY Edition
Black Myth: Wukong
The Witcher 3: Wild Hunt
```

DS 시리즈 5개 모두 후보 200에서 빠지고 정통 비-시리즈 후계작이 진입. LLM이 5개 다 응답에 사용 (Issue #8 fix와 결합).

### Lesson

- LLM에 의존하는 부분(post-hoc filtering)은 fragile. **결정론적 logic으로 candidate 단계에서 제외**가 더 안정적.
- "시리즈" 개념은 데이터에 없지만 title의 prefix로 추론 가능. heuristic이 명확한 효과.
- 사용자 의도("X 시리즈 말고")가 명시적이면 그것을 시스템 차원에서 명시적으로 처리.

---

## Issue #7: Rerank novelty 슬라이더가 작은 값에서도 유명 게임 과도하게 죽임

### Symptom

입문자 프리셋 (relevance=9, novelty=2, serendipity=1, diversity=4) 사용 시 추천 top 5에 `Elden Ring`, `Lies of P` 같은 정통 인기작이 없고 `Blade of Darkness`, `Immortal: Unchained`, `Arx Fatalis` 같은 niche 게임이 등장. novelty=2 (작은 값) 인데도 popularity 큰 게임을 과도하게 penalty.

### Diagnosis

기존 rerank 공식 (`retriever.py:rerank_candidates`):
```python
base = (w_rel * rel + w_nov * nov + w_ser * ser) / (w_rel + w_nov + w_ser)
```

모든 weight가 양수 → `novelty=0`이어야 popularity 영향 없음. 사용자는 슬라이더 **5**(중간)를 neutral로 인식 → 5보다 작은 값(2)도 "약한 novelty"가 아니라 의도와 다른 동작.

또 linear weight → 슬라이더 1 차이가 일정한 효과. "4 vs 6은 약하게, 9 vs 10은 강하게" 의도와 불일치.

### Root Cause

`pipeline/game_rec/agent/retriever.py:rerank_candidates`의 weight 해석이 "positive only" — neutral 개념 없음. 사용자 멘탈 모델(5=neutral, 양 끝=강한 효과)과 불일치.

### Fix

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

### Verification

입문자 (rel=9, nov=2):
- `nov_mod = sigmoid_modifier(2) = -0.65` (popular 우대)
- `Elden Ring` (popular): nov_centered=-1 → contribution = (-0.65)(-1) = +0.65 boost
- `Blade of Darkness` (niche): nov_centered=+1 → contribution = -0.65 penalty

→ Elden Ring/Sekiro/Witcher 3/MH World/Wukong 같은 정통 인기작이 top 5에 자연스럽게 등장.

pytest: 49 → **55건** 통과.

### Lesson

- 사용자 UI mental model을 코드와 align. "5=중립"이 직관이면 코드도 5에서 부호 바뀌게.
- Linear scale은 모든 구간에서 동등 효과. Sigmoid는 양 끝에 자유도. 사용자 선택권.
- 슬라이더 의미를 코드 주석/UI tooltip에 명시 ("0=popular 우대, 5=neutral, 10=niche 우대").

---

## Issue #8: LLM이 rerank top 5 중 3개만 응답에 mention

### Symptom

rerank top 5 = (Lords of the Fallen, Blade of Darkness, Dragon's Dogma, Immortal: Unchained, Arx Fatalis). 그런데 response_generator 응답은 첫 3개(Lords, Dragon, Blade)만 mention. 나머지 2개 누락.

### Diagnosis

1. `prompts/response_generator.txt` 확인:
   ```
   1. You MUST only explain and select from the games provided in the list below.
      Do not mention any other games.
   ```
2. **"5개 다 mention"은 강제하지 않음**. LLM이 임의로 일부 선택 가능.
3. Gemini default temperature ~1.0 → 응답 가변성 큼.

### Root Cause

- `prompts/response_generator.txt` rule이 "다른 게임 mention 금지"는 있지만 "주어진 모든 게임 mention" 강제는 없음.
- `serving/main.py`의 `ChatGoogleGenerativeAI` init이 temperature 명시 안 함 → default ~1.0 (gemini family).

### Fix

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

### Verification

같은 쿼리 재시도 → 5개 모두 응답에 등장:
- Elden Ring
- Monster Hunter World
- Sekiro
- Witcher 3
- Black Myth: Wukong

(Issue #6 fix와 결합된 결과)

### Lesson

- LLM 강제 사항은 prompt에 명시적으로. "Do not X"만으로는 "Must do Y"가 강제 안 됨.
- Temperature 낮추면 deterministic 응답. 정해진 list를 정확히 반환해야 할 때 (`temperature=0.2`).
- prompt rule 단위 테스트 가능: 5개 게임 → 5 bullet point인지 응답 파싱 검증.

---

## Issue #9: `steam_games_tags.csv` 1031 rows vs 새 9956 게임 → KeyError 2855

### Symptom

streamlit 첫 실행 시 vibe 쿼리 던지면 `recommend_vibe`의 line 192에서 KeyError:

```
KeyError: np.int64(2855)
File "pipeline/game_rec/agent/retriever.py", line 192:
    candidate_appids = [self.idx_to_appid[i] for i in indices[0]]
```

### Diagnosis

1. `retriever.py`의 `_load_data`:
   ```python
   self.games_df = pd.read_csv("steam_games_tags.csv").set_index('appid')
   self.idx_to_appid = {i: appid for i, appid in enumerate(self.games_df.index)}
   ```
2. `serving/data/steam_games_tags.csv` row 수 = **1031** (옛 베이스라인 시절)
3. `index_maps.json` appid 수 = **9956** (새 SteamSpy)
4. faiss search가 row 2855 반환 → `idx_to_appid[2855]` KeyError (dict에 1031개만)

### Root Cause

M3.1에서 `tag_vocab` + `game_tag_matrix`는 새 SteamSpy 기반으로 갱신했지만 **`steam_games_tags.csv` 생성 단계 누락**. 새 SteamSpy 크롤러는 `steamspy_games.csv` (raw `tags_json` dict)로 저장. 옛 베이스라인의 normalized CSV (`appid, game_title, tags, tag_count`)는 schema 다름. 두 단계 사이 변환이 안 됨.

### Fix

`scripts/build_games_tags_csv.py` 작성:

```python
def normalize_tag(tag):
    t = unicodedata.normalize("NFKC", str(tag)).lower().strip()
    t = re.sub(r"[/\s]+", "-", t)
    t = re.sub(r"-+", "-", t)
    return t

def main():
    spy = pd.read_csv("outputs/steamspy_games.csv")
    imap = json.loads(Path("outputs/index_maps.json").read_text())
    row2appid = imap["row2appid"]
    ordered_appids = [v for _, v in sorted(((int(k), v) for k, v in row2appid.items()))]
    spy_indexed = spy.set_index("appid")

    rows = []
    for appid in ordered_appids:
        if appid not in spy_indexed.index: continue
        r = spy_indexed.loc[appid]
        tags_dict = _parse_tags_json(r["tags_json"])
        tag_names = [normalize_tag(t) for t in tags_dict.keys()]
        rows.append({
            "appid": appid, "game_title": r["name"],
            "tags": ",".join(tag_names), "tag_count": len(tag_names),
        })
    pd.DataFrame(rows).to_csv("outputs/steam_games_tags.csv", index=False)
```

핵심: **`index_maps.json`의 `row2appid` 순서로 정렬**. retriever의 `idx_to_appid`와 일관성 보장.

### Verification

```powershell
python scripts/build_games_tags_csv.py
# wrote 9956 rows to outputs/steam_games_tags.csv

python scripts/sync_data.py
# serving/data/steam_games_tags.csv = 9956 rows
```

streamlit 재시작 → KeyError 사라짐. retriever가 9956 게임 다 lookup 가능.

### Lesson

- "데이터 schema 마이그레이션" 단계는 명시적으로. M3.1에서 했어야 할 일을 보완 스크립트로 따로 처리.
- 옛 산출물이 dead asset처럼 남아있으면 silent mismatch 위험. 의존 관계 명시 + sync 자동화 (Issue #5 fix와 연관).
- 추후 game_tag_matrix.py에 통합 가능 (M3.1 단계에서 자동 생성하도록).

---

## Issue #10: `quality.py`가 numpy float32 JSON serialize 실패

### Symptom

build_offline 마지막 stage `pipeline.game_rec.evaluation.quality`에서:

```
TypeError: Object of type float32 is not JSON serializable
File "pipeline/game_rec/io.py", line 63 in save_stats:
    json.dump(stats, f, ensure_ascii=False, indent=2)
```

### Diagnosis

1. weighted X 도입 (Issue #4) 후 `quality.py`가 산출하는 통계 dict에 `numpy.float32` 값 포함됨.
2. python의 기본 `json.dump`는 numpy scalar를 모름.
3. `pipeline/game_rec/io.py:58` `save_stats`에 `default=` 인자 없음.

### Root Cause

`pipeline/game_rec/io.py:58` `save_stats`:
```python
def save_stats(stats, path):
    ...
    json.dump(stats, f, ensure_ascii=False, indent=2)   # default 인자 없음
```

다른 stage들은 numpy → python float casting을 명시적으로 했지만, quality.py는 numpy 값 그대로 dict에 넣음.

### Fix

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

### Verification

```powershell
python -m pipeline.game_rec.evaluation.quality
# 정상 종료, outputs/quality_report.json 생성

python scripts/sync_data.py
```

### Lesson

- 모든 JSON serialization에서 numpy 타입 호환 default callback 두는 게 안전.
- numpy의 `.item()` 메서드는 모든 scalar 타입 (float32, int64, bool_, etc.)을 Python native로 변환.
- 단일 위치(`io.py:save_stats`)에서 처리 → 모든 stage가 자동 혜택.

---

## Issue #11: `langchain-google-genai 4.x` 설치 시 다른 langchain 패키지 4개와 충돌

### Symptom

처음 `pip install langchain-google-genai` 시도 → 4.2.2 설치되고 `langchain-core` 1.4.0으로 업그레이드됨. 그 후:

```
langchain 0.3.27 has requirement langchain-core<1.0.0,>=0.3.72
langchain-openai 0.3.31 has requirement langchain-core<1.0.0,>=0.3.74
langchain-text-splitters 0.3.9 has requirement langchain-core<1.0.0,>=0.3.72
langchain-upstage 0.7.3 has requirement langchain-core<0.4.0,>=0.3.29
```

### Diagnosis

- langchain-google-genai 4.x가 `langchain-core 1.x` 요구
- 다른 langchain 패키지들은 `langchain-core <1.0` 요구
- 호환 불가

### Root Cause

langchain ecosystem의 patch number 정책 차이. langchain-google-genai가 langchain-core 1.0 출시 후 빠르게 4.x로 jump했지만, 다른 langchain 패키지(langchain, langchain-openai, langchain-text-splitters, langchain-upstage)는 아직 0.3.x stable line 유지.

### Fix

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

### Verification

```powershell
python -c "from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI; print('ok')"
# ok

pip check
# No broken requirements found
```

### Lesson

- 단일 패키지 install이 transitive 의존성 (langchain-core)을 변경하면 다른 패키지에 영향. `pip check` 항상.
- 큰 ecosystem (langchain, huggingface, etc.) 안에서 한 패키지만 최신 버전 가는 건 위험.
- 호환 가능한 동일 라인 (예: langchain-core 0.3.x로 일관) 유지가 우선.

---

## Issue #12: `text-embedding-004` 모델이 deprecated → 404

### Symptom

`text_alignment.py` 실행 중:

```
google.api_core.exceptions.NotFound: 404 models/text-embedding-004 is not found
  for API version v1beta, or is not supported for embedContent.
```

### Diagnosis

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

### Root Cause

Google이 embedding 모델 라인을 `text-embedding-004` → `gemini-embedding-XXX`로 rebrand. 옛 모델 이름은 v1beta API에서 제거됨.

### Fix

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

### Verification

```powershell
python -m pipeline.game_rec.models.text_alignment
# Successfully embeds 447 tags
# W_align.npy shape (3072, 128) — gemini-embedding-2 차원
```

### Lesson

- LLM provider의 모델 lineup은 빠르게 변함. hardcode하지 말고 `.env` / config에서 갱신 가능하게.
- 새 환경 셋업 시 `list_models()` API로 사용 가능 모델 확인이 첫 단계.
- 모델 이름의 prefix(`models/`) 일관성 확인 — langchain wrapper가 가끔 prefix를 추가/제거.

---

## Issue #13: Streamlit `cache_resource`가 .npy 갱신 시 자동 reload 안 됨

### Symptom

파이프라인 재학습 후 streamlit 브라우저에서 R 키 누르거나 자동 reload → 결과가 옛 산출물 그대로. 새 weighted X 기반 vector가 반영 안 됨.

### Diagnosis

`serving/main.py`:
```python
@st.cache_resource
def init_recommender():
    return VectorBasedRecommender(data_path=..., embedding_model=...)
```

`@st.cache_resource`는 함수 **인자**를 hash해서 caching. `data_path` 같은 string은 hash되지만 그 경로의 **파일 내용** 변경은 추적 안 됨. 결과: streamlit process가 살아있는 동안 `VectorBasedRecommender` 인스턴스가 메모리에 남고, `__init__`에서 load한 .npy 데이터도 그대로.

### Root Cause

Streamlit cache_resource의 의도된 동작 (long-lived singleton). 파일 내용 변경 추적은 cache_resource의 책임 X. 명시적 invalidate가 필요.

### Fix

해결책 자체는 단순: **streamlit process 완전 재시작**.

```powershell
Ctrl+C    # streamlit 종료
streamlit run serving\main.py    # 다시 실행
```

브라우저 R 키 또는 auto-reload는 cache_resource를 invalidate하지 않음.

대안 (구현 안 함, future enhancement):
- `init_recommender`에 `_file_mtime` 인자 추가 (data_path/game_vecs.npy의 mtime을 hash 키로) → mtime 변경 시 cache miss
- 또는 `st.cache_resource(ttl=300)` 같은 TTL 설정

### Verification

파이프라인 재학습 + streamlit Ctrl+C → 다시 실행 → 새 산출물 반영 확인 (시각적으로 다른 추천 결과).

### Lesson

- 운영 시 산출물 갱신 → cache reset 명시적으로. 자동 reload는 불충분.
- `@st.cache_resource` vs `@st.cache_data` 선택 시: resource는 process-wide singleton (LLM, model 등), data는 input hash 기반 (DataFrame transform 등). 우리는 resource가 맞음 (recommender는 무거운 init).
- 향후 개선: data_path의 모든 file mtime을 함께 hash → 파일 변경 시 자동 cache invalidate.

---

## Issue #14: Vibe 모드 niche cluster bias (M9.A 시도 → revert → M9.C로 해소)

### Symptom

30 query 평가 (label-free `llm_vs_system.py`) 결과 — vibe 카테고리에서 **`My Beautiful Paper Smile`, `Strobophagia`, `Magnus Positive Phototaxis`, `A Detective's Novel`, `Bacteria`, `Puzzle Galaxies`** 가 카테고리 무관 **반복 등장**:

| Query (vibe 카테고리) | 우리 top 5 (실패 케이스) | LLM top 5 (정통) |
|---|---|---|
| q03 "마음 편하게 따뜻한" | Bacteria, Puzzle Galaxies, Cosmic Pioneer ... | Stardew, A Short Hike, Coffee Talk |
| q05 "짧은 로그라이크" | Bacteria, Puzzle Galaxies, The Next Door ... | Vampire Survivors, Hades, Slay the Spire |
| q12 "픽셀 RPG 감성적" | My Beautiful Paper Smile, Sanfu, Strobophagia ... | To the Moon, Stardew, Undertale, OMORI |

같은 niche 게임들이 다른 카테고리 query에 반복 등장.

### Diagnosis

1. 반복 등장 게임들의 popularity 확인: 약 890,000 owners (SteamSpy 가장 작은 owners range bucket).
2. game_vec 공간 안에서 좁고 dense한 cluster 형성 (atmospheric, psychological-horror, walking-simulator, surreal 같은 niche tag 공유).
3. 사용자 자연어 → Gemini embed → `W_align` projection → tag space → 매우 일관되게 이 niche cluster 근처로 falling.
4. 단일 강한 장르 시그널 (survival, rhythm, farming) query에서는 OK — projection이 mainstream tag로 정확히 매핑.
5. 복합/모호 자연어 (어두운+스토리, 픽셀+감성, 짧고 여운) 일 때 niche cluster로 self-bias.

### Root Cause

`pipeline/game_rec/models/text_alignment.py`의 W_align 학습 데이터가 **편향**:
- 학습 입력 = 447개 짧은 태그 wrapper 문장 (`"This is a souls-like game"`)
- 학습 target = 447개 tag_vec (PPMI+SVD)
- PPMI tag_vecs 공간에서 niche tag들이 sparse하고 강한 신호로 over-represent → Ridge가 niche 방향으로 학습 강함
- mainstream 태그(`action`, `indie`)는 PPMI에서 약화 → Ridge에서 약한 매핑
- 결과: 사용자 phrase의 자연스러운 자연어가 mainstream 매핑이 약해서 niche cluster로 falling

### Fix Path — M9.A 시도 → 의도 반대 효과 → revert → M9.C로 해소

#### 시도 1: M9.A (description input augmentation)

학습 데이터의 input을 늘려 sparse niche cluster bias를 약화하려 함. **target은 tag space에 유지** (그 게임의 top-5 vote 태그의 vote-weighted 평균 vec) — 정체성 유지.

```python
# pipeline/game_rec/models/text_alignment.py — main()에 약 25줄 추가
# Stage 2: 게임 description Gemini embed → target = top-5 vote 태그 가중평균 tag_vec
T_combined = vstack([T_tag, T_game])      # (10497, 3072)
Y_combined = vstack([Y_tag, Y_game])      # (10497, 128) — 둘 다 tag space
W = Ridge.fit(T_combined, Y_combined)
```

CLI: `--include-descriptions` (default True). 학습 데이터 447 → 10,497, Ridge R² 0.40.

#### 시도 1 결과 — **의도 반대**

`llm_vs_system.py` 30 query 평가:

| | `pre_m9a` (M9.A 전) | `a07` (M9.A 후) |
|---|---|---|
| `vibe_our_avg_pop` | 7.19M | **4.64M (-35%)** |

mainstream 추천 늘기를 의도했는데 **오히려 niche로 더 깊이 falling**.

**원인 진단**: 학습 데이터에 추가된 9956 게임 description의 자연어 분포가 **long-tail** (niche 게임이 mainstream보다 더 많음). Ridge가 다수파인 niche cluster로 더 강하게 self-bias. 학습 sample을 단순히 늘리는 게 root cause를 풀지 않고 오히려 강화.

→ **M9.A revert**: `text_alignment.py --no-include-descriptions`로 옛 방식 W_align 복원.

#### 시도 2: M9.C ablation (`ensemble_alpha`)

α ∈ {0.5, 0.7, 0.9, 1.0} variant 학습 + 평가:

| variant | overall overlap@5 | vibe_overlap@5 | vibe_our_avg_pop |
|---|---|---|---|
| α=0.5 (Item2Vec 비중 ↑) | 0.013 | 0.000 | 1.35M |
| α=0.7 (기존 default) | 0.053 | 0.040 | 4.64M |
| α=0.9 | 0.047 | 0.027 | 5.86M |
| **α=1.0 (Item2Vec OFF)** | **0.087** | **0.080** | **6.08M** |

**α=1.0이 모든 지표 best**. Item2Vec 자체가 noise였다는 결정적 증거.

원인: `user_reviews.py` 페이지네이션 issue (각 user 첫 페이지 10건만 수집) → Skip-Gram sentence 짧음 → 학습 부실 → ensemble에서 noise.

#### 시도 3: M9.D (`eta`)

η=0 (β-축 OFF) vs η=0.2: 차이 미미. R²=0.10인 약한 신호라 예상된 결과. **η=0** 채택 (단순화).

#### 최종 (Final) — 채택

`config/default.yaml`:
- `ensemble_alpha: 0.7 → 1.0`
- `eta: 0.2 → 0`
- W_align는 M9.A revert (옛 방식, tag wrapper만)

30 query 재평가:

| 메트릭 | pre_m9a → final | 변화 |
|---|---|---|
| `overlap@5` | 0.060 → **0.087** | **+45%** |
| `our_avg_pop` | 6.22M → **7.91M** | +27% |
| `vibe_overlap@5` | 0.040 → **0.093** | **+133%** |
| `vibe_our_avg_pop` | 7.19M → **9.58M** | **+33%** |
| `llm_existence_rate` | 0.987 (유지) | hallucination 0% |

vibe 모드의 niche cluster bias **사실상 해소**. mainstream 정통작이 자연스럽게 진입.

### Verification

- `outputs/llm_vs_system_final.csv` + `outputs/ablation_summary.md`
- Streamlit에서 같은 vibe 쿼리 ("어두운 분위기 RPG") → niche 반복 등장 게임들 (`My Beautiful Paper Smile` 등) 빠지고 mainstream 정통작 진입

### Lesson

- **학습 sample을 단순히 늘리는 게 root cause를 풀지 않음**. Long-tail 분포라면 다수파(niche) bias가 오히려 강화됨. M9.A는 이를 정량 검증한 negative finding.
- **Ablation으로 가설 검증**. "Item2Vec이 도움 될 거라는 직관" vs "ablation 결과 noise였음" — 정량 측정이 직관을 뒤집음.
- **데이터 부실은 알고리즘 비활성화로 해결되기도**. user_reviews 페이지네이션 issue는 Item2Vec quality에 직결 → 데이터 수집 안 고치면 알고리즘 자체 끄는 게 best.
- **β-축 (tag_effects)** 같은 약한 signal(R²=0.10)은 처음부터 의심. ablation으로 확인 후 제거.
- **시스템 정체성 우선**: M9.A target에 game_vecs 넣자는 첫 제안을 사용자가 잡아냈음. 그게 정체성 약화로 갔으면 더 큰 후폭풍. target=tag space 유지는 옳았으나 학습 분포 문제로 실패. **정체성 유지 + 효과 확인 + revert** 같은 disciplined cycle이 중요.
- Label-free 평가 framework (`llm_vs_system.py`) 가치 — 이 모든 결정을 정량 근거 위에서 가능하게 함. ground truth label 없이도 정량.

---

## Issue #15: Serendipity slider redundancy (M11에서 제거)

### Symptom

사용자가 4-axis rerank scheme (Relevance/Diversity/Novelty/Serendipity)을 검토하다 의문:
> "Serendipity는 Novelty와 너무 비슷한 신호 아니야? 둘 다 popularity 기반인데."

### Diagnosis

`Serendipity = Relevance × (1 - popularity_percentile)`의 식 분해:
- Relevance: Relevance 축에 이미 들어있음
- (1 - popularity_percentile): popularity 기반 — Novelty와 같은 source

→ Serendipity는 본질적으로 **Relevance × Novelty의 곱셈 변형**. 독립 신호 X.

또 학계 reference:
- Adamopoulos & Tuzhilin (2014): "Serendipity should not be directly optimized; it emerges from relevance + unexpectedness"
- Kotkov et al. (2016): "Serendipity = relevance + novelty + unexpectedness의 함수"

→ 학계 일반적 user-facing control은 **3-axis** (Rel/Div/Nov), Serendipity는 측정 metric용.

### Root Cause

원본 baseline이 4-metric 평가 framework (`pipeline/game_rec/evaluation/metrics.py`)을 만들었고, 그 4개를 그대로 user-facing slider로 옮긴 게 4-axis가 된 원인. **measurement metric**과 **user control axis** 구분 안 함.

## Issue #16: 추론 시 신호 결합 — Hybrid 가중 합산 + Parser lock + Tag alias

### Symptom

- "아이작의 번제처럼 어두운 스토리 게임" hybrid 쿼리 → narrative-adventure 게임 5개 추천. roguelike 정체성 사라짐.
- "한 판 한 판 짧게 즐길 수 있는 로그라이크" vibe 쿼리 → puzzle 게임 5개 추천 (klocki, Perspective). 명시 장르 무시.
- Genre Precision 측정 시 `vibe-roguelike` 카테고리 0%.

### Diagnosis

세 원인이 layered:

1. **Hybrid `recommend_hybrid` 가중 합산 (`α·seed + β·vibe`)** — vibe vector magnitude가 크면 (W_align이 narrative-adventure cluster로 매핑) seed(Isaac) 정체성 압도.
2. **`_create_query_vector`에서 명시 target_tag weight가 expand 5개 sum에 묻힘** — parser가 `rogue-like` weight 1.0 출력해도 expand 5개 (각 cosine sim ~0.5) sum이 더 큼.
3. **Parser 출력 vs vocab mismatch** — Parser가 `rogue-like` (하이픈) 출력, vocab은 `roguelike` (하이픈 X). `tag_to_idx['rogue-like']` lookup 실패 → lock 무시. q05의 추천이 lock 적용 후에도 변하지 않은 진짜 원인.

검증:
- Parser 출력 디버깅: q05 던져서 `target_tags`에 `rogue-like` (locked: true) 잘 포함 확인 → Parser는 OK
- Vocab 확인: `tag_vocab.json`에 `roguelike` 매칭, `rogue-like` 매칭 X
- 시스템 추천 niche game 5개를 LLM에 직접 물어봄 → 2개 unknown, 1개 부분 인지 → 시스템 추천 quality는 정확하지만 LLM-as-Judge가 mainstream bias로 unfair (별도 metric 제외 결정)

### Root Cause

- **C1**: `pipeline/game_rec/agent/retriever.py:recommend_hybrid` — 두 벡터 단순 가중 합 + magnitude 정규화 없음
- **C2**: 같은 파일 `_create_query_vector` — normalize 없이 `vec * weight` 합산 → magnitude 큰 expand cluster가 dominant
- **C3**: 같은 파일 `expand_query_tags` — `tag_to_idx[name]` 직접 조회, format drift 처리 없음

### Fix

3 단계 변경 + 각 단계 평가 재실행으로 효과 검증:

**Step 1 — Hybrid 2-stage retrieval**:
- Stage 1: seed로 FAISS coarse search → Isaac 근처 200 후보 (시리즈 자동 제외 포함)
- Stage 2: rerank 단계 `rel = min(cos_seed, cos_vibe)` (vibe는 추가 signal)
- → Seed 정체성을 pool로 한정

**Step 2 — 동적 lock weight + L2 normalize**:
- 모든 tag vector L2 normalize 후 weight 곱
- `locked: true` flag 분리
- 동적: `per_lock_weight = max(non_lock_sum × 2.0, 2.0)` → 비율 일정
- Parser prompt: `target_tags`에 `"locked": true` flag만 (weight는 retriever 계산)

**Step 3 — Normalizer 노드의 책임 확장 (parser ↔ vocab format drift)**:
- 기존 `game_name_normalizer_node`는 **게임명만** canonical 매핑 ("Dark Souls 3" → "DARK SOULS III"), 태그명은 미처리
- 그 결과 Parser가 `rogue-like` 출력, vocab은 `roguelike` → `tag_to_idx` lookup silent fail → lock 무시
- 해결: normalizer 노드의 책임을 entity 전체로 확장. `target_tags`·`avoid_tags`도 normalize. `_resolve_tag` helper(하이픈/언더스코어 normalize 후 vocab 매칭)를 normalizer에서 호출
- 이후 router/recommender는 "이미 canonical entity만 들어온다"는 contract에 의존 가능
- 교훈: **Agent flow의 entity normalize는 한 노드에서 일관 처리**. 책임 범위가 좁으면 다른 entity의 format drift가 silent fail로 누적됨

### Verification

3 fix 누적 효과 (Genre Precision, Steam vote 기반 객관 측정):

| | 처음 | Step 1+2 | + Step 3 |
|---|---|---|---|
| Genre Precision (전체) | 76.7% | 87.3% | **90.7%** |
| vibe-roguelike | 0% | 0% | **100%** |
| vibe-stealth | 0% | 100% | 100% |
| vibe-pixel-rpg | 20% | 100% | 100% |

q05 추천 변화 (alias fix 후):
- 옛: The Cat and the Coup, Trauma, Through Abandoned, The White Door, Ramify (puzzle/narrative)
- 새: Unalive, Fancy Skulls, Not The Robots, Star Chronicles, Never Split the Party (정통 roguelike, Steam 태그 100% rogue-like 보유 확인)

### Lesson

- **추론 시 query vector 결합도 학습 시 신호 강도 통제와 같은 원리.** 두 신호 단순 합산은 magnitude 큰 쪽이 압도. 의도 명확한 신호(seed game, 명시 장르)는 약한 vibe 신호에 묻히지 않도록 구조적 보장 필요.
- **고정 weight (예: lock=2.0)는 깨지기 쉬움.** 다른 태그 개수가 늘면 다시 묻힘. **비율 보존 (lock = non_lock_sum × ratio)** 이 robust.
- **Parser 출력과 vocab 사이의 format drift는 silent failure.** Parser가 lock을 잡았다고 보고해도 vocab과 매칭 안 되면 무시됨. **fuzzy alias 매핑이 안전망.**
- **시스템 추천 객관 검증 (Steam vote 기반 태그)이 LLM-as-Judge보다 더 fair.** LLM-as-Judge는 niche indie game을 LLM이 모를 때 unfair → 별도 metric으로 제외 결정 (portfolio_content.md에 자기 검증 사례로 명시).

### Fix

`pipeline/game_rec/agent/retriever.py:rerank_candidates`에서 Serendipity 계산 부분 제거:
- `ser_raw / ser / ser_centered / ser_mod` 변수 제거
- `base = rel_contrib + 0.5 × nov_mod × nov_centered + 0.5 × ser_mod × ser_centered` → `0.5 × nov_mod × nov_centered`만 남김

UI/config/평가 코드 3축으로:
- `serving/ui.py`: 4 slider → 3
- `config/default.yaml`: presets 3축
- `pipeline/orchestration/llm_vs_system.py` PRESETS: 3축
- `pipeline/game_rec/evaluation/metrics.py`: Serendipity@K 함수 **유지** (측정용)

또 입문자 프리셋 `novelty: 2 → 1` 보정 (Serendipity 1 (음수 modifier)이 제공하던 popular boost를 nov로 약간 보강).

### Verification

label-free 30 query 평가 (`outputs/llm_vs_system_final3.csv`):

| 메트릭 | 4-axis (final) | 3-axis (final3) | pre_m9a (baseline) |
|---|---|---|---|
| overlap@5 | 0.087 | 0.067 | 0.060 |
| vibe_overlap@5 | 0.093 | 0.080 | 0.040 |
| vibe_our_avg_pop | 9.58M | 7.38M | 7.19M |

3-axis가 4-axis 대비 약간 부진 (Serendipity가 popular boost에 기여하고 있었음). 그래도 baseline 대비 명확 우세 (vibe_overlap +100%).

### Lesson

- **measurement metric ≠ user control axis**. 측정에 유용한 metric 4개라고 해서 user에게 4개 slider 줄 필요 X. control axis 설계 시 신호 간 redundancy 검토 필요.
- 학계 표준 follow하는 게 일반적으로 안전. 단 정량 측정으로 검증.
- 정량 vs UX 트레이드오프: 4-axis가 정량 best였지만 UX/학계 표준은 3-axis. 사용자/팀의 우선순위에 따라 결정. 본 시스템은 **simplicity + standard** 우선 → 3-axis.

---

## 정리 — 발견 패턴

위 15건의 issue를 카테고리로 분류:

| 카테고리 | Issues | 패턴 |
|---|---|---|
| **의존성 관리** | #1, #11, #12 | 외부 패키지/API 정책 변경에 코드가 hard-coupled — `.env` / config 추출이 답 |
| **데이터 mismatch** | #5, #9 | outputs/ ↔ serving/data/ 경계 모호 → 자동 sync로 해소 |
| **알고리즘 / 학습 결과** | #3, #4, #7, #14 | 시스템이 "사람의 직관"과 다르게 동작 → spot check + label-free 평가로 발견 |
| **LLM prompt 강제 부족** | #6, #8 | "Do not X" 만으론 부족, "Must do Y"도 명시 + temperature 낮춤 |
| **인프라 / 운영** | #2, #10, #13 | 외부 의존성, JSON edge case, cache invalidation |
| **User control 설계** | #15 | measurement metric ≠ user-facing control axis. 신호 redundancy 검토. 학계 표준 follow |

### 공통 디버깅 패턴

1. **Symptom을 정확히 reproduce** (spot check 가능한 쿼리/명령)
2. **수동 측정** (cosine, vote count, JSON shape)으로 root cause 좁힘
3. **코드 위치 명시** + 잘못된 가정을 명시
4. Fix는 **가장 작은 침투** 선호 — 1 파일, 한 함수, 몇 줄
5. **Verification은 정량적으로** — 전후 비교 표

### 가장 큰 교훈

- **Label-free 평가 framework**(LLM vs 시스템)가 ground-truth 라벨 없이도 정량 측정 가능 → niche bias 같은 약점을 발견하게 해줌. 평가 인프라 자체가 자산.
- 시스템 **정체성(태그 기반 추천)** 을 모든 변경의 1급 기준으로 사용 → "더 좋은 결과" 추구가 정체성 약화로 가지 않게.
- 옛 산출물이 dead asset처럼 남아 있으면 silent mismatch 위험 (Issue #5, #9). 의존 관계 명시 + auto sync.
- **Algorithm activation도 ablation으로 결정** (Issue #14의 M9.C/D). "더 많은 signal = 더 좋은 결과" 직관 의심. 약한 signal (Item2Vec, β-축)은 ablation으로 검증 후 비활성화. 단순함이 정량적으로 best일 때 있음.
- **데이터 quality 부족은 알고리즘 비활성화로 해결되기도** (Issue #14). user_reviews 페이지네이션 fix가 정공법이지만, sentence 짧음 → Item2Vec 비활성이 임시 best. 데이터 fix 비용 큰 경우의 차선책.
- **추론 시 신호 결합도 학습 시 신호 강도와 같은 원리** (Issue #16). 두 신호 단순 합산 X — 비율 보존 + L2 normalize + format drift 안전망 (alias 매핑). 고정 weight 대신 동적 (`max(non_lock_sum × ratio, floor)`).
- **잘못된 metric을 의도적으로 제외하는 자기 검증** (Issue #16). LLM-as-Judge가 unfair한 결과 낼 때 그 metric을 portfolio에서 빼는 결정도 평가 framework의 일부. 모든 측정이 fair한 건 아님.
