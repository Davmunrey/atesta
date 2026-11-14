"""Queue a scan (scanner-connectors spec, Scan lifecycle).

One transaction inserts the scan and defers its run on the session's own connection, so both
commit or neither does. The partial unique index on scans allows one queued or running scan per
connection; a second request is refused inside a savepoint, so a caller such as the schedule job
can skip it and go on. The caller has already entered the org context.
"""

import uuid
from typing import Literal

from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from atesta_api.modules.connections.api import scan_target
from atesta_api.modules.scanning.expected import ENGINE_VERSION
from atesta_api.modules.scanning.ingest import ENGINE
from atesta_api.modules.scanning.models import Scan
from atesta_api.platform.audit import record
from atesta_api.platform.queue import defer

RUN_TASK = "atesta:run_scan"  # the worker's namespaced name; a worker test pins it (PR 8b)
ACTIVE_SCAN_INDEX = "uq_scans_one_active_per_connection"

type Trigger = Literal["schedule", "user", "activation"]


class ConnectionNotFoundError(LookupError):
    """No such connection in this org."""


class ConnectionNotActiveError(RuntimeError):
    """Only an active connection is scanned; permanent, never retried."""


class AlreadyQueuedError(RuntimeError):
    """The connection already has a queued or running scan."""


def _is_active_scan_conflict(exc: IntegrityError) -> bool:
    orig = exc.orig
    return isinstance(orig, UniqueViolation) and orig.diag.constraint_name == ACTIVE_SCAN_INDEX


def queue_scan(
    session: Session,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    *,
    trigger: Trigger,
    requested_by: uuid.UUID | None = None,
) -> Scan:
    target = scan_target(session, organization_id, connection_id)
    if target is None:
        raise ConnectionNotFoundError(str(connection_id))
    if not target.active:
        raise ConnectionNotActiveError(target.status)
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
    ids = {"organization_id": str(organization_id), "scan_id": str(scan.id)}
    defer(session, RUN_TASK, queue="scans", **ids)  # commits with the scan row
    return scan
