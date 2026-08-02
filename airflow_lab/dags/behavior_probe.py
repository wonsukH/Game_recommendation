"""Scheduler behaviour probe — NOT part of the pipeline.

p5_rebuild broke on its own during the first run (missing inputs) and that showed
retries burning out and downstream blocking. It never showed a task *recovering*
on retry, a timeout being enforced, or a trigger_rule other than the default.
This DAG provokes those four behaviours on purpose so they can be observed
instead of assumed.

Nothing here touches project data. Every task is echo/sleep/exit. Keep it that
way — the moment a probe task does real work it stops being a probe.

Expected outcome when triggered:

    flaky              attempt 1 fails, attempt 2 succeeds   -> success
    hard_fail          retries=0, fails once                 -> failed
    gated_all_success  default trigger_rule                  -> upstream_failed
    gated_all_done     trigger_rule="all_done"               -> success
    slow               sleeps 120s under a 30s timeout       -> failed (killed)
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.trigger_rule import TriggerRule

with DAG(
    dag_id="behavior_probe",
    description="Provokes retry / timeout / trigger_rule behaviour so it can be observed",
    start_date=datetime(2026, 8, 1),
    schedule=None,            # manual only; nothing here should run on a timer
    catchup=False,
    tags=["probe"],
) as dag:

    # try_number is 1 on the first attempt, so this fails once and then passes.
    flaky = BashOperator(
        task_id="flaky",
        retries=2,
        retry_delay=timedelta(seconds=30),
        bash_command=(
            "if [ {{ ti.try_number }} -lt 2 ]; then"
            "  echo \"attempt {{ ti.try_number }}: simulated transient failure\"; exit 1;"
            "fi; echo \"attempt {{ ti.try_number }}: recovered\""
        ),
    )

    hard_fail = BashOperator(
        task_id="hard_fail",
        retries=0,
        bash_command="echo 'deterministic failure, no retry'; exit 1",
    )

    gated_all_success = BashOperator(
        task_id="gated_all_success",
        bash_command="echo 'should never run'",
    )

    gated_all_done = BashOperator(
        task_id="gated_all_done",
        trigger_rule=TriggerRule.ALL_DONE,
        bash_command="echo 'runs even though upstream failed'",
    )

    slow = BashOperator(
        task_id="slow",
        retries=0,
        execution_timeout=timedelta(seconds=30),
        bash_command="echo 'sleeping 120s under a 30s timeout'; sleep 120",
    )

    hard_fail >> [gated_all_success, gated_all_done]
