"""One scan attempt (scanner-connectors spec, Scan lifecycle, run_scan steps 1 and 3)."""

import uuid
from pathlib import Path
from typing import Any

import pytest
from atesta_api.modules.scanning.api import (
    INGEST_TASK,
    FixtureRunner,
    LocalScanStore,
    ScanJob,
    ScanNotFoundError,
    ended_event,
    exclusions,
    expected_checks,
    finish_attempt,
    ingest_scan,
    output_prefix,
    queue_scan,
    start_attempt,
)
from atesta_scanner.job import load_job
from sqlalchemy import text
from sqlalchemy.orm import Session

from .conftest import ORG_A
from .test_scan_queue import USER, as_org, connection

REPO = Path(__file__).resolve().parents[4]
EXPECTED = REPO / "scanner" / "expected"
FIXTURES = REPO / "scanner" / "fixtures" / "synthetic"
TENANT = "11111111-1111-4111-8111-111111111111"  # the synthetic fixtures' tenant
EVENT_KEYS = {
    "event",
    "organization_id",
    "scan_id",
    "connection_id",
    "provider",
    "status",
    "attempts",
    "duration_seconds",
    "error_code",
}


@pytest.fixture(autouse=True)
def dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATESTA_ENV", "test")


@pytest.fixture
def store(tmp_path: Path) -> LocalScanStore:
    return LocalScanStore(tmp_path / "scans")


@pytest.fixture
def scan_id(db_rollback: Session) -> uuid.UUID:
    connection_id = connection(db_rollback, tenant=TENANT)
    return queue_scan(db_rollback, ORG_A, connection_id, trigger="user", requested_by=USER).id


def row(session: Session, scan_id: uuid.UUID) -> dict[str, Any]:
    query = text(
        "SELECT status, attempts, error_code, output_prefix, started_at IS NOT NULL AS started,"
        " finished_at IS NOT NULL AS finished FROM scans WHERE id = :id"
    )
    return dict(session.execute(query, {"id": scan_id}).mappings().one())


def audit(session: Session, scan_id: uuid.UUID) -> list[str]:
    query = text(
        "SELECT action FROM audit_events WHERE target_type = 'scan' AND target_id = :id"
        " AND action <> 'scan.requested' ORDER BY occurred_at"
    )
    return list(session.execute(query, {"id": str(scan_id)}).scalars())


def ingest_jobs(session: Session, scan_id: uuid.UUID) -> list[dict[str, str]]:
    query = text(
        "SELECT args FROM procrastinate_jobs WHERE task_name = :t AND args->>'scan_id' = :id"
    )
    return list(session.execute(query, {"t": INGEST_TASK, "id": str(scan_id)}).scalars())


def start(session: Session, scan_id: uuid.UUID, store: LocalScanStore, attempt: int = 1) -> Any:
    return start_attempt(
        session, ORG_A, scan_id, attempt=attempt, store=store, expected_root=EXPECTED
    )


def test_an_attempt_starts_with_a_job_file_the_scanner_accepts(
    db_rollback: Session, scan_id: uuid.UUID, store: LocalScanStore
) -> None:
    started = start(db_rollback, scan_id, store)
    assert (started.job, started.finished) == (ScanJob(ORG_A, scan_id, 1, "m365"), None)
    assert row(db_rollback, scan_id) == {
        "status": "running",
        "attempts": 1,
        "error_code": None,
        "output_prefix": None,
        "started": True,
        "finished": False,
    }
    raw = store.read(f"{ORG_A}/scans/{scan_id}/attempt-1/job.json")
    job = load_job(raw)  # the wrapper's strict loader: ids, tenant pin and exclusions, no secret
    assert (job.organization_id, job.scan_id, job.attempt) == (str(ORG_A), str(scan_id), 1)
    assert (job.provider, job.tenant) == ("m365", TENANT)
    assert job.excluded == tuple(sorted(exclusions(EXPECTED, "m365")))
    again = start(db_rollback, scan_id, store)  # a redelivered job rewrites the same file
    assert again.job == started.job


def test_a_scan_past_running_is_not_started_again(
    db_rollback: Session, scan_id: uuid.UUID, store: LocalScanStore
) -> None:
    db_rollback.execute(text("UPDATE scans SET status = 'collected'"))
    started = start(db_rollback, scan_id, store)
    assert (started.job, started.finished) == (None, None)
    assert store.list(f"{ORG_A}/scans/{scan_id}/") == []


def test_a_connection_no_longer_active_blocks_the_scan_for_good(
    db_rollback: Session, scan_id: uuid.UUID, store: LocalScanStore
) -> None:
    db_rollback.execute(text("UPDATE connections SET status = 'disconnected'"))
    started = start(db_rollback, scan_id, store)
    assert started.job is None
    assert row(db_rollback, scan_id) == {
        "status": "blocked",
        "attempts": 0,
        "error_code": "scanning.connection_not_active",
        "output_prefix": None,
        "started": False,
        "finished": True,
    }
    assert audit(db_rollback, scan_id) == ["scan.blocked"]
    event = started.finished
    assert set(event) == EVENT_KEYS
    assert event["event"] == "scan.finished"
    assert (event["status"], event["attempts"]) == ("blocked", 0)
    assert event["error_code"] == "scanning.connection_not_active"
    assert (event["scan_id"], event["organization_id"]) == (str(scan_id), str(ORG_A))
    assert isinstance(event["duration_seconds"], int) and event["duration_seconds"] >= 0


def test_a_finished_run_is_collected_and_its_ingest_deferred(
    db_rollback: Session, scan_id: uuid.UUID, store: LocalScanStore
) -> None:
    job = start(db_rollback, scan_id, store).job
    assert FixtureRunner(store, FIXTURES).run(job) == 0
    outcome = finish_attempt(db_rollback, job, 0, final=False)
    assert (outcome.status, outcome.retry, outcome.finished) == ("collected", False, None)
    assert row(db_rollback, scan_id)["output_prefix"] == output_prefix(ORG_A, scan_id, 1)
    assert ingest_jobs(db_rollback, scan_id) == [
        {"organization_id": str(ORG_A), "scan_id": str(scan_id)}
    ]
    assert audit(db_rollback, scan_id) == []  # ingest closes the scan and audits it


@pytest.mark.parametrize(
    ("exit_code", "error_code"),
    [
        (11, "scanning.engine_failed"),  # credential unavailable
        (12, "scanning.engine_failed"),  # verification transient
        (20, "scanning.engine_failed"),
        (21, "scanning.timeout"),
        (30, "scanning.output_invalid"),
        (137, "scanning.engine_failed"),  # killed: any unknown code is transient
    ],
)
def test_a_transient_failure_is_retried_then_fails(
    db_rollback: Session,
    scan_id: uuid.UUID,
    store: LocalScanStore,
    exit_code: int,
    error_code: str,
) -> None:
    first = start(db_rollback, scan_id, store).job
    outcome = finish_attempt(db_rollback, first, exit_code, final=False)
    assert (outcome.status, outcome.retry, outcome.finished) == ("running", True, None)
    assert row(db_rollback, scan_id)["error_code"] == error_code
    second = start(db_rollback, scan_id, store, attempt=2).job
    assert second == ScanJob(ORG_A, scan_id, 2, "m365")
    second_file = store.read(f"{ORG_A}/scans/{scan_id}/attempt-2/job.json")
    assert load_job(second_file).attempt == 2  # each attempt has its own folder and job file
    assert row(db_rollback, scan_id)["error_code"] is None  # a new attempt starts clean
    last = finish_attempt(db_rollback, second, exit_code, final=True)
    assert (last.status, last.retry) == ("failed", False)
    assert last.finished is not None
    assert (last.finished["status"], last.finished["attempts"]) == ("failed", 2)
    assert last.finished["error_code"] == error_code
    assert row(db_rollback, scan_id) == {
        "status": "failed",
        "attempts": 2,
        "error_code": error_code,
        "output_prefix": None,
        "started": True,
        "finished": True,
    }
    assert audit(db_rollback, scan_id) == ["scan.failed"]
    assert ingest_jobs(db_rollback, scan_id) == []


def test_a_refused_verification_blocks_the_scan_without_retry(
    db_rollback: Session, scan_id: uuid.UUID, store: LocalScanStore
) -> None:
    job = start(db_rollback, scan_id, store).job
    outcome = finish_attempt(db_rollback, job, 10, final=False)
    assert (outcome.status, outcome.retry) == ("blocked", False)
    assert outcome.finished is not None and outcome.finished["status"] == "blocked"
    assert audit(db_rollback, scan_id) == ["scan.blocked"]


def test_a_stale_attempts_result_changes_nothing(
    db_rollback: Session, scan_id: uuid.UUID, store: LocalScanStore
) -> None:
    stale = start(db_rollback, scan_id, store).job
    start(db_rollback, scan_id, store, attempt=2)
    outcome = finish_attempt(db_rollback, stale, 0, final=False)
    assert (outcome.status, outcome.retry, outcome.finished) == ("running", False, None)
    assert row(db_rollback, scan_id)["attempts"] == 2
    assert ingest_jobs(db_rollback, scan_id) == []


def test_an_unknown_scan_is_not_found(db_rollback: Session, store: LocalScanStore) -> None:
    as_org(db_rollback, ORG_A)
    with pytest.raises(ScanNotFoundError):
        start(db_rollback, uuid.uuid4(), store)
    with pytest.raises(ScanNotFoundError):
        finish_attempt(db_rollback, ScanJob(ORG_A, uuid.uuid4(), 1, "m365"), 0, final=False)


def test_one_scan_runs_from_queue_to_ingest_and_reports_its_end_once(
    db_rollback: Session, scan_id: uuid.UUID, store: LocalScanStore
) -> None:
    job = start(db_rollback, scan_id, store).job
    assert ended_event(db_rollback, scan_id) is None
    assert FixtureRunner(store, FIXTURES).run(job) == 0
    assert finish_attempt(db_rollback, job, 0, final=False).status == "collected"
    assert ended_event(db_rollback, scan_id) is None  # collected is not an end
    status = ingest_scan(
        db_rollback,
        scan_id,
        store=store,
        tenant=TENANT,
        listed=expected_checks(EXPECTED, "m365"),
        excluded={},  # the synthetic fixture holds PowerShell-backed findings, as atesta-dev-scan
    )
    event = ended_event(db_rollback, scan_id)
    assert event is not None and set(event) == EVENT_KEYS
    assert (event["status"], event["attempts"], event["error_code"]) == (status, 1, None)
    assert status in ("succeeded", "partial")
