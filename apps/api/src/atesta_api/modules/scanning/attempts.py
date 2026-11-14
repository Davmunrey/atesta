"""One scan attempt (scanner-connectors spec, Scan lifecycle, run_scan steps 1 and 3).

The worker runs step 1 in one transaction, calls the runner with no transaction open (step 2),
and runs step 3 in another transaction. Each step locks the scan row. A result for an attempt
that is no longer the scan's current one changes nothing, so a redelivered job is harmless.

The scan.finished event (ids, codes and counts only; rule 2) is returned, not logged: the worker
logs it after its transaction commits, so a rolled-back end never reports a finished scan.
"""

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atesta_api.modules.connections.api import scan_target
from atesta_api.modules.scanning.expected import exclusions
from atesta_api.modules.scanning.ingest import ScanNotFoundError
from atesta_api.modules.scanning.models import Scan
from atesta_api.modules.scanning.runners import (
    JOB_FILE,
    OutputExistsError,
    ScanJob,
    ScanStore,
    output_prefix,
)
from atesta_api.platform.audit import record
from atesta_api.platform.queue import defer

INGEST_TASK = "atesta:ingest_scan"  # the worker's namespaced name; a worker test pins it
DONE = 0
VERIFICATION_REFUSED = 10  # the only permanent wrapper exit (scanner/atesta_scanner/exits.py)
TRANSIENT_ERRORS = {21: "scanning.timeout", 30: "scanning.output_invalid"}
ENGINE_FAILED = "scanning.engine_failed"  # 11, 12, 20 and any code the wrapper never returns

type Event = Mapping[str, str | int | None]


class ScanTransientError(RuntimeError):
    """The attempt failed transiently; the worker raises it after commit so the job is retried."""


@dataclass(frozen=True, slots=True)
class Started:
    job: ScanJob | None  # None: nothing to run
    finished: Event | None  # set when the scan ended here (blocked)


@dataclass(frozen=True, slots=True)
class Outcome:
    status: str
    retry: bool
    finished: Event | None


def _locked(session: Session, scan_id: uuid.UUID) -> Scan:
    scan = session.scalars(
        select(Scan)
        .where(Scan.id == scan_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if scan is None:
        raise ScanNotFoundError(str(scan_id))
    return scan


def _end(session: Session, scan: Scan, status: str, error_code: str | None) -> Event:
    scan.status, scan.error_code, scan.finished_at = status, error_code, func.now()
    record(
        session,
        organization_id=scan.organization_id,
        action=f"scan.{status}",
        target_type="scan",
        target_id=str(scan.id),
        metadata={"provider": scan.provider, "error_code": error_code},
    )
    session.flush()
    session.refresh(scan)
    return finished_event(scan)


def finished_event(scan: Scan) -> Event:
    """The structured scan.finished event of an ended scan; never a value from scan output."""
    if scan.finished_at is None:
        raise ValueError("the scan has not finished")
    return {
        "event": "scan.finished",
        "organization_id": str(scan.organization_id),
        "scan_id": str(scan.id),
        "connection_id": str(scan.connection_id),
        "provider": scan.provider,
        "status": scan.status,
        "attempts": scan.attempts,
        "duration_seconds": int((scan.finished_at - scan.queued_at).total_seconds()),
        "error_code": scan.error_code,
    }


def ended_event(session: Session, scan_id: uuid.UUID) -> Event | None:
    """scan.finished of a scan that has ended (ingest closes collected scans); else None."""
    scan = session.scalars(select(Scan).where(Scan.id == scan_id)).one_or_none()
    if scan is None:
        raise ScanNotFoundError(str(scan_id))
    return None if scan.finished_at is None else finished_event(scan)


def _write_job_file(store: ScanStore, key: str, data: bytes) -> None:
    """Write-once; a redelivered job may find the identical file it wrote before."""
    try:
        store.write(key, data)
    except OutputExistsError:
        if store.read(key) != data:
            raise


def start_attempt(
    session: Session,
    organization_id: uuid.UUID,
    scan_id: uuid.UUID,
    *,
    attempt: int,
    store: ScanStore,
    expected_root: Path,
) -> Started:
    """Step 1: mark the scan running for this attempt and write its job file (ids, no secret)."""
    scan = _locked(session, scan_id)
    if scan.status not in ("queued", "running"):
        return Started(None, None)
    target = scan_target(session, organization_id, scan.connection_id)
    if target is None or not target.active or target.external_tenant_id is None:
        return Started(None, _end(session, scan, "blocked", "scanning.connection_not_active"))
    scan.status, scan.attempts, scan.error_code = "running", attempt, None
    scan.started_at = func.now()
    job = ScanJob(organization_id, scan.id, attempt, scan.provider)
    excluded = sorted(exclusions(expected_root, scan.provider))
    data = {
        "organization_id": str(organization_id),
        "scan_id": str(scan.id),
        "attempt": attempt,
        "provider": scan.provider,
        "tenant": target.external_tenant_id,
        "excluded": excluded,
    }
    prefix = output_prefix(organization_id, scan.id, attempt).removesuffix("out/")
    _write_job_file(store, prefix + JOB_FILE, json.dumps(data, sort_keys=True).encode())
    session.flush()
    return Started(job, None)


def finish_attempt(session: Session, job: ScanJob, exit_code: int, *, final: bool) -> Outcome:
    """Step 3: record the runner's exit. final: no retry is left for a transient failure."""
    scan = _locked(session, job.scan_id)
    if scan.status != "running" or scan.attempts != job.attempt:
        return Outcome(scan.status, False, None)  # a stale attempt
    if exit_code == DONE:
        scan.status = "collected"
        scan.output_prefix = output_prefix(job.organization_id, scan.id, job.attempt)
        session.flush()
        defer(  # commits with the collected status
            session,
            INGEST_TASK,
            queue="scans",
            organization_id=str(job.organization_id),
            scan_id=str(scan.id),
        )
        return Outcome("collected", False, None)
    if exit_code == VERIFICATION_REFUSED:  # PR 9 records the verification report on the connection
        return Outcome("blocked", False, _end(session, scan, "blocked", None))
    error_code = TRANSIENT_ERRORS.get(exit_code, ENGINE_FAILED)
    if final:
        return Outcome("failed", False, _end(session, scan, "failed", error_code))
    scan.error_code = error_code
    session.flush()
    return Outcome("running", True, None)


def abandon_scan(session: Session, scan_id: uuid.UUID) -> Event | None:
    """Fail a scan whose job ended without a result, so no scan stays active for good."""
    scan = _locked(session, scan_id)
    if scan.status not in ("queued", "running"):
        return None
    return _end(session, scan, "failed", ENGINE_FAILED)
