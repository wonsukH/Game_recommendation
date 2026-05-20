# Archive — 미채택 / 이전 실험 코드

이 폴더는 **현재 production에서 사용되지 않는** 코드를 보존하기 위한 공간입니다. 학습/참고 목적으로만 두고, 메인 파이프라인에서는 import하지 않습니다.

## 내용

### `step10.py` ~ `step15.py` + `README_ONLINE_SERVING.md` + `EXAMPLES.md`

**무엇이었나**: 사용자 의도를 받아 게임을 추천하는 **온라인 서빙 파이프라인** v0 시도. 각 step을 별도 CLI 스크립트로 chaining (`run_online_pipeline.py`가 subprocess로 차례 호출).

- Step 10: LLM 의도 파싱 (intent → JSON)
- Step 11: 쿼리 벡터 생성
- Step 12: ANN 후보 검색
- Step 13: 필터 & 스코어링
- Step 14: MMR 다양성 선택
- Step 15: LLM 설명 생성

**왜 폐기됐나**: subprocess 체이닝 구조가 (1) 상태 전달이 파일 I/O로만 가능, (2) 노드 간 의존성이 명시적이지 않음, (3) 분기/조건부 라우팅이 어려움. 같은 기능을 **LangGraph**(`st_app/`)로 재구현하면서 단일 프로세스 + 명시적 그래프 토폴로지 + 조건부 엣지를 얻음. 그 결과 mode 라우팅(similar/vibe/hybrid/general)이 한 노드에서 깔끔하게 처리됨.

**현재 시스템 대응표**:

| archive | 현재 (`st_app/`) |
|---|---|
| step10.py | `rag/nodes/parser_node.py` + `normalization_node.py` |
| step11.py | `rag/retriever.py:_create_query_vector` |
| step12.py | `rag/retriever.py:recommend_*` (FAISS 검색) |
| step13.py | `app.py:rerank_node` |
| step14.py | (현재 미구현 — novelty 점수가 placeholder) |
| step15.py | `rag/nodes/response_generator_node.py` |
| run_online_pipeline.py | `app.py`의 LangGraph compile + stream |

**왜 지우지 않았나**: 면접/리뷰 시 "왜 LangGraph로 갔는지" 설명할 때 비교 자료로 유용. 또한 step14의 MMR 다양성 선택 알고리즘은 향후 rerank node 개선 시 참조 가치가 있음.
