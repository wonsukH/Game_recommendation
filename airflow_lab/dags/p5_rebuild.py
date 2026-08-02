"""P5 serving-artifact rebuild — the batch that docs/operations.md §7 runs by hand.

Every task shells out to a real pipeline module. Nothing here is a placeholder:
each step reads the previous step's artifact off disk and fails loudly if it is
missing or fails its gate.

    extract ──┬─▶ ease ──▶ validate ──┐
              │                       ├──▶ smoke
              └─▶ catalog ────────────┘

Reads   : /opt/project/data_collection/steam.db  (read-only mount)
Writes  : /opt/project/outputs, /opt/project/serving/data
          — both are scratch overlays, see docker-compose.yaml.

max_active_runs=1 is load-bearing: the steps hand off through fixed paths in the
artifact dirs, so two concurrent runs would overwrite each other mid-flight.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PY = "python -m"
OUT = "/opt/project/outputs/p5"

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "execution_timeout": timedelta(minutes=45),
}

with DAG(
    dag_id="p5_rebuild",
    description="Rebuild the serving artifacts from steam.db (operations.md §7)",
    start_date=datetime(2026, 8, 1),
    schedule="0 12 * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["game-rec", "p9"],
) as dag:

    extract = BashOperator(
        task_id="behavioral_extract",
        bash_command=f"{PY} pipeline.game_rec.data.behavioral_extract --out {OUT}",
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

    extract >> ease >> validate
    extract >> catalog
    [validate, catalog] >> smoke
