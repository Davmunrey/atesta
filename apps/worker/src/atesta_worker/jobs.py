"""Job definitions. Arguments are ids only: queue tables have no RLS (ADR-012 amendment 2)."""

import json
import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from atesta_api.modules.compliance.api import due_items, incident_clocks, weekly_compliance
from atesta_api.modules.connections.api import inactive_connection_count
from atesta_api.modules.identity.api import expire_key_usage
from atesta_api.modules.notifications.api import (
    WeeklyFacts,
    defer_daily,
    handle_event,
    is_send_slot,
    notice_days,
    send_clock_notices,
    send_due_digest,
    send_weekly_summary,
)
from atesta_api.modules.scanning.api import (
    ScanNotFoundError,
    ScanTransientError,
    abandon_scan,
    ended_event,
    finish_attempt,
    ingest_collected,
    scan_counts,
    scheduled_scan,
    start_attempt,
)
from atesta_api.modules.scanning.api import rescore_reviews as rescore_org
from atesta_api.modules.scanning.api import snapshot_scores as score_scan
from procrastinate import Blueprint, JobContext, RetryStrategy
from sqlalchemy.exc import OperationalError

from atesta_worker import file_scans
from atesta_worker.context import org_session
from atesta_worker.scans import scan_config

MADRID = ZoneInfo("Europe/Madrid")
SCAN_RETRIES = 3  # after 300, 600 and 900 s (scanner-connectors spec, Retries)
RUNNER_ERROR_EXIT = 20  # a runner that raises counts as a failed engine run: transient
scan_events = logging.getLogger("atesta.scan")
retention_events = logging.getLogger("atesta.retention")
file_scan_events = logging.getLogger("atesta.file_scans")


def _report(event: Mapping[str, str | int | None] | None) -> None:
    """Log scan.finished after its transaction committed. Ids and codes only (rule 2)."""
    if event is not None:
        scan_events.info(json.dumps(dict(event), sort_keys=True))


async def retry_stalled_jobs(context: JobContext, timestamp: int) -> None:
    """Retry jobs whose worker stopped sending heartbeats (scanner-connectors spec)."""
    manager = context.app.job_manager
    for job in await manager.get_stalled_jobs():
        await manager.retry_job(job)


def snapshot_scores(organization_id: str, scan_id: str) -> None:
    """One snapshot per scoreable framework for an ingested scan. Idempotent per scan."""
    with org_session(organization_id, isolation_level="REPEATABLE READ") as session:
        score_scan(session, uuid.UUID(scan_id))


def _attempt(organization_id: str, scan_id: str, *, attempt: int, final: bool) -> None:
    """run_scan steps 1 to 3: two short transactions around a runner call with none open."""
    config = scan_config()
    org, scan = uuid.UUID(organization_id), uuid.UUID(scan_id)
    with org_session(organization_id) as session:
        started = start_attempt(
            session,
            org,
            scan,
            attempt=attempt,
            store=config.store,
            expected_root=config.expected_root,
            m365_credential_ref=config.m365_credential_ref,
        )
    _report(started.finished)
    if started.job is None:
        return  # past running, or blocked for good: never retried
    try:
        exit_code = config.runner.run(started.job)
    except Exception as error:  # noqa: BLE001 - any runner fault is one failed engine run
        scan_events.warning("scan runner raised %s", type(error).__name__)
        exit_code = RUNNER_ERROR_EXIT
    with org_session(organization_id) as session:
        outcome = finish_attempt(session, started.job, exit_code, final=final, store=config.store)
    _report(outcome.finished)
    if outcome.retry:
        raise ScanTransientError(f"scan {scan_id} attempt {attempt} exited {exit_code}")


def run_scan(context: JobContext, organization_id: str, scan_id: str) -> None:
    """One attempt of a scan. A job that ends without a result fails its scan, so no scan stays
    queued or running for good; ids that do not match find no scan and are never retried."""
    previous = context.job.attempts
    final = previous >= SCAN_RETRIES
    try:
        _attempt(organization_id, scan_id, attempt=previous + 1, final=final)
    except (ScanTransientError, ScanNotFoundError):
        raise
    except Exception as error:
        if isinstance(error, OperationalError) and not final:
            raise  # retried like a transient engine failure
        with org_session(organization_id) as session:
            event = abandon_scan(session, uuid.UUID(scan_id))
        _report(event)
        raise


def ingest_scan(organization_id: str, scan_id: str) -> None:
    """Ingest a collected scan; scan.finished is logged once, by the call that closed it."""
    config = scan_config()
    org, scan = uuid.UUID(organization_id), uuid.UUID(scan_id)
    with org_session(organization_id) as session:
        already = ended_event(session, scan)
        ingest_collected(session, org, scan, store=config.store, root=config.expected_root)
        event = None if already is not None else ended_event(session, scan)
    _report(event)


def schedule_scan(organization_id: str, connection_id: str) -> None:
    """Daily scan of an active connection; defers itself 24 h ahead (queueing_lock sched:<id>)."""
    with org_session(organization_id) as session:
        scheduled_scan(session, uuid.UUID(organization_id), uuid.UUID(connection_id))


def rescore_reviews(organization_id: str) -> None:
    """A correction of the latest scan's snapshots after a review. A retry adds one more link."""
    with org_session(organization_id, isolation_level="REPEATABLE READ") as session:
        rescore_org(session, uuid.UUID(organization_id))


def notify_event(organization_id: str, event_id: str) -> None:
    """Email owners and admins about one audit event (notifications spec PR 2)."""
    with org_session(organization_id) as session:
        handle_event(
            session, uuid.UUID(organization_id), uuid.UUID(event_id), now=datetime.now(UTC)
        )


def notify_clock(organization_id: str, incident_id: str) -> None:
    """Email the incident clock milestones owed now; recomputed, so a met clock sends nothing."""
    with org_session(organization_id) as session:
        view = incident_clocks(session, uuid.UUID(organization_id), uuid.UUID(incident_id))
        if view is not None:
            send_clock_notices(session, uuid.UUID(organization_id), view, now=datetime.now(UTC))


def notify_daily(organization_id: str) -> None:
    """The organization's daily job. 08:00 in Madrid: the due digest, and on Monday the weekly
    summary; then re-arm. After that, in its own transaction, the key usage log loses the rows
    older than 90 days (issue 353), so mail and retention never hold each other back."""
    org = uuid.UUID(organization_id)
    now = datetime.now(UTC)
    with org_session(organization_id) as session:
        if is_send_slot(now):  # a chain started at another hour only re-arms
            today = now.astimezone(MADRID).date()
            send_due_digest(session, org, due_items(session, org, notice_days(today)), now=now)
            if today.weekday() == 0:
                week = weekly_compliance(session, org, today=today)
                facts = WeeklyFacts(
                    frameworks=week.frameworks,
                    scans=scan_counts(session, org, since=now - timedelta(days=7)),
                    inactive_connections=inactive_connection_count(session),
                    due_soon=week.due_soon,
                    overdue=week.overdue,
                )
                send_weekly_summary(session, org, facts, now=now)
        defer_daily(session, org, now=now)
    with org_session(organization_id) as session:
        expired = expire_key_usage(session, org, now=now)
    if expired:  # ids and counts only (rule 2), logged after the delete committed
        retention_events.info(
            json.dumps(
                {"event": "key_usage.expired", "organization_id": organization_id, "rows": expired},
                sort_keys=True,
            )
        )


def poll_file_scans(timestamp: int) -> None:
    """Drain GuardDuty's malware scan results (evidence-malware-scanning spec). Counts only."""
    config = file_scans.file_scan_config()
    if config is None:
        return
    counts = file_scans.drain(config.queue, lambda body: file_scans.handle(body, config.bucket))
    if any(counts.values()):
        file_scan_events.info(json.dumps({"event": "file_scans.polled", **counts}, sort_keys=True))


def make_blueprint() -> Blueprint:
    """A fresh blueprint per app: Procrastinate renames task objects when an app adds them.

    Task names are explicit, so the task_name stored with each job never depends on the
    module path.
    """
    blueprint = Blueprint()
    task = blueprint.task(name="retry_stalled_jobs", queue="maintenance", pass_context=True)
    blueprint.periodic(cron="*/5 * * * *")(task(retry_stalled_jobs))
    # Transient database errors only (serialization failures, lost connections). A scan the
    # ids do not find is never retried.
    transient = RetryStrategy(max_attempts=3, retry_exceptions={OperationalError})
    blueprint.task(name="snapshot_scores", queue="scans", retry=transient)(snapshot_scores)
    blueprint.task(name="rescore_reviews", queue="scans", retry=transient)(rescore_reviews)
    blueprint.task(name="ingest_scan", queue="scans", retry=transient)(ingest_scan)
    # A lost schedule job would end the daily chain for good: transient database errors retry.
    blueprint.task(name="schedule_scan", queue="scans", retry=transient)(schedule_scan)
    scan_retry = RetryStrategy(
        max_attempts=SCAN_RETRIES,
        wait=300,
        linear_wait=300,
        retry_exceptions={ScanTransientError, OperationalError},
    )
    run = blueprint.task(name="run_scan", queue="scans", retry=scan_retry, pass_context=True)
    run(run_scan)
    # Each delivery is claimed once, so a retried notification job never emails twice.
    blueprint.task(name="notify_event", queue="notifications", retry=transient)(notify_event)
    blueprint.task(name="notify_clock", queue="notifications", retry=transient)(notify_clock)
    # A lost daily job would end the chain: transient database errors retry, as schedule_scan.
    blueprint.task(name="notify_daily", queue="notifications", retry=transient)(notify_daily)
    # Every minute; an unfinished message stays in SQS, so the job itself is never retried.
    poll = blueprint.task(name="poll_file_scans", queue="files")
    blueprint.periodic(cron="* * * * *")(poll(poll_file_scans))
    return blueprint
