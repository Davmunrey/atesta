"""One scan attempt (scanner-connectors spec, Scan lifecycle, run_scan steps 1 and 3).

The worker runs step 1 in one transaction, calls the runner with no transaction open (step 2),
and runs step 3 in another transaction. Each step locks the scan row. A result for an attempt
that is no longer the scan's current one changes nothing, so a redelivered job is harmless.

The scan.finished event (ids, codes and counts only; rule 2) is returned, not logged: the worker
logs it after its transaction commits, so a rolled-back end never reports a finished scan.
"""

import contextlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atesta_api.modules.connections.api import (
    ConnectionStateError,
    TenantMismatchError,
    VerificationReport,
    record_verification,
    scan_target,
)
from atesta_api.modules.notifications.api import queue_event
from atesta_api.modules.scanning.error_codes import (
    BLOCKED_CODES,
    CONNECTION_NOT_ACTIVE,
    ENGINE_FAILED,
    TENANT_MISMATCH,
    TRANSIENT_ERRORS,
)
from atesta_api.modules.scanning.expected import exclusions
from atesta_api.modules.scanning.ingest import ScanNotFoundError
from atesta_api.modules.scanning.lifecycle import SCHEDULE_EVERY_SECONDS, defer_schedule
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
VERIFICATION_FILE = "verification.json"  # the wrapper's report, beside the attempt's output

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
    event_id = record(
        session,
        organization_id=scan.organization_id,
        action=f"scan.{status}",
        target_type="scan",
        target_id=str(scan.id),
        metadata={
            "provider": scan.provider,
            "error_code": error_code,
            "connection_id": str(scan.connection_id),
            "trigger": scan.trigger,
        },
    )
    queue_event(session, scan.organization_id, event_id, f"scan.{status}")  # notifications spec
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
    # Onboarding (#331): the activation scan verifies a `verifying` connection, pins the tenant
    # bound at sign-in and names the consenting admin for the binding check (step 6).
    activating = target is not None and target.verifying and scan.trigger == "activation"
    tenant = None if target is None else target.external_tenant_id
    if activating and target is not None and tenant is None:
        tenant = target.ms_tenant_id
    if target is None or not (target.active or activating) or tenant is None:
        return Started(None, _end(session, scan, "blocked", CONNECTION_NOT_ACTIVE))
    scan.status, scan.attempts, scan.error_code = "running", attempt, None
    scan.started_at = func.now()
    job = ScanJob(organization_id, scan.id, attempt, scan.provider, target.credential_ref)
    excluded = sorted(exclusions(expected_root, scan.provider))
    data: dict[str, object] = {
        "organization_id": str(organization_id),
        "scan_id": str(scan.id),
        "attempt": attempt,
        "provider": scan.provider,
        "tenant": tenant,
        "excluded": excluded,
        "allowlist_version": target.allowlist_version,
    }
    if activating and target.consented_by_oid is not None:
        data["admin_oid"] = target.consented_by_oid
    prefix = output_prefix(organization_id, scan.id, attempt).removesuffix("out/")
    _write_job_file(store, prefix + JOB_FILE, json.dumps(data, sort_keys=True).encode())
    session.flush()
    return Started(job, None)


def _verification(store: ScanStore | None, job: ScanJob) -> VerificationReport | None:
    """The wrapper's report for this attempt; None when absent or not what the wrapper writes.

    Untrusted output (rule 5): only these fields are read, each as text.
    """
    if store is None:
        return None
    key = output_prefix(job.organization_id, job.scan_id, job.attempt) + VERIFICATION_FILE
    try:
        data = json.loads(store.read(key))
        tenant = data["tenant_id"]
        report = VerificationReport(
            verdict=str(data["verdict"]),
            tenant_id=None if tenant is None else str(tenant),
            granted={str(k): [str(i) for i in ids] for k, ids in data["granted"].items()},
            missing=[str(item) for item in data["missing"]],
            extra=[str(item) for item in data["extra"]],
            limits=[str(item) for item in data["limits"]],
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return report  # callers act only on `ok` or a verdict in BLOCKED_CODES


def _record(session: Session, scan: Scan, report: VerificationReport) -> None:
    # Disconnected meanwhile: there is no connection state left to change.
    with contextlib.suppress(ConnectionStateError):
        record_verification(session, scan.organization_id, scan.connection_id, report)


def finish_attempt(
    session: Session,
    job: ScanJob,
    exit_code: int,
    *,
    final: bool,
    store: ScanStore | None = None,
) -> Outcome:
    """Step 3: record the runner's exit. final: no retry is left for a transient failure.

    With the store, the wrapper's verification report is recorded on the connection: an `ok`
    refreshes it before ingest, a refusal blocks the connection as well as the scan.
    """
    scan = _locked(session, job.scan_id)
    if scan.status != "running" or scan.attempts != job.attempt:
        return Outcome(scan.status, False, None)  # a stale attempt
    report = _verification(store, job) if exit_code in (DONE, VERIFICATION_REFUSED) else None
    if exit_code == DONE:
        if report is not None and report.verdict == "ok":
            try:
                _record(session, scan, report)
            except TenantMismatchError:  # verified a tenant other than the one bound or pinned
                return Outcome("blocked", False, _end(session, scan, "blocked", TENANT_MISMATCH))
            if scan.trigger == "activation":  # the connection is active now: daily scans start
                defer_schedule(
                    session,
                    scan.organization_id,
                    scan.connection_id,
                    in_seconds=SCHEDULE_EVERY_SECONDS,
                )
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
    if exit_code == VERIFICATION_REFUSED:
        code = None
        if report is not None and report.verdict in BLOCKED_CODES:
            _record(session, scan, report)
            code = BLOCKED_CODES[report.verdict]
        return Outcome("blocked", False, _end(session, scan, "blocked", code))
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
