"""Queue a scan (scanner-connectors spec, Scan lifecycle).

One transaction inserts the scan and defers its run on the session's own connection, so both
commit or neither does. The partial unique index on scans allows one queued or running scan per
connection; a second request is refused inside a savepoint, so a caller such as the schedule job
can skip it and go on. The caller has already entered the org context.

"Scan now" has a daily budget (#265): each scan reads the customer's whole tenant, and Graph and
Google throttle per tenant and per app. `user` scans are counted per connection over the Madrid
calendar day, read from the database clock; `schedule` and `activation` scans never are.
"""

import uuid
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from procrastinate.exceptions import AlreadyEnqueued
from psycopg.errors import UniqueViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from atesta_api.modules.connections.api import scan_target
from atesta_api.modules.scanning.expected import ENGINE_VERSION
from atesta_api.modules.scanning.ingest import ENGINE
from atesta_api.modules.scanning.models import Scan
from atesta_api.platform.audit import record
from atesta_api.platform.queue import defer

RUN_TASK = "atesta:run_scan"  # the worker's namespaced name; a worker test pins it
ACTIVE_SCAN_INDEX = "uq_scans_one_active_per_connection"
GOOGLE_POLICY_API_LOCK = "gws-policy-api"  # 1 QPS per GCP project, shared by every Google scan
SCHEDULE_TASK = "atesta:schedule_scan"
SCHEDULE_EVERY_SECONDS = 24 * 3600
_UNSCHEDULED = frozenset({"disconnected", "revoked"})  # the daily chain ends with the connection
MANUAL_SCANS_PER_DAY = 6  # owner, 2026-11-23 (#265)
MADRID = ZoneInfo("Europe/Madrid")

type Trigger = Literal["schedule", "user", "activation"]


class ConnectionNotFoundError(LookupError):
    """No such connection in this org."""


class ConnectionNotActiveError(RuntimeError):
    """Only an active connection is scanned; permanent, never retried."""


class AlreadyQueuedError(RuntimeError):
    """The connection already has a queued or running scan."""


class DailyLimitError(RuntimeError):
    """The connection has used today's manual scans; retry_at is the next Madrid midnight."""

    def __init__(self, retry_at: datetime) -> None:
        super().__init__(retry_at.isoformat())
        self.retry_at = retry_at


def madrid_day(now: datetime) -> tuple[datetime, datetime]:
    """The Madrid calendar day holding `now`, as [start, end) in UTC; 23 h or 25 h on DST days."""
    if now.tzinfo is None:
        raise ValueError("now needs a timezone")
    day = now.astimezone(MADRID).date()
    start = datetime(day.year, day.month, day.day, tzinfo=MADRID)
    following = day + timedelta(days=1)
    end = datetime(following.year, following.month, following.day, tzinfo=MADRID)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def _check_daily_budget(
    session: Session, organization_id: uuid.UUID, connection_id: uuid.UUID
) -> None:
    start, end = madrid_day(session.execute(select(func.now())).scalar_one())
    used = session.execute(
        select(func.count())
        .select_from(Scan)
        .where(
            Scan.organization_id == organization_id,
            Scan.connection_id == connection_id,
            Scan.trigger == "user",
            Scan.queued_at >= start,
        )
    ).scalar_one()
    if used >= MANUAL_SCANS_PER_DAY:
        raise DailyLimitError(end)


def _is_active_scan_conflict(exc: IntegrityError) -> bool:
    orig = exc.orig
    return isinstance(orig, UniqueViolation) and orig.diag.constraint_name == ACTIVE_SCAN_INDEX


def scan_lock(provider: str, connection_id: uuid.UUID) -> str:
    """No two attempts of one connection at once; Google scans also share the Policy API."""
    return GOOGLE_POLICY_API_LOCK if provider == "google_workspace" else f"conn:{connection_id}"


def queue_scan(
    session: Session,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    *,
    trigger: Trigger,
    requested_by: uuid.UUID | None = None,
    delay_seconds: int | None = None,
) -> Scan:
    """delay_seconds holds the run back, as Google's propagation retry does (issue 398)."""
    target = scan_target(session, organization_id, connection_id)
    if target is None:
        raise ConnectionNotFoundError(str(connection_id))
    if not (target.active or (trigger == "activation" and target.verifying)):
        raise ConnectionNotActiveError(target.status)  # only activation runs while verifying
    if trigger == "user":
        _check_daily_budget(session, organization_id, connection_id)
    scan = Scan(
        organization_id=organization_id,
        connection_id=connection_id,
        provider=target.provider,
        trigger=trigger,
        status="queued",
        engine=ENGINE,
        engine_version=ENGINE_VERSION,
        requested_by=requested_by,
    )
    try:
        with session.begin_nested():
            session.add(scan)
    except IntegrityError as exc:
        if not _is_active_scan_conflict(exc):
            raise
        raise AlreadyQueuedError(str(connection_id)) from None
    session.refresh(scan)
    record(
        session,
        organization_id=organization_id,
        action="scan.requested",
        target_type="scan",
        target_id=str(scan.id),
        actor_user_id=requested_by,
        metadata={"provider": scan.provider, "trigger": trigger},
    )
    session.flush()
    defer(  # commits with the scan row
        session,
        RUN_TASK,
        queue="scans",
        lock=scan_lock(scan.provider, connection_id),
        schedule_in_seconds=delay_seconds,
        organization_id=str(organization_id),
        scan_id=str(scan.id),
    )
    return scan


def defer_schedule(
    session: Session, organization_id: uuid.UUID, connection_id: uuid.UUID, *, in_seconds: int
) -> bool:
    """Defer the connection's next schedule_scan; False when one is already waiting.

    queueing_lock sched:<connection_id> keeps one waiting job per connection, so activating a
    connection twice never starts a second daily chain.
    """
    try:
        with session.begin_nested():  # a refused insert must not abort the caller's transaction
            defer(
                session,
                SCHEDULE_TASK,
                queue="scans",
                queueing_lock=f"sched:{connection_id}",
                schedule_in_seconds=in_seconds,
                organization_id=str(organization_id),
                connection_id=str(connection_id),
            )
    except AlreadyEnqueued:
        return False
    return True


def scheduled_scan(
    session: Session, organization_id: uuid.UUID, connection_id: uuid.UUID
) -> Scan | None:
    """schedule_scan job: scan an active connection, then defer itself 24 h ahead.

    Skipped when a scan is already queued or running; the chain goes on while the connection is
    neither disconnected nor revoked, so a connection that recovers is scanned again.
    """
    target = scan_target(session, organization_id, connection_id)
    if target is None or target.status in _UNSCHEDULED:
        return None
    scan = None
    if target.active:
        try:
            scan = queue_scan(session, organization_id, connection_id, trigger="schedule")
        except AlreadyQueuedError:
            scan = None
    defer_schedule(session, organization_id, connection_id, in_seconds=SCHEDULE_EVERY_SECONDS)
    return scan
