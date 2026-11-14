"""Scan jobs end to end on a real Postgres with real commits (scanner-connectors spec, Scan
lifecycle): run_scan, ingest_scan and schedule_scan as the worker runs them."""

import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from atesta_api.modules.connections.api import create_connection
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_api.modules.scanning.api import (
    INGEST_TASK,
    SCHEDULE_TASK,
    SNAPSHOT_TASK,
    FixtureRunner,
    LocalScanStore,
    ScanTransientError,
    defer_schedule,
    queue_scan,
)
from atesta_api.platform.db import make_engine
from atesta_worker import context, jobs
from atesta_worker.scans import ScanConfig, configure_scans
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .conftest import APP_PASSWORD, fresh_database

REPO = Path(__file__).resolve().parents[4]
EXPECTED = REPO / "scanner" / "expected"
FIXTURES = REPO / "scanner" / "fixtures" / "synthetic"
TENANT = "11111111-1111-4111-8111-111111111111"  # the synthetic fixtures' tenant


@pytest.fixture(scope="module")
def own_database() -> Iterator[URL]:
    """Its own database: these tests commit, like the worker."""
    with fresh_database() as url:
        yield url


@pytest.fixture(scope="module")
def owner(own_database: URL) -> Engine:
    return make_engine(own_database, sslmode="disable", null_pool=True)


@pytest.fixture(scope="module")
def app(own_database: URL) -> Engine:
    url = own_database.set(username="atesta_app", password=APP_PASSWORD)
    return make_engine(url, sslmode="disable", null_pool=True)


@pytest.fixture
def store(app: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[LocalScanStore]:
    monkeypatch.setenv("ATESTA_ENV", "test")
    context.configure(app)
    made = LocalScanStore(tmp_path / "scans")
    worker(made)
    yield made
    configure_scans(None)


def worker(store: LocalScanStore, exit_code: int = 0) -> None:
    runner = FixtureRunner(store, FIXTURES, exit_code=exit_code)
    configure_scans(ScanConfig(store, runner, EXPECTED, 3600))


@contextmanager
def org_session(app: Engine, org: uuid.UUID) -> Iterator[Session]:
    """One committed transaction in the org's context, as a request or a job."""
    with Session(app) as session, session.begin():
        enter_org_context(session, org, ContextReason.JOB)
        yield session


def connected(owner: Engine, app: Engine, status: str = "active") -> tuple[uuid.UUID, uuid.UUID]:
    org = uuid.uuid4()
    with owner.begin() as conn:
        conn.execute(text("INSERT INTO organizations (id, name) VALUES (:o, 'x')"), {"o": org})
    with org_session(app, org) as session:
        made = create_connection(
            session, organization_id=org, provider="m365", display_name="x", created_by=org
        )
        made.status, made.external_tenant_id = status, TENANT if status == "active" else None
        session.flush()
        return org, made.id


def queued(app: Engine, org: uuid.UUID, connection_id: uuid.UUID) -> uuid.UUID:
    with org_session(app, org) as session:
        return queue_scan(session, org, connection_id, trigger="user").id


def scan(owner: Engine, scan_id: uuid.UUID) -> dict[str, Any]:
    query = text("SELECT status, attempts, error_code FROM scans WHERE id = :s")
    with owner.connect() as conn:
        return dict(conn.execute(query, {"s": scan_id}).mappings().one())


def jobs_of(owner: Engine, task: str, key: str, value: object) -> list[dict[str, Any]]:
    query = text(
        "SELECT status::text, scheduled_at, args FROM procrastinate_jobs"
        " WHERE task_name = :t AND args->>:k = :v ORDER BY id"
    )
    with owner.connect() as conn:
        rows = conn.execute(query, {"t": task, "k": key, "v": str(value)}).mappings()
        return [dict(r) for r in rows]


def ctx(attempts: int) -> Any:
    return SimpleNamespace(job=SimpleNamespace(attempts=attempts))


def finished(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "atesta.scan"]


@pytest.fixture(autouse=True)
def scan_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="atesta.scan")


def test_a_queued_scan_runs_and_is_ingested_by_the_jobs(
    owner: Engine, app: Engine, store: LocalScanStore, caplog: pytest.LogCaptureFixture
) -> None:
    org, connection_id = connected(owner, app)
    scan_id = queued(app, org, connection_id)
    jobs.run_scan(ctx(0), str(org), str(scan_id))
    assert scan(owner, scan_id) == {"status": "collected", "attempts": 1, "error_code": None}
    assert len(jobs_of(owner, INGEST_TASK, "scan_id", scan_id)) == 1
    assert finished(caplog) == []
    jobs.ingest_scan(str(org), str(scan_id))
    jobs.ingest_scan(str(org), str(scan_id))  # a redelivered ingest changes nothing
    status = scan(owner, scan_id)["status"]
    # The fixture runner honors job.json's exclusions like the wrapper, so ingest accepts it.
    assert status in ("succeeded", "partial")
    assert len(jobs_of(owner, SNAPSHOT_TASK, "scan_id", scan_id)) == 1
    [event] = finished(caplog)  # exactly one scan.finished per scan
    assert (event["scan_id"], event["status"], event["attempts"]) == (str(scan_id), status, 1)
    reason = text(
        "SELECT status, reason FROM scan_check_results WHERE scan_id = :s AND check_id = :c"
    )
    with owner.connect() as conn:  # a PowerShell-backed check: excluded, never "no findings"
        params = {"s": scan_id, "c": "exchange_mailbox_audit_bypass_disabled"}
        assert tuple(conn.execute(reason, params).one()) == ("not_evaluated", "not_granted")


def test_a_transient_failure_is_retried_until_the_scan_fails_once(
    owner: Engine, app: Engine, store: LocalScanStore, caplog: pytest.LogCaptureFixture
) -> None:
    worker(store, exit_code=20)
    org, connection_id = connected(owner, app)
    scan_id = queued(app, org, connection_id)
    for previous in range(3):
        with pytest.raises(ScanTransientError):
            jobs.run_scan(ctx(previous), str(org), str(scan_id))
        assert scan(owner, scan_id) == {
            "status": "running",
            "attempts": previous + 1,
            "error_code": "scanning.engine_failed",
        }
    jobs.run_scan(ctx(3), str(org), str(scan_id))  # the last attempt ends the scan: no raise
    assert scan(owner, scan_id) == {
        "status": "failed",
        "attempts": 4,
        "error_code": "scanning.engine_failed",
    }
    [event] = finished(caplog)
    assert (event["status"], event["attempts"]) == ("failed", 4)


def test_a_job_that_cannot_run_fails_its_scan_instead_of_leaving_it_active(
    owner: Engine, app: Engine, store: LocalScanStore, caplog: pytest.LogCaptureFixture
) -> None:
    org, connection_id = connected(owner, app)
    scan_id = queued(app, org, connection_id)
    configure_scans(None)
    with pytest.raises(RuntimeError, match="not configured"):
        jobs.run_scan(ctx(0), str(org), str(scan_id))
    assert scan(owner, scan_id)["status"] == "failed"
    assert [e["status"] for e in finished(caplog)] == ["failed"]
    assert queued(app, org, connection_id) != scan_id  # the connection can be scanned again


def test_a_connection_disconnected_before_the_run_blocks_its_scan(
    owner: Engine, app: Engine, store: LocalScanStore, caplog: pytest.LogCaptureFixture
) -> None:
    org, connection_id = connected(owner, app)
    scan_id = queued(app, org, connection_id)
    with owner.begin() as conn:
        disconnect = text("UPDATE connections SET status = 'disconnected' WHERE id = :c")
        conn.execute(disconnect, {"c": connection_id})
    jobs.run_scan(ctx(0), str(org), str(scan_id))  # permanent: returns, never retried
    assert scan(owner, scan_id) == {
        "status": "blocked",
        "attempts": 0,
        "error_code": "scanning.connection_not_active",
    }
    assert [e["status"] for e in finished(caplog)] == ["blocked"]


def start_schedule(app: Engine, org: uuid.UUID, connection_id: uuid.UUID) -> bool:
    with org_session(app, org) as session:
        return defer_schedule(session, org, connection_id, in_seconds=0)


def run_schedule(owner: Engine, org: uuid.UUID, connection_id: uuid.UUID) -> None:
    """As the worker does: the waiting job becomes doing, then the task runs."""
    with owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE procrastinate_jobs SET status = 'doing' WHERE task_name = :t"
                " AND args->>'connection_id' = :c AND status = 'todo'"
            ),
            {"t": SCHEDULE_TASK, "c": str(connection_id)},
        )
    jobs.schedule_scan(str(org), str(connection_id))


def test_the_daily_chain_scans_an_active_connection_and_defers_itself(
    owner: Engine, app: Engine, store: LocalScanStore
) -> None:
    org, connection_id = connected(owner, app)
    assert start_schedule(app, org, connection_id)
    assert not start_schedule(app, org, connection_id)  # one waiting job per connection
    run_schedule(owner, org, connection_id)
    run_schedule(owner, org, connection_id)  # a scan is already queued: skipped
    with owner.connect() as conn:
        triggers = conn.execute(
            text("SELECT trigger FROM scans WHERE connection_id = :c"), {"c": connection_id}
        ).scalars()
        assert list(triggers) == ["schedule"]
        later = conn.execute(text("SELECT now() + interval '23 hours'")).scalar_one()
    waiting = jobs_of(owner, SCHEDULE_TASK, "connection_id", connection_id)
    todo = [j for j in waiting if j["status"] == "todo"]
    assert len(todo) == 1 and todo[0]["scheduled_at"] > later


@pytest.mark.parametrize(("status", "goes_on"), [("incomplete", True), ("disconnected", False)])
def test_the_chain_waits_out_an_inactive_connection_and_ends_with_a_disconnected_one(
    owner: Engine, app: Engine, store: LocalScanStore, status: str, goes_on: bool
) -> None:
    org, connection_id = connected(owner, app, status)
    assert start_schedule(app, org, connection_id)
    run_schedule(owner, org, connection_id)
    with owner.connect() as conn:
        count = text("SELECT count(*) FROM scans WHERE connection_id = :c")
        assert conn.execute(count, {"c": connection_id}).scalar_one() == 0
    todo = [
        j
        for j in jobs_of(owner, SCHEDULE_TASK, "connection_id", connection_id)
        if j["status"] == "todo"
    ]
    assert len(todo) == (1 if goes_on else 0)


class BrokenRunner:
    def run(self, job: object) -> int:
        raise OSError("docker: cannot connect")


def test_a_runner_that_raises_counts_as_a_transient_engine_failure(
    owner: Engine, app: Engine, store: LocalScanStore, caplog: pytest.LogCaptureFixture
) -> None:
    configure_scans(ScanConfig(store, BrokenRunner(), EXPECTED, 3600))
    org, connection_id = connected(owner, app)
    scan_id = queued(app, org, connection_id)
    with pytest.raises(ScanTransientError):
        jobs.run_scan(ctx(0), str(org), str(scan_id))
    assert scan(owner, scan_id)["error_code"] == "scanning.engine_failed"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ["scan runner raised OSError"]  # the type only, never the message


def test_a_lost_database_is_retried_and_only_the_last_attempt_fails_the_scan(
    owner: Engine,
    app: Engine,
    store: LocalScanStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, connection_id = connected(owner, app)
    scan_id = queued(app, org, connection_id)

    def lost(*args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection lost"))

    monkeypatch.setattr(jobs, "start_attempt", lost)
    with pytest.raises(OperationalError):
        jobs.run_scan(ctx(0), str(org), str(scan_id))
    assert scan(owner, scan_id)["status"] == "queued"  # the retry runs it
    with pytest.raises(OperationalError):
        jobs.run_scan(ctx(3), str(org), str(scan_id))
    assert scan(owner, scan_id)["status"] == "failed"  # no retry left: never active for good


def test_a_refused_schedule_keeps_the_rest_of_its_transaction(
    owner: Engine, app: Engine, store: LocalScanStore
) -> None:
    org, connection_id = connected(owner, app)
    assert start_schedule(app, org, connection_id)
    with org_session(app, org) as session:
        made = queue_scan(session, org, connection_id, trigger="schedule").id
        assert not defer_schedule(session, org, connection_id, in_seconds=0)
    assert scan(owner, made)["status"] == "queued"  # the refused insert rolled back alone
