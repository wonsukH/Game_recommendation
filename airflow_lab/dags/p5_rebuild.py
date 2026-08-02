"""P9 daily batch — collect, then rebuild the serving artifacts.

Steps 2-6 are the sequence docs/operations.md §7 documents as a manual run. Step 1
is the crawl, bounded into a daily slice so it is a batch instead of a daemon.

    crawl ──▶ extract ──┬─▶ ease ──▶ validate ──┐
                        │                       ├──▶ smoke
                        └─▶ catalog ────────────┘

Every task shells out to a real pipeline module. Nothing here is a placeholder:
each step reads the previous step's artifact off disk and fails loudly if it is
missing or fails its gate.

Reads   : /opt/project/data_collection/steam.db
Writes  : steam.db (crawl only), /opt/project/outputs, /opt/project/serving/data
          — the latter two are scratch overlays, see docker-compose.yaml.

max_active_runs=1 is load-bearing twice over: the rebuild steps hand off through
fixed paths so two concurrent runs would overwrite each other mid-flight, and two
concurrent crawlers would both be writing steam.db across the bind mount, which is
the case SQLite's WAL does not support.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.utils.trigger_rule import TriggerRule

PY = "python -m"
OUT = "/opt/project/outputs/p5"
DB = "/opt/project/data_collection/steam.db"

# --stop-at-users is a CUMULATIVE target, not a delta: the crawler stops once the
# database holds that many public+complete users. Passing a fixed number would make
# the task a no-op the moment the count passed it, so the slice size is added to the
# current count at run time.
CRAWL = f"""set -eu
CUR=$(python - <<'PYEOF'
import sqlite3
con = sqlite3.connect("file:{DB}?mode=ro", uri=True)
print(con.execute(
    "select count(*) from users where public=1 and complete=1").fetchone()[0])
PYEOF
)
TARGET=$((CUR + {{{{ params.users_per_run }}}}))
echo "usable users now=$CUR -> target=$TARGET (+{{{{ params.users_per_run }}}})"
{PY} data_collection.crawl_unified \
  --stop-at-users "$TARGET" \
  --no-achievements --user-source random --users-chunk 100
"""

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "execution_timeout": timedelta(minutes=45),
}

with DAG(
    dag_id="p5_rebuild",
    description="Crawl a daily slice, then rebuild the serving artifacts from steam.db",
    start_date=datetime(2026, 8, 1),
    schedule="0 12 * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    params={
        "users_per_run": Param(
            100, type="integer", minimum=0,
            description="public+complete users to add this run (0 skips crawling)"),
    },
    tags=["game-rec", "p9"],
) as dag:

    # retries=0 on purpose. The daily API budget is spent by the calls already made,
    # so a retry after a mid-run failure burns quota to redo work the resume cursors
    # would have picked up anyway. Retrying is safe here — the crawler is idempotent
    # — but safe and worthwhile are different questions, and this one is not worth it.
    crawl = BashOperator(
        task_id="crawl_slice",
        bash_command=CRAWL,
        retries=0,
        execution_timeout=timedelta(minutes=60),
    )

    # all_done, not the default all_success: a crawl that hits the daily budget cap
    # or a throttle should not block rebuilding from the data already collected.
    # The rebuild is useful on yesterday's rows too.
    extract = BashOperator(
        task_id="behavioral_extract",
        bash_command=f"{PY} pipeline.game_rec.data.behavioral_extract --out {OUT}",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    # --topk/--cap are passed explicitly, not left to the script defaults. The
    # script's own default is topk=512, but the gate-chosen production value is
    # 2048 (512 and 1024 both failed p5_validate's truncation tolerance), and the
    # live artifact's meta.json confirms 2048. operations.md §7 describes 2048 as
    # a default, which is wrong — the production build passed it explicitly.
    ease = BashOperator(
        task_id="build_ease_artifact",
        bash_command=(
            f"{PY} pipeline.game_rec.data.build_ease_artifact "
            f"--artifacts {OUT} --cap 12000 --topk 2048"
        ),
    )

    validate = BashOperator(
        task_id="p5_validate",
        bash_command=f"{PY} pipeline.orchestration.p5_validate",
    )

    catalog = BashOperator(
        task_id="build_catalog_db",
        bash_command=f"{PY} pipeline.game_rec.data.build_catalog_db --pool {OUT}/pool.json",
    )

    smoke = BashOperator(
        task_id="p5_smoke",
        bash_command=f"{PY} pipeline.orchestration.p5_smoke",
    )

    crawl >> extract
    extract >> ease >> validate
    extract >> catalog
    [validate, catalog] >> smoke
