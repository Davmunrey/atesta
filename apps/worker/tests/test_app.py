"""Worker app wiring: ids-only job arguments, TLS settings, org context entry."""

import datetime
import logging
import uuid

import pytest
from atesta_api.modules.scanning.api import (
    INGEST_TASK,
    RESCORE_TASK,
    RUN_TASK,
    SCHEDULE_TASK,
    SNAPSHOT_TASK,
    ScanNotFoundError,
    ScanTransientError,
)
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
    # The names the scanning module defers by.
    assert {SNAPSHOT_TASK, RESCORE_TASK, RUN_TASK, INGEST_TASK, SCHEDULE_TASK} <= set(app.tasks)
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


def test_a_scan_retries_three_times_after_300_600_and_900_seconds() -> None:
    task = build_app(URL, "disable").tasks[RUN_TASK]
    assert task.queue == "scans"
    strategy = task.retry_strategy
    assert strategy is not None
    transient = ScanTransientError("exit 20")
    lost = OperationalError("SELECT 1", {}, Exception("connection lost"))
    for error in (transient, lost):
        waits = []
        for attempts in range(3):
            before = datetime.datetime.now(datetime.UTC)
            decision = strategy.get_retry_decision(exception=error, job=_job(attempts))
            assert decision is not None and decision.retry_at is not None
            waits.append(round((decision.retry_at - before).total_seconds() / 100) * 100)
        assert waits == [300, 600, 900]
        assert strategy.get_retry_decision(exception=error, job=_job(3)) is None
    # Permanent: ids that do not match, or anything that is not a transient failure.
    for permanent in (ScanNotFoundError("x"), RuntimeError("not configured")):
        assert strategy.get_retry_decision(exception=permanent, job=_job(0)) is None


@pytest.mark.parametrize("name", [INGEST_TASK, SCHEDULE_TASK])
def test_ingest_and_schedule_retry_transient_database_errors_only(name: str) -> None:
    strategy = build_app(URL, "disable").tasks[name].retry_strategy
    assert strategy is not None and strategy.max_attempts == 3
    lost = OperationalError("SELECT 1", {}, Exception("connection lost"))
    assert strategy.get_retry_decision(exception=lost, job=_job(0)) is not None
    assert strategy.get_retry_decision(exception=ScanNotFoundError("x"), job=_job(0)) is None


def test_build_app_installs_log_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Procrastinate logs a failed job with exc_info; its message never reaches the log."""
    monkeypatch.setattr(logging, "_logRecordFactory", logging.LogRecord)
    build_app(URL, "disable")
    error = ValueError("Key (email)=(ana@example.com) already exists.")
    record = logging.getLogger("procrastinate.worker").makeRecord(
        "procrastinate.worker", logging.ERROR, "f", 1, "Job ended", (), (ValueError, error, None)
    )
    assert record.exc_info is None
    assert record.exc_text is not None and "ana@example.com" not in record.exc_text
    assert "builtins.ValueError" in record.exc_text
