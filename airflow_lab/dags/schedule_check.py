"""Does the scheduler actually fire on its own? — NOT part of the pipeline.

Every p5_rebuild run so far was a manual `dags trigger`. That leaves the most
basic claim about a batch system unverified: that it starts by itself. This DAG
fires every 10 minutes and prints the wall-clock time next to the logical_date,
which also makes the gap between the two visible.

Echo only. Once firing is confirmed, pause it — a 10-minute heartbeat has no
reason to keep running.

    airflow dags pause schedule_check
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="schedule_check",
    description="Confirms the scheduler starts runs without a manual trigger",
    start_date=datetime(2026, 8, 2),
    schedule="*/10 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["probe"],
) as dag:

    tick = BashOperator(
        task_id="tick",
        retries=0,
        bash_command=(
            "echo \"fired at $(date -u '+%Y-%m-%d %H:%M:%S') UTC | \""
            "\"run_id={{ run_id }} | logical_date={{ ts }} | \""
            "\"run_type={{ dag_run.run_type }}\""
        ),
    )
