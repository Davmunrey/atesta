"""Worker app wiring: ids-only job arguments, TLS settings, org context entry."""

import uuid

import pytest
from atesta_api.modules.scanning.api import SNAPSHOT_TASK, ScanNotFoundError
from atesta_api.platform.db import RDS_CA
from atesta_worker import context
from atesta_worker.app import build_app, connection_kwargs, conninfo, non_id_parameters
from atesta_worker.jobs import make_blueprint
from procrastinate import Blueprint, JobContext
from procrastinate.jobs import Job
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

URL = "postgresql+psycopg://atesta_app:pw@db.example.com:5432/atesta?sslmode=disable"


def test_real_jobs_take_ids_only() -> None:
    app = build_app(URL, "disable")
    assert "atesta:retry_stalled_jobs" in app.tasks
    assert SNAPSHOT_TASK in app.tasks  # the name ingest defers by
    assert non_id_parameters(make_blueprint().tasks.values()) == []


def test_non_id_arguments_are_refused() -> None:
    bad = Blueprint()

    @bad.task(name="notify")
    def notify(organization_id: str, email: str) -> None: ...

    @bad.task(name="typed")
    def typed(scan_id: uuid.UUID) -> None: ...

    @bad.task(name="fine", pass_context=True)
    def fine(context: JobContext, organization_id: str, connection_id: str) -> None: ...

    with pytest.raises(ValueError, match=r"ids only: notify\(email\), typed\(scan_id\)$"):
        build_app(URL, "disable", extra=(bad,))


def test_conninfo_drops_tls_settings_from_the_url() -> None:
    assert conninfo(URL) == "postgresql://atesta_app:pw@db.example.com:5432/atesta"


def test_tls_is_verify_full_with_the_pinned_ca() -> None:
    assert connection_kwargs("verify-full") == {"sslmode": "verify-full", "sslrootcert": RDS_CA}
    assert connection_kwargs("disable") == {"sslmode": "disable"}
    with pytest.raises(ValueError, match="sslmode"):
        connection_kwargs("require")


def test_org_session_refuses_a_malformed_id_before_any_query() -> None:
    context.configure(create_engine("postgresql+psycopg://nobody@127.0.0.1:1/none"))
    with pytest.raises(ValueError), context.org_session("not-a-uuid"):
        pass


def test_snapshot_scores_retries_transient_errors_only() -> None:
    task = build_app(URL, "disable").tasks[SNAPSHOT_TASK]
    assert task.queue == "scans"
    strategy = task.retry_strategy
    assert strategy is not None
    assert strategy.max_attempts == 3
    transient = OperationalError("SELECT 1", {}, Exception("serialization failure"))
    assert strategy.get_retry_decision(exception=transient, job=_job(0)) is not None
    assert strategy.get_retry_decision(exception=transient, job=_job(3)) is None
    # A job whose org and scan ids do not match finds no row and fails without retry.
    assert strategy.get_retry_decision(exception=ScanNotFoundError("x"), job=_job(0)) is None


def _job(attempts: int) -> Job:
    return Job(
        id=1,
        queue="scans",
        lock=None,
        queueing_lock=None,
        task_name=SNAPSHOT_TASK,
        attempts=attempts,
    )
