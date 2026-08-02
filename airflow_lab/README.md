# airflow_lab — P5 재빌드 배치를 Airflow로

`docs/operations.md` §7이 손으로 돌리라고 적어둔 서빙 산출물 재빌드를 Airflow DAG으로 옮긴 것.
로드맵 P9("periodically re-run P5–6 on accumulated data")에 해당한다.

스텁 태스크는 없다. 5개 태스크 전부 실제 파이프라인 모듈을 실행하고, 앞 단계가 디스크에 남긴
산출물을 뒤 단계가 읽는다.

## 무엇을 만들었나

```
airflow_lab/
  docker-compose.yaml       postgres + scheduler + webserver (LocalExecutor)
  Dockerfile                apache/airflow:2.10.5-python3.11 + numpy/scipy/pandas/sklearn
  seed.sh                   스크래치에 입력 파일 채우기
  dags/p5_rebuild.py        5-task 파이프라인 DAG
  dags/behavior_probe.py    재시도·타임아웃·trigger_rule 확인용 (파이프라인 아님)
  dags/schedule_check.py    스케줄 발화 확인용, 확인 후 pause (파이프라인 아님)
  AIRFLOW_GUIDE.html        Airflow 실행·사용 레퍼런스
  work/                     스크래치 산출물 (gitignored)
  logs/                     태스크 로그 (gitignored)
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

## 실행 기록

### run 1 — 2026-08-02 (`manual__2026-08-02T05:21:46+00:00`)

실제 `steam.db`(23,347명) 기준. 처음 실행에서 뒤 두 태스크가 입력 부재로 깨졌고,
파일을 채운 뒤 실패한 것만 `tasks clear`로 재실행해 5/5로 마감했다.

| 태스크 | 결과 | 소요 |
|---|---|---|
| `behavioral_extract` | success | 11분 09초 |
| `build_ease_artifact` | success | 5분 31초 |
| `build_catalog_db` | 3회 실패 후 success | 1분 29초 |
| `p5_validate` | 3회 실패 후 success | 12분 12초 |
| `p5_smoke` | success | 11초 |

산출물이 2026-07-20 프로덕션 빌드를 재현했다.

| 지표 | 이 실행 | `docs/status.md` · 라이브 `meta.json` |
|---|---|---|
| 절단 손실 `d(sparse-exact)` | -0.0027 [-0.0041, -0.0013] SIG | -0.0027 |
| top-20 Jaccard | 0.966 | 0.966 |
| `d(pctl-pvalue)` | +0.0104 [+0.0071, +0.0139] SIG | +0.0104 SIG |
| items / B nnz / graph users | 34,050 / 69,734,400 / 12,000 | 34,050 / 69,734,400 / 12,000 |
| 추출 substrate | 23,347명 / 1,239,021 played / pool 41,266 | 23,347 / 1.24M / 41,266 |

`p5_smoke`는 5개 경로 전부 통과(SMOKE PASS). 라이브러리 경로 20건, 시드 경로 10건,
탐색 경로는 평범한 top-10과 1/10만 겹쳐 스티어링이 실제로 작동함을 확인.

### run 2 — 신선 실행 (`manual__2026-08-02T06:40:25+00:00`)

빈 상태에서 5단계를 처음부터 다시 돌린 실행. 재시도 0회, 실패 0건.

| 태스크 | 결과 | 소요 |
|---|---|---|
| `behavioral_extract` | success | 11분 18초 |
| `build_catalog_db` | success | 3분 27초 |
| `build_ease_artifact` | success | 4분 55초 |
| `p5_validate` | success | 13분 19초 |
| `p5_smoke` | success | 13초 |

전체 29분 52초. `build_catalog_db`와 `build_ease_artifact`는 같은 시각(06:51:45)에 시작해
병렬로 돌았다.

**결정성.** run 2의 게이트 수치가 run 1과 소수점까지 같다.

| 지표 | run 1 | run 2 |
|---|---|---|
| G-a `d(sparse-exact)` | -0.0027 [-0.0041, -0.0013] | -0.0027 [-0.0041, -0.0013] |
| G-a top-20 Jaccard | 0.966 | 0.966 |
| G-b `d(pctl-pvalue)` | +0.0104 [+0.0071, +0.0139] | +0.0104 [+0.0071, +0.0139] |
| G-c spearman / ndcg | 0.9961 / 0.4340 | 0.9961 / 0.4340 |
| smoke | 20/10/10 · 1/10 겹침 · 17/30 · 26/30 | 동일 |

부트스트랩 신뢰구간까지 일치한다. 같은 DB로 독립 실행한 두 결과가 완전히 같고,
그 값이 2026-07-20 프로덕션 빌드와도 같다. run 1의 일치는 우연이 아니다.

**자원.** run 2의 `p5_validate` 실행 중 측정값이다.

```
airflow-scheduler   CPU 254~360%   MEM 5.7~6.0GiB / 7.446GiB
host RAM free 0.7~0.8 GB of 15.4 GB
```

7.4GiB는 `.wslconfig`가 없을 때 WSL2가 잡는 기본 한계(호스트의 50%)다. 여유가 1.4GiB뿐이라
데이터가 늘면 호스트에서는 돌아갈 작업이 컨테이너 안에서 먼저 죽는다.
대응은 `AIRFLOW_GUIDE.html` 15절 참고.

### 실패 동작

run 1의 실패는 의도한 것이 아니라 진짜로 깨진 것이다. 관측된 그대로.

```
05:32:57  build_catalog_db  running
05:33:37  build_catalog_db  up_for_retry     1차 실패, 1분 대기
05:34:45  build_catalog_db  running
05:35:58  build_catalog_db  up_for_retry
05:37:00  build_catalog_db  running
05:38:02  build_catalog_db  failed           재시도 소진
05:38:02  p5_smoke          upstream_failed  즉시 차단
```

같은 시각 `build_ease_artifact`는 영향 없이 완주했다. 형제 태스크의 실패는 무관한 가지로 번지지 않는다.

`tasks clear` 로 재실행하면 로그가 `attempt=4.log` 로 이어붙는다. 실패 이력이 덮이지 않는다.

### behavior_probe — 나머지 동작 확인

run 1의 사고는 "재시도가 소진되는" 경우만 보여줬다. 재시도로 **복구되는** 경우, 타임아웃,
`trigger_rule` 변경은 안 보여줬으므로 `dags/behavior_probe.py` 로 따로 유발해 확인했다.
파이프라인과 무관한 echo/sleep 뿐이다.

| 태스크 | 설정 | 관측 |
|---|---|---|
| `flaky` | try 1에만 exit 1, `retries=2` | attempt 1 실패 → 30초 뒤 attempt 2 `recovered` → success |
| `hard_fail` | `retries=0` | 0.25초 만에 failed, 재시도 없음 |
| `gated_all_success` | 기본 trigger_rule | upstream_failed, 실행 안 됨 |
| `gated_all_done` | `trigger_rule="all_done"` | 앞이 실패해도 success |
| `slow` | 120초 sleep, `execution_timeout=30s` | 30.2초에 `AirflowTaskTimeout`으로 강제 종료 |

## 크롤 태스크 방침

현재 DAG에 수집 단계는 없다. 넣지 않은 이유와 넣으려면 무엇이 필요한지.

**막는 것.** 컨테이너에서 `steam.db`에 쓰는 경로가 안전하지 않다. WAL 모드는 `-shm` 공유 메모리를
mmap해야 하는데 Windows 드라이브를 컨테이너에 붙일 때 거치는 9p에서 보장되지 않는다.
읽기 실패는 다시 하면 되지만 쓰기 실패는 2GB 원본을 잃는 일이다.

**바운디드 슬라이스 자체는 코드 수정 없이 된다.** `--stop-at-users`가 누적 총량 기준이므로
현재 카운트에 N을 더해 넘기면 되고, `--seed-today`로 별도 DB에서도 예산 게이트를 승계할 수 있다.
즉 `--forever` 데몬을 일일 배치로 바꾸는 것은 문제가 아니다. 실행 위치만 문제다.

**선택지.**

- **호스트 위임 (`SSHOperator`)** — Airflow는 컨테이너에서 스케줄만 하고 크롤은 Windows 프로세스로
  실행한다. 9p를 안 거치므로 안전하고, 오케스트레이터와 실행 주체를 분리하는 표준 패턴이다.
  Windows OpenSSH Server 설치가 필요하고 관리자 권한이 든다. 현재 이 머신에 미설치(`sshd` 서비스 없음).
- **현행 유지** — 크롤은 기존 `daily_crawl.bat` + 워치독에 두고 Airflow는 재빌드 배치만 맡는다.
  예산 게이트·AIMD·서킷브레이커·재개 커서를 자체 보유한 상시 데몬은 원래 스케줄러가 감쌀 물건이
  아니라 서비스로 띄울 물건이라는 점에서 방어된다.

**판단.** 현행 유지 쪽이 낫다고 본다. 반론을 먼저 적으면, `docs/status.md`에 07-15 → 07-18
3일 크롤 공백이 기록되어 있고 원인은 "OS 스케줄러가 없어 워치독이 세션 안에서만 돈다"였다.
스케줄링 공백은 실재하는 문제다. 그러나 그 공백을 Airflow가 더 잘 메우지는 않는다 —
Docker Desktop 위의 Airflow도 노트북이 꺼지면 같이 꺼지고, 부팅 후 자동 기동은 Windows 예약 작업과
같은 층위의 문제다. 예약 작업은 사용자가 이미 명시적으로 거부했다(`operations.md` §2).
따라서 크롤의 스케줄링 문제는 Airflow 도입으로 해결되는 문제가 아니고, 별도로 다뤄야 한다.

`SSHOperator` 경로는 사용자 결정 사항으로 남긴다. 채택하면 태스크는 이런 형태가 된다.

```python
from airflow.providers.ssh.operators.ssh import SSHOperator

crawl = SSHOperator(
    task_id="crawl_slice",
    ssh_conn_id="windows_host",          # host.docker.internal, 키 인증
    command=(
        r'"D:\...\.venv\Scripts\python.exe" -m data_collection.crawl_unified '
        r"--stop-at-users {{ ti.xcom_pull(task_ids='current_user_count') + 200 }} "
        r"--no-achievements --user-source random --users-chunk 100"
    ),
    retries=0,                            # 예산을 쓰는 작업은 자동 재시도 금지
)
```

`retries=0`이 중요하다. 크롤은 실패해도 이미 쓴 API 호출이 예산에서 빠져나간 뒤다.
재시도가 안전한지와 재시도가 **바람직한지**는 다른 질문이다.

### schedule_check — 스케줄러가 스스로 도는지

run 1·2와 프로브는 전부 `dags trigger` 수동 실행이었다. 배치 시스템에 대한 가장 기본적인 주장,
"알아서 시작한다"가 검증되지 않은 채였다. `dags/schedule_check.py`(echo 한 줄)를 10분 주기로
걸어 확인했다.

| logical_date | 실제 발화 (UTC) | 비고 |
|---|---|---|
| 07:00:00 | 07:14:32 | unpause 시점에 밀린 구간 1개가 실행됨 |
| 07:10:00 | 07:20:01 | 정상 주기, 지연 1초 |

```
fired at 2026-08-02 07:14:32 UTC | run_id=scheduled__2026-08-02T07:00:00+00:00
logical_date=2026-08-02T07:00:00+00:00 | run_type=scheduled
```

`run_type=scheduled` 이므로 수동 트리거가 아니다. 두 번째 행이 `logical_date`의 의미를 그대로
보여준다 — 구간 시작이 07:10인 실행이 구간이 끝나는 07:20에 돈다.

첫 행도 알아둘 만하다. `catchup=False`는 "앞으로 것만"이 아니라 "밀린 것을 전부 소급하지 않는다"는
뜻이고, **가장 최근 구간 하나는 실행한다.** unpause 직후 아무것도 안 걸었는데 실행이 하나 뜬 이유다.

확인 후 이 DAG는 pause 했다. 10분 심박을 계속 돌릴 이유가 없다.

## 정리

### 확인한 것

- 5개 태스크가 실제 파이프라인 모듈을 실행하고, 앞 단계 산출물을 뒤 단계가 디스크에서 읽는다.
- 실제 `steam.db`(23,347명)를 컨테이너에서 read-only로 읽어 2026-07-20 프로덕션 빌드를 재현했다.
  게이트 4개 지표와 추출 substrate가 문서 수치와 일치.
- 독립 실행 두 번의 평가 수치가 부트스트랩 신뢰구간까지 동일하다.
- 재시도가 소진되는 경우, 재시도로 복구되는 경우, `execution_timeout` 강제 종료,
  `upstream_failed` 자동 차단, `trigger_rule="all_done"` 우회를 전부 관측했다.
- 실패한 태스크만 `tasks clear`로 재실행해 앞 단계 17분을 재사용했다.
- 컨테이너가 배포 산출물과 동결 패널에 도달할 수 없음을 쓰기 시도로 확인했다.

### 확인하지 못한 것

- **`p5_rebuild` 자신의 스케줄 발화.** 스케줄러가 스스로 실행을 만든다는 것은
  `schedule_check`로 확인했으나(위), `p5_rebuild`의 `0 12 * * *`는 아직 그 시각을 넘기지 않았다.
  즉 "스케줄러가 돈다"는 확인됐고 "이 파이프라인이 스케줄로 돈다"는 아직이다.
- **수집(크롤) 태스크.** DAG에 넣지 않았다. 사유는 위 "크롤 태스크 방침".
- **실제 `serving/data` 갱신.** 의도적으로 막아뒀다. 스크래치 산출물만 만들었고
  배포 아티팩트는 07-22자 그대로다.
- **재부팅 후 자동 기동.** Docker Desktop과 컨테이너의 부팅 시 복구를 시험하지 않았다.
- **다른 머신에서의 재현.** 데탑용 절차를 문서로 적었을 뿐 실행하지 않았다.
- **알림.** 실패를 사람이 UI로 확인하는 것 외의 경로가 없다.
- **9p 마운트 비용의 분리 측정.** 컨테이너 314초 대 호스트 13초라는 관측은 있으나
  DB 크기가 함께 달라져 마운트 비용만 떼어낸 값이 아니다.
- **Docker 크래시 해결의 인과.** `max-concurrent-downloads: 1`과 Docker Desktop
  28.3.0 → 29.6.2 자동 업데이트가 같은 재시작에서 겹쳤다. 어느 쪽이 고쳤는지 모른다.

### 시간이 더 있었다면

- 스케줄 발화 확인. 수동 트리거만으로는 "배치가 돈다"의 절반만 보인 것이다.
- `on_failure_callback` 로 실패 알림. 지금은 사람이 봐야만 안다.
- 결정론적 실패에 `retries=0` 적용. 입력 누락으로 3회씩 돈 4분은 순손실이었다.
- `pop_unbiased.json` 갱신 단계를 DAG에 편입. 지금은 씨앗 파일로 밖에서 넣는데,
  OOD 코호트가 커지면 이 사전도 낡는다. `p6_e2_unbiased_pop`이 그것을 만들지만
  E2 실험 전체를 돌리는 스크립트라 필요한 부분만 떼는 작업이 선행되어야 한다.
- `.wslconfig` 로 VM 메모리 명시. 지금 여유가 1.4GiB뿐이다.

### 작업 시간

2026-08-02 12:40 KST 시작, 16:15 KST 기준 약 3시간 35분.
그중 Docker 백엔드 크래시 진단과 우회에 약 50분, 로컬 `steam.db` 유실 발견과 복구에 약 40분이
들어갔다. 순수 Airflow 구성 시간은 그보다 짧다.
