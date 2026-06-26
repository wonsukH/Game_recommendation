# 설계 의도 — 왜 이렇게 만들었는가

> ⚠️ **[폐기·이력] 이 문서는 *피벗 이전*(태그-유사도/PPMI·SVD/W_align/FAISS/Item2Vec, similar·vibe·hybrid 모드) 시스템 기준이라 현재 아키텍처와 불일치한다.** 현재 시스템(개인화 CF moat + LangGraph agent[library/seed/multi_entity/explore/anonymous] + 행동 SQLite `steam.db`)은 [`../README.md`](../README.md)·[`ROADMAP.md`](ROADMAP.md) 참조. 이 파일은 당시 설계의도의 *역사적 기록*으로만 보존(전면 갱신은 데이터층 재구축 P8 이후).

이 문서는 본 프로젝트의 **모든 결정의 이유**를 처음 보는 사람도 이해할 수 있게 풀어쓴 글이다. 수식이나 코드 디테일은 [README_PIPELINE.md](README_PIPELINE.md)에 있다. 여기서는 **"왜"**와 **"어떤 동작을 의도했는가"**에 집중.

---

## 0. 한 문장 요약

> Steam 게임을 추천하는 챗봇인데, **"태그의 의미"를 진짜로 이해하는 게 핵심**이다. 사용자가 "어두운 분위기 RPG 처음 해보고 싶어"라고 자연어로 말하면, 시스템이 "Soulslike", "Dark Fantasy", "Atmospheric" 같은 태그가 의미적으로 가까이 있다는 걸 알고, 거기 해당하는 게임을 찾아주는 시스템.

---

## 1. 왜 이 문제를 푸나

### 사용자의 진짜 어려움

게임을 잘 모르는 사람이 Steam에서 게임을 고를 때 어떤 어려움을 겪나?

- **장르 용어가 외계어**: "Soulslike", "Roguelite", "Metroidvania", "Cozy", "Vampire Survivors-like"... 이런 용어를 모르면 검색조차 못 함
- **태그 필터링은 한계**: Steam이 태그로 필터를 제공하지만, 사용자가 어떤 태그를 골라야 할지 모르면 무용
- **LLM 추천도 부족**: ChatGPT/Gemini에게 물어보면 그럴듯한 답을 주지만, **(1) 모르는 게임을 hallucinate하기도 하고, (2) 항상 유명한 게임 위주라 long-tail을 못 발굴**

### 우리 시스템의 강점

- **자연어 → 태그 자동 매핑**: 사용자가 "어두운 분위기"라고 하면 시스템이 알아서 `Dark`, `Atmospheric`, `Souls-like` 같은 태그로 변환
- **0% hallucination**: 실제 Steam에 있는 9956개 게임 안에서만 추천 (LLM과 다름)
- **long-tail 발굴**: 유명한 Elden Ring뿐만 아니라 `Blade of Darkness`, `Lords of the Fallen` 같이 덜 알려진 정통 후계작도 자연스럽게 잡음

---

## 2. 큰 그림 — 시스템이 어떻게 작동하나

### 두 부분으로 분리

이 시스템은 **(A) 오프라인 학습** + **(B) 온라인 서빙** 두 부분이다.

```
   ┌─────────────── (A) 오프라인 학습 ───────────────┐
   │                                                 │
   │  Steam에서 데이터 수집                          │
   │  ↓                                              │
   │  태그 의미 임베딩 학습 (PPMI + SVD)             │
   │  ↓                                              │
   │  게임 의미 임베딩 합성 (태그 + 사용자 신호)     │
   │  ↓                                              │
   │  자연어 ↔ 태그 사상 학습 (Gemini + Ridge)       │
   │  ↓                                              │
   │  검색 인덱스 빌드 (FAISS)                       │
   │                                                 │
   └─────────────────────────────────────────────────┘
                       ↓
   ┌─────────────── (B) 온라인 서빙 ────────────────┐
   │                                                 │
   │  사용자: "어두운 RPG 처음 해보고 싶어"          │
   │  ↓                                              │
   │  LLM이 파싱: {mode, games, phrases, ...}        │
   │  ↓                                              │
   │  게임명 정규화 + 시리즈 자동 필터               │
   │  ↓                                              │
   │  의미 임베딩 기반 후보 검색 (FAISS top 200)     │
   │  ↓                                              │
   │  사용자 슬라이더 기반 재정렬 (MMR + 4축)        │
   │  ↓                                              │
   │  LLM이 자연어로 답변                            │
   │                                                 │
   └─────────────────────────────────────────────────┘
```

### 핵심 아이디어

"의미 임베딩"이 핵심이다. 각 태그를 **128차원의 숫자 벡터**로 표현하는데, **의미가 비슷한 태그는 벡터도 가깝게** 학습된다. 예:

- `souls-like` ↔ `difficult` ↔ `dark-fantasy` (가까움)
- `souls-like` ↔ `cooking-sim` (멀리)

이 vector를 학습하는 게 가장 어려운 부분. 한 번 학습되면:
- 게임 간 유사도 (`Dark Souls` ↔ `Elden Ring` 가까움)
- 자연어 → 태그 매핑 ("어두운 분위기" → `dark`, `atmospheric`)
- 시각화 (UMAP으로 2D 지도)

가 다 가능해진다.

---

## 3. 단계별 의도

### 3.1. 데이터 수집 — 왜 SteamSpy?

**문제**: Steam 공식 API는 user-tag vote count를 안 알려준다. "이 게임에 'Souls-like' 태그를 몇 명이 달았는지" 모름.

**해결**: SteamSpy (Steam 비공식 통계 사이트)의 API가 이걸 제공함. **각 태그의 vote 수**가 핵심. 메인 태그(50000표)와 곁다리 태그(1표)를 구분할 수 있어야 PPMI 학습이 잘 됨.

**왜 풀을 1031 → 10000으로 늘렸나**:
- 원본 1031개는 Metacritic 상위 위주 → 유명한 정통작만 있고 niche/long-tail 없음
- "일반적인 추천만 나온다"는 문제는 사실 데이터 풀의 편향 때문이었음
- SteamSpy로 인기 순 10000개 (popularity 다양한 분포)로 확장 → 진짜 다양한 추천 가능

### 3.2. 태그 정규화 — 왜 필요한가

**문제**: SteamSpy 태그 이름이 일관성 없음.
- `"Action / Adventure"`, `"action-adventure"`, `"Action Adventure"` 다 다른 string

**해결**: `normalize_tag` 함수로 통일:
- 유니코드 정규화 (NFKC)
- 소문자
- 슬래시/공백 → 하이픈
- 연속 하이픈 합치기

→ 모두 `"action-adventure"`로 통일. 다운스트림에서 같은 태그로 처리.

### 3.3. 게임 가중치 — 왜 Bayesian Shrinkage?

**원래 의도**: 어떤 게임이 평균적으로 사용자에게 좋은 평가를 받는지를 PPMI 학습에 반영하고 싶음. 즉 "평점 높은 게임"의 태그 co-occurrence를 더 강하게 학습.

**문제**: 단순 평균은 노이즈 큼.
- 게임 A: 1명만 플레이, 평점 9.0 → 평균 9.0
- 게임 B: 100명 플레이, 평점 8.5 → 평균 8.5
- 그러면 A가 더 가중치 큼. 표본 1개라 신뢰성 없는데도.

**해결**: **Bayesian shrinkage**. 표본 크기 작으면 글로벌 평균으로 끌어당김.
- 글로벌 평균 6.5라면, 게임 A의 보정 평균은 `(1×9 + 10×6.5) / 11 = 6.73` (글로벌 쪽)
- 게임 B의 보정 평균은 `(100×8.5 + 10×6.5) / 110 = 8.32` (자기 평균 가까움)

**의도**: 신뢰할 수 있는 게임 평점만 강하게 반영.

### 3.4. PPMI 임베딩 — 왜 PPMI?

**원래 의도**: 태그 간 의미 관계를 학습. 같은 게임에 자주 함께 등장하는 태그는 의미가 비슷할 것이다.

**단순 co-occurrence count의 문제**:
- 모든 게임에 `"Indie"` 태그가 붙어있음 (vote 합계 매우 큼)
- 그러면 모든 태그와 `"Indie"`의 co-occurrence가 크게 잡힘
- 결과: `"Indie"`가 모든 태그와 비슷하다고 학습됨 — 의미 없음

**PPMI (Positive Pointwise Mutual Information)**:
- "같이 등장한 횟수"가 아니라 **"기대보다 많이 같이 등장했는지"**를 측정
- 일반적인 태그 (`Indie`, `Action`)는 자동으로 약화됨 — 어차피 다 같이 등장하니까
- 특수한 태그 쌍 (`Souls-like` + `Dark Fantasy`)은 강하게 학습됨 — 기대보다 훨씬 자주 같이 등장

PPMI는 NLP의 word embedding에서 검증된 기법. 우리는 "단어 = 태그", "문장 = 게임"으로 가져온 것.

### 3.5. Vote-Weighted X — 왜 바꿨나

**버전 1 (옛)**: binary matrix — 게임이 태그를 가지면 1, 아니면 0.
- 문제: Outbreak (좀비 horror)에 누가 농담으로 "Souls-like" 1표 던지면 → Dark Souls와 같은 카테고리로 묶임
- **메인 태그와 곁다리 태그를 구분 못 함**

**버전 2 (새)**: weighted matrix — element = vote count.
- Dark Souls의 "Souls-like" = 50000
- Outbreak의 "Souls-like" = 200
- PPMI 학습이 메인 태그를 더 강하게 반영 → Outbreak가 자연스럽게 Souls-like cluster에서 밀려남

**측정 결과**: Outbreak ↔ Dark Souls II cosine 0.918 → 0.846 (떨어짐, 정상). Lies of P, Elden Ring이 top-10에 진입.

### 3.6. Item2Vec — 왜 추가했나

**PPMI의 한계**: 태그가 비슷한 게임끼리만 가깝다. **"태그는 비슷하지 않지만 같은 유저가 좋아하는" 게임 신호는 못 잡음**.

예: `Dark Souls`와 `Sekiro`는 태그가 다름 (Souls-like vs Ninja Action). 하지만 Dark Souls 좋아하는 유저가 Sekiro도 좋아할 확률 매우 높음.

**해결**: Word2Vec의 SkipGram을 게임에 적용. 각 유저의 favorite 게임 목록을 "sentence"로 보고, 같은 sentence에 자주 등장하는 게임끼리 가깝게 학습.

**의도**: PPMI(태그 기반) + Item2Vec(유저 행동 기반) 두 신호를 **둘 다** 사용. 서로 다른 정보 제공.

### 3.7. Ensemble — 왜 가중평균인가

**선택**: PPMI 70% + Item2Vec 30%.

**의도**:
- PPMI가 main: 태그 의미 자체가 시스템의 1급 자산이니까
- Item2Vec은 30%만: cold-start 게임 (user 데이터 적음)에서 noise일 수 있음
- Item2Vec이 0 벡터인 게임은 자동으로 PPMI만 사용 (per-row fallback)

이 비율은 ablation으로 조정 가능. 예: α=0.9 → PPMI dominant, α=0.5 → 균형.

### 3.8. Text Alignment (W_align) — 왜 Ridge?

**문제**: 사용자가 "어두운 분위기 RPG"라고 자연어로 입력. 이걸 어떻게 태그 공간으로 변환?

**아이디어**:
1. Gemini로 "어두운 분위기 RPG"를 3072차원 vector로 임베딩
2. 그 vector를 어떻게든 우리 128차원 태그 공간으로 사영
3. 사영된 vector와 가장 가까운 태그를 찾음

**구체적 학습 방식**:
- 각 태그 이름 ("souls-like")을 sentence ("This is a souls-like game")로 만들어 Gemini 임베딩 (3072d)
- 이 3072d vector → 128d tag_vec으로 가는 **Ridge 회귀** 학습
- 결과: W_align matrix (3072 × 128). $T \cdot W \approx \text{tag\_vecs}$

**런타임**: 사용자 입력 → Gemini embed → @ W_align → 128d → 가장 가까운 tag 검색.

**왜 Ridge?**:
- 단순한 linear projection — 빠르고 안정적
- 학습 데이터가 적음 (447 태그 × 3072d) → 복잡한 model은 overfit
- L2 regularization으로 안정성

### 3.9. FAISS — 왜 IndexFlatL2?

**왜 FAISS**: 9956개 게임에서 top 200 nearest neighbors를 1ms 안에 찾으려면 brute-force matrix multiplication도 빠르지만, FAISS가 future scaling (100K+) 대비 옵션 풍부.

**왜 IndexFlatL2 (가장 단순한 종류)**:
- 정확한 거리 계산 (approximation 아님)
- 10000개 정도면 충분히 빠름
- IVF, HNSW 같은 approximate index는 데이터 양이 더 많아질 때.

### 3.10. UMAP 태그 지도 — 왜?

**의도**: 시스템의 핵심 자산 (태그 의미 임베딩)을 사용자가 시각적으로 확인할 수 있게.

- 128차원은 사람이 볼 수 없으니 2D로 압축 (UMAP)
- 같은 클러스터인 태그끼리 색깔 같게 (KMeans)
- 호버하면 그 태그의 인기 게임 Top 5

면접 demo에서 "우리 시스템이 진짜로 태그 의미를 학습했나?" 보여줄 때 효과적. `Soulslike`, `Hardcore`, `Dark Fantasy`가 한 클러스터에 모여 있으면 학습이 잘 됐다는 증거.

### 3.11. 옵시디언 스타일 Force Graph — 보너스

UMAP은 정적 좌표 (위치 자체가 의미 있음). 사용자가 노드를 끌어 옮기는 동적 시각화를 원해서 2개 페이지 추가:
- **2D**: streamlit-agraph (vis.js 기반). 옵시디언과 가장 비슷한 느낌. drag/zoom/physics
- **3D**: vasturiano의 3d-force-graph (three.js). 마우스로 3D 회전

force-directed는 좌표 자체가 의미는 없지만 "엣지가 진짜 의미적 이웃"이라 정보 손실 적음 (UMAP의 좌표 왜곡 회피).

---

## 4. 온라인 에이전트 — 왜 LangGraph?

### Pipeline 구조

```
parser → normalizer → mode-specific node → rerank → response
```

각 노드를 분리한 이유:
- **parser**: LLM이 자연어 → JSON 변환. 어떤 LLM이든 substitute 가능
- **normalizer**: "Dark Souls 3" 같은 사용자 표현을 데이터셋의 canonical title ("DARK SOULS III")에 매핑
- **mode 분기**: similar (게임명) / vibe (자연어만) / hybrid (둘 다) — 각각 다른 query vector 구성
- **rerank**: 사용자 선호 슬라이더 반영
- **response**: LLM이 자연어 답변 생성

LangGraph는 이 흐름을 명시적으로 표현. 디버깅도 쉬움 (각 노드 expander로 확인).

### Normalizer의 Roman ↔ Arabic Fix

사용자가 "Dark Souls 3"라고 하면 데이터셋은 "DARK SOULS III"로 저장됨. Jaccard bigram similarity로 매칭하는데:
- "Dark Souls 3" vs "DARK SOULS II" = 0.77
- "Dark Souls 3" vs "DARK SOULS III" = 0.77 (동점!)

"II"와 "III"의 차이가 bigram set에서 사라지기 때문. **해결**: 매칭 전에 "III" → "3"로 변환해서 정확히 일치하게.

**의도**: 사용자가 한국어로 "다크 소울 3"라고 해도 정확히 3편을 찾게.

### Series 자동 필터

사용자: "다크 소울 시리즈 말고 비슷한 거"
- 옛 방식: parser가 "Dark Souls" 1개 추출 → DS II 1개만 candidate에서 제외 → 결과에 DS Prepare, Remastered, III 등 포함 → LLM이 후처리로 제거하다 1개만 남음
- 새 방식: seed title의 prefix ("dark souls") 추출 → 전 시리즈 5개 다 candidate에서 자동 제외 → 비-시리즈 정통 후계만 top 5

**의도**: "X 시리즈 말고"를 의도대로 작동시키기.

### Rerank — Signed Sigmoid

사용자가 사이드바 슬라이더로 추천 성향 조정:
- Relevance (쿼리 일치): 0=무시, 10=최대 강조
- Diversity (다양성): 5=중립, 10=다양, 0=비슷한 류
- Novelty (새로움): 5=중립, 10=niche, 0=유명 게임 우대
- Serendipity (의외성): 같음

**왜 5가 중립?**
- 사용자가 "값을 안 건드리면 영향 없음"을 직관적으로 기대
- 옛 방식: 모든 값이 양수 weight → 5도 영향이 있음 (less popular 게임 boost) → 입문자 프리셋(nov=2)에서도 유명 게임이 너무 약하게 됨
- 새 방식: 5=neutral, >5=niche 강조, <5=popular 강조 → 직관적

**왜 sigmoid?**
- linear 변환이면 4 vs 6의 효과가 9 vs 10과 비슷 → 사용자가 "값을 살짝 바꿀 때 너무 큰 변화"
- sigmoid는 중앙(5) 근처는 약하고 양 끝(0, 10)에서 강함 → "값을 결단력 있게 양 끝으로 가야 명확한 효과"

**의도**: 슬라이더가 직관적으로 작동.

### MMR (Maximal Marginal Relevance)

후보 200개에서 top 5 뽑을 때 단순히 cosine top 5만 뽑으면 **다 비슷한 게임**.

예: DS II 시드 → top 5가 모두 DS 시리즈 변형. 사용자는 "비슷한데 다른 거"를 원함.

**MMR**: greedy로 첫 번째는 가장 cosine 높은 거. 두 번째부터는 "cosine 높지만 이미 뽑힌 게임들과 다른 거"를 선택. 즉:

```
score = (1 - λ) × cosine - λ × max(이미 뽑힌 게임과의 유사도)
```

λ는 diversity 슬라이더에서 결정. **의도**: 결과가 단조롭지 않게.

### Response Generator Prompt 강화

LLM이 5개 다 받았는데 3개만 응답에 등장하던 문제 → prompt에 명시적으로 "5개 다 mention", temperature=0.2로 deterministic.

---

## 5. 평가 — 왜 LLM 비교?

### 원래 계획: ideal label 30개 라벨링

문제: **만 개 게임을 다 알아야 30개 query에 ideal recommendation 5-10개를 정할 수 있음**. 비현실적.

### 새 framework: LLM 단독과 비교

**아이디어**: ground truth label이 없어도, "LLM 단독 추천과 우리 시스템 추천을 비교"하면 정량적으로 차이를 측정 가능.

**최종 채택 metric (외부 어필용)**:
- **Pool Coverage Miss**: LLM 추천이 도메인 풀(9,956) 외부 비율 — 운영 통합 시 dead link 위험
- **True Hallucination**: Steam Storefront API cross-check로 진짜 hallucination 분리 (Pool Miss와 다름 — 풀 외부지만 실존하는 게임이 대부분)
- **Genre Precision**: 시스템 추천이 쿼리의 명시 카테고리 태그를 보유한 비율 (Steam 사용자 vote 기반 객관 측정)

**검토했지만 의도적으로 제외한 metric**:
- **Overlap@5 / ILD**: 두 시스템 목표가 다름 (LLM=풀 외부 mainstream, 시스템=풀 내부 검증 추천)에서 비롯되는 자연 차이라 외부 어필 부적합. 내부 ablation 도구로만 활용.
- **LLM-as-Judge** (Gemini에게 "추천이 적합한가?"): 시도했지만 LLM이 niche indie game을 모를 때 unfair한 결과. 시스템이 추천한 정통 roguelike 5개를 LLM에 직접 물어봐 검증 → 2개 unknown, 1개 부분 인지 → bias 입증 → portfolio에서 제외. **잘못된 metric을 명시적으로 빼는 자기 검증도 평가 framework의 일부**.

**측정 못 하는 것**: 절대 정확도 (둘 다 추천이지 정답 아님). 다만 **상대 차이 + 객관 태그 매칭은 충분히 의미 있음**.

### 30 query 결과 요약

- **우리 시스템 추천은 100% 도메인 풀 내** (운영 통합 가능). LLM 단독은 7.3%가 풀 외부.
- **Genre Precision 90.7%** (시스템 추천이 명시 카테고리 태그를 객관적으로 정확히 매칭). 3 fix (Hybrid 2-stage + parser lock 동적 weight + tag alias 매핑)를 통해 76.7% → 90.7% 누적 개선.
- **niche 발굴은 우리만 가능** (Stardew Valley 같은 유명한 거 말고 indie 발굴) — LLM-as-Judge bias의 원인이기도

**결론**: 두 시스템 **보완 가치**. 시스템의 차별점은 **운영 통합 가능성 + 카테고리 객관 정확도 + niche 발굴**. LLM은 mainstream 친숙도 측면에서 강점. 같은 metric으로 비교 부적합 → 다른 metric으로 각자 평가.

---

## 6. M9 — Vibe 약점 풀기 시도 + 결과

### 시도한 것

**M9.A: W_align 학습 데이터 augmentation**
- 9956 게임의 description을 Gemini로 임베딩
- target은 그 게임의 top-5 vote 태그의 가중평균 tag_vec (tag space 유지로 정체성 보존)
- 의도: niche cluster bias 약화

### 결과 — 의외의 negative finding

`vibe_our_avg_pop` 7.19M → **4.64M (-35%)**. 의도와 정반대로 niche bias가 **강화**됨.

원인: 추가한 9956 description의 자연어 분포가 long-tail (niche가 mainstream보다 다수). Ridge가 다수파 niche cluster로 더 강하게 self-bias.

→ **revert**. M9.A는 negative finding으로 기록.

### M9.C ablation으로 답을 찾음

`ensemble_alpha` 값을 변경하며 비교:

| α | overlap@5 | vibe_our_avg_pop |
|---|---|---|
| 0.5 | 0.013 | 1.35M |
| 0.7 (옛 default) | 0.053 | 4.64M |
| 0.9 | 0.047 | 5.86M |
| **1.0 (Item2Vec OFF)** | **0.087** | **6.08M** |

**Item2Vec 자체가 noise였음**. 비활성하면 모든 지표 개선.

원인: `user_reviews.py` 페이지네이션 issue — user당 첫 페이지(10건)만 수집되어 Skip-Gram sentence가 짧음 → 학습 부실 → ensemble에서 noise 도입.

### 최종 채택

| 설정 | 옛 | 새 |
|---|---|---|
| W_align 학습 방식 | tag wrapper만 | **그대로 유지 (M9.A revert)** |
| `ensemble_alpha` | 0.7 | **1.0** (Item2Vec OFF) |
| `eta` (β-축) | 0.2 | **0** (β-축 OFF, 효과 미미) |
| 사용자 슬라이더 | 4-axis (Rel/Div/Nov/**Ser**) | **3-axis** (Rel/Div/Nov) — M11 |

결과: vibe 모드의 niche cluster bias 사실상 해소. 시스템 정체성 (태그 의미 기반 추천) 그대로.

### M11 — Serendipity slider 제거 (학계 표준 + UX 단순화)

Serendipity = Relevance × (1 - popularity_percentile). Novelty와 popularity 기반 redundant. 사용자 control 다이얼로는 두 슬라이더가 거의 같은 효과 (200 후보가 이미 cosine top이라 rel 곱이 미미).

학계 표준 (Adamopoulos & Tuzhilin 2014, Kotkov 2016 등): "Serendipity should not be directly optimized; it emerges from relevance + novelty combination". measurement metric으로만 사용하고 user-facing axis로는 두지 않는 게 일반적.

→ Serendipity slider 제거, 3-axis(Rel/Div/Nov)로 단순화. Serendipity@K **metric**은 `evaluation/metrics.py`에 측정용으로 그대로 유지.

정량 트레이드오프: 4-axis 대비 vibe_our_avg_pop 9.58M → 7.38M (입문자에서 popular boost 약간 약해짐). 다만 baseline(pre_m9a) 대비는 여전히 명확히 우세 (vibe_overlap 0.040 → 0.080, +100%). 학계 표준 + UX 깔끔함 우선.

## 7. 다음 방향 (이번 plan 범위 밖)

### 더 풍부한 데이터

- 게임 설명 텍스트 (`steam_appdetails.csv`의 description) — M9.A에서 시도했지만 단순 추가는 효과 X. mainstream-위주 sampling 또는 다른 활용 방법 필요
- 유저 리뷰 텍스트 (steam_reviews.csv) — 이미 있음, 미사용

### user_reviews 페이지네이션 fix

user당 전체 리뷰 수집 → sentence 길어짐 → Item2Vec 재활성 시도 가능 (현재는 noise라 OFF).

### 시스템 가치 강화

- **FastAPI 백엔드 분리** — Streamlit은 prototype, production은 API
- **Session memory** — 익명 session 기반으로 추천 history 학습
- **A/B test infra** — 두 시스템을 사이드바 토글로 비교 가능하게

---

## 7. 면접 / 포트폴리오 관점

### 어떤 시그널을 보여주나

이 프로젝트가 보여주는 엔지니어링 / 데이터 사이언스 시그널:

1. **NLP 임베딩 깊이 있는 이해**: PPMI + SVD + Ridge로 자연어 ↔ 태그 사상 학습 (LLM 시대 이전 기법을 LLM과 결합)
2. **시스템 설계**: 오프라인 학습 / 온라인 서빙 분리, sync 자동화, blue-green deploy 비슷한 outputs/serving 분리
3. **데이터 품질 진단**: vote-weighted vs binary X의 매크로 분류 오류 진단, Bayesian shrinkage로 noise 정리
4. **사용자 인터랙션 디자인**: signed sigmoid slider (5=neutral, 비선형 분산)
5. **LLM 한계 이해 + 보완**: hallucination 정량 측정, grounding-based system 가치 증명
6. **시각화**: UMAP scatter + force-directed graph로 임베딩 quality 시각적 확인 가능
7. **Reproducibility**: 모든 hyperparameter / 명령 / API endpoint 문서화

### 어떤 한계를 정직히 명시했나

- vibe 모드 quality 부족 (W_align sparse bias)
- timestamp 없음 → sequence-based 모델 불가
- user 데이터 sentence 짧음 (페이지네이션 누락)
- 영문 리뷰만

---

## 부록: 용어 사전

| 용어 | 풀이 |
|---|---|
| **PPMI** (Positive Pointwise Mutual Information) | "기대보다 많이 같이 등장했는가"를 측정. 0보다 작으면 0으로 clip |
| **SVD** (Singular Value Decomposition) | 큰 행렬을 작은 차원으로 압축 (정보 최대 보존). PCA의 일반화 |
| **Skip-Gram** | Word2Vec의 한 종류. 한 단어 주변에 어떤 단어가 나올지 예측하면서 임베딩 학습 |
| **Item2Vec** | Skip-Gram을 단어 대신 item(게임)에 적용 |
| **Ridge Regression** | OLS에 L2 regularization 추가. 안정적인 linear regression |
| **MMR** (Maximal Marginal Relevance) | "relevant하지만 이미 뽑힌 거랑 비슷하지 않은" 결과 선택 |
| **UMAP** (Uniform Manifold Approximation) | 고차원 임베딩을 2D/3D로 줄이는 알고리즘. t-SNE의 후속 |
| **FAISS** (Facebook AI Similarity Search) | 빠른 nearest neighbor 검색 라이브러리 |
| **LangGraph** | LangChain의 graph-based agent framework. node들의 흐름을 명시적으로 |
| **Cosine similarity** | 두 vector의 각도. 1 = 같은 방향, 0 = 직교, -1 = 정반대 |
| **L2 normalization** | vector를 자기 길이로 나눠 단위 벡터로. cosine 계산 안정화 |
