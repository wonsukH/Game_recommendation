# airflow_lab — P5 재빌드 배치를 Airflow로

`docs/operations.md` §7이 손으로 돌리라고 적어둔 서빙 산출물 재빌드를 Airflow DAG으로 옮긴 것.
로드맵 P9("periodically re-run P5–6 on accumulated data")에 해당한다.

스텁 태스크는 없다. 5개 태스크 전부 실제 파이프라인 모듈을 실행하고, 앞 단계가 디스크에 남긴
산출물을 뒤 단계가 읽는다.

## 무엇을 만들었나

```
airflow_lab/
  docker-compose.yaml   postgres + scheduler + webserver (LocalExecutor)
  Dockerfile            apache/airflow:2.10.5-python3.11 + numpy/scipy/pandas/sklearn
  dags/p5_rebuild.py    5-task DAG
  work/                 스크래치 산출물 (gitignored)
  logs/                 태스크 로그 (gitignored)
```

DAG 형태:

```
behavioral_extract ──┬─▶ build_ease_artifact ──▶ p5_validate ──┐
                     │                                         ├──▶ p5_smoke
                     └─▶ build_catalog_db ─────────────────────┘
```

`build_ease_artifact`와 `build_catalog_db`는 둘 다 extract 산출물만 있으면 되므로 병렬로 갈린다.
`p5_smoke`는 양쪽이 다 끝나야 한다 — EASE 텐서와 카탈로그 파일을 동시에 읽기 때문.

## 안전 경계 (제일 중요)

컨테이너는 **실제 서빙 산출물에 물리적으로 도달할 수 없다.**

| 컨테이너 경로 | 실체 | 권한 |
|---|---|---|
| `/opt/project` | 리포 루트 | **read-only** |
| `/opt/project/outputs` | `airflow_lab/work/outputs` | rw (스크래치) |
| `/opt/project/serving/data` | `airflow_lab/work/serving_data` | rw (스크래치) |
| `/opt/project/experiments/p6_ood` | `airflow_lab/work/p6_ood` | rw (스크래치) |
| `/opt/project/data_collection/steam.db` | 실제 DB | read-only (상위 ro 마운트) |

`p6_ood` 오버레이가 있는 이유는 `p5_validate`가 판정 결과를
`experiments/p6_ood/p5_validate.json` 에 쓰기 때문이다. 그런데 같은 디렉터리에 **동결된 P6 패널**이
들어 있다. 되돌릴 수 없는 증거 파일이라 컨테이너에 실제 디렉터리 쓰기 권한을 주지 않고,
사본을 주고 `p6_panels.json` 만 씨앗으로 넣는다.

read-only 마운트 안에 rw 마운트를 겹쳐 넣은 구조다. 파이프라인 스크립트가 전부 경로를
`REPO_ROOT / "outputs"`, `REPO_ROOT / "serving" / "data"` 로 계산하기 때문에, **프로젝트 코드를 한 줄도
고치지 않고** 모든 기본 경로가 스크래치로 떨어진다. 배포된 앱이 읽는 git-tracked 파일 16개는
컨테이너 안에서 목록에조차 나오지 않는다.

검증한 것:

```
$ touch /opt/project/__should_fail
touch: cannot touch '/opt/project/__should_fail': Read-only file system

$ ls /opt/project/serving/data
ease  tag_vocab.json        # 실제 catalog.json / index_maps.json 등은 보이지 않음
```

**왜 스크래치인가.** 처음에는 실제 `serving/data`에 쓰는 것을 목표로 잡았다가 바꿨다. 작업 중
로컬 `steam.db`가 07-03 상태(1,669명)로 되돌아가 있고 라이브 산출물을 만든 23k DB가 이 디스크에
없다는 것을 발견했기 때문이다. 그 상태로 재빌드를 돌려 덮으면 라이브 추천 품질이 퇴행한다.
DB는 이후 다른 PC에서 복구했지만(23,347명 확인), 출력 격리는 그대로 두는 편이 맞다고 판단했다.

## 돌리는 법

```bash
cd airflow_lab
docker compose build
docker compose up airflow-init                       # 최초 1회 (db migrate + admin 생성)
docker compose up -d airflow-scheduler airflow-webserver
```

- 웹 UI: http://localhost:8080 (admin / admin)
- 수동 실행: `docker compose exec airflow-scheduler airflow dags trigger p5_rebuild`
- 스케줄: 매일 12:00 UTC. `catchup=False`.

## 씨앗 파일

`work/` 는 gitignore라 클론 직후 비어 있다. 파이프라인이 **읽기만 하고 만들지는 않는** 입력 4개를
넣어줘야 한다. 리포 루트에서 한 번 돌린다.

```bash
bash airflow_lab/seed.sh
```

| 파일 | 없으면 |
|---|---|
| `outputs/tag_vocab.json` | 큐레이션 태그 어휘 없이 진행 (경고만) |
| `outputs/p6/pop_unbiased.json` | `build_catalog_db` 실패 |
| `serving/data/tag_vocab.json` | `p5_smoke` 영향 |
| `experiments/p6_ood/p6_panels.json` | `p5_validate` 실패 |

뒤의 두 개는 **gitignore된 로컬 전용 파일**이라 클론으로 따라오지 않는다.
`p6_panels.json` 은 raw SteamID를 담고 있어 2026-07-22에 추적 해제됐고, `pop_unbiased.json` 은
P6 E2 산출물이다. 둘 다 이것들을 만든 머신에만 있다.

## 다른 머신에서 이어서 하기

이 디렉터리는 git으로 따라오지만 데이터는 안 따라온다. 새 머신에서 필요한 것.

1. Docker Desktop. 이미지 pull 중 백엔드가 죽으면 `AIRFLOW_GUIDE.html` 14절 참고
   (`max-concurrent-downloads: 1`).
2. `data_collection/steam.db` — 실제 DB.
3. `bash airflow_lab/seed.sh` 가 통과할 것. 실패하면 어떤 입력이 없는지 알려준다.
4. `pipeline/orchestration/` 은 gitignore된 내부 전용 디렉터리라 클론에 없다.
   `p5_validate` 와 `p5_smoke` 가 여기 있으므로, 이 두 태스크를 돌리려면 해당 파일이 로컬에 있어야 한다.

그다음은 아래 실행 절차와 같다.

## 파라미터를 명시한 이유

`build_ease_artifact`에 `--cap 12000 --topk 2048`을 명시적으로 넘긴다. 스크립트의 실제 기본값은
`--topk 512`인데, 게이트가 고른 프로덕션 값은 2048이다(512와 1024는 `p5_validate`의 truncation
허용치를 통과하지 못했다). 라이브 산출물의 `meta.json`도 2048이다.

`docs/operations.md` §7은 2048을 "기본값"이라고 적어놨지만 코드 기본값은 512다. 프로덕션 빌드가
명시적으로 넘겼던 것으로 보인다. 문서 쪽 수정은 별도 확인 필요.

## max_active_runs=1

각 태스크가 고정 경로로 산출물을 주고받기 때문에, 동시 실행 두 개가 붙으면 서로의 중간 파일을
덮어쓴다. 스케줄 간격보다 실행이 길어질 때 조용히 깨지는 종류의 사고라 명시해 뒀다.
