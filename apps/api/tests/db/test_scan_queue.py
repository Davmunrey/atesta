"""Queue a scan (scanner-connectors spec, Scan lifecycle): one transaction, one active scan."""

import dataclasses
import uuid
from datetime import timedelta
from typing import Any

import pytest
from atesta_api.modules.connections.api import create_connection, scan_target
from atesta_api.modules.scanning.api import (
    ENGINE_VERSION,
    MANUAL_SCANS_PER_DAY,
    RUN_TASK,
    AlreadyQueuedError,
    ConnectionNotActiveError,
    ConnectionNotFoundError,
    DailyLimitError,
    queue_scan,
    scan_lock,
)
from atesta_api.platform.context import TenantContext
from atesta_api.platform.tenancy import set_tenant_context
from sqlalchemy import text
from sqlalchemy.orm import Session

from .conftest import ORG_A, ORG_B

TENANT = "22222222-2222-4222-8222-222222222222"
USER = uuid.UUID("33333333-3333-4333-8333-333333333333")


def connection(
    session: Session, status: str = "active", org: uuid.UUID = ORG_A, tenant: str | None = None
) -> uuid.UUID:
    as_org(session, org)
    made = create_connection(
        session, organization_id=org, provider="m365", display_name="M365", created_by=USER
    )
    if status != made.status:
        made.status = status
        made.external_tenant_id = (tenant or str(uuid.uuid4())) if status == "active" else None
    session.flush()
    return made.id


def as_org(session: Session, org: uuid.UUID) -> None:
    """Tests switch orgs inside one rolled-back transaction; production code never does."""
    set_tenant_context(session, TenantContext(organization_id=org))


def jobs(session: Session) -> list[tuple[Any, ...]]:
    # Only this module's orgs: HTTP tests elsewhere commit their own jobs (#331).
    query = text(
        "SELECT task_name, queue_name, lock, args FROM procrastinate_jobs"
        " WHERE task_name = :task AND args->>'organization_id' IN (:a, :b) ORDER BY id"
    )
    params = {"task": RUN_TASK, "a": str(ORG_A), "b": str(ORG_B)}
    return [tuple(r) for r in session.execute(query, params)]


def scans(session: Session) -> list[tuple[Any, ...]]:
    query = text("SELECT status, trigger FROM scans ORDER BY queued_at, id")
    return [tuple(r) for r in session.execute(query)]


def requested(session: Session) -> list[tuple[Any, ...]]:
    query = text(
        "SELECT target_id, actor_user_id, metadata FROM audit_events"
        " WHERE action = 'scan.requested' ORDER BY occurred_at"
    )
    return [tuple(r) for r in session.execute(query)]


def test_the_scan_target_holds_ids_and_references_never_a_secret(db_rollback: Session) -> None:
    connection_id = connection(db_rollback, tenant=TENANT)
    target = scan_target(db_rollback, ORG_A, connection_id)
    assert target is not None
    assert dataclasses.asdict(target) == {
        "connection_id": connection_id,
        "provider": "m365",
        "status": "active",
        "external_tenant_id": TENANT,
        "allowlist_version": "m365-v1",
        "credential_ref": None,  # M365 uses the platform's one credential (D5)
        "verifier_credential_ref": None,
        "google_client_id": None,
        "google_verifier_client_id": None,
        "google_subject_email": None,
        "ms_tenant_id": None,  # bound at sign-in (#314); ids only, never a secret
        "consented_by_oid": None,
    }
    assert target.active


def test_another_orgs_or_an_unknown_connection_has_no_target(db_rollback: Session) -> None:
    theirs = connection(db_rollback, org=ORG_B)
    assert scan_target(db_rollback, ORG_B, theirs) is not None
    # A job whose org and connection ids do not match finds no row, even in the right context.
    assert scan_target(db_rollback, ORG_A, theirs) is None
    as_org(db_rollback, ORG_A)
    assert scan_target(db_rollback, ORG_A, theirs) is None  # RLS
    assert scan_target(db_rollback, ORG_A, uuid.uuid4()) is None


def test_queueing_inserts_the_scan_and_defers_its_run_in_the_same_transaction(
    db_rollback: Session,
) -> None:
    connection_id = connection(db_rollback)
    scan = queue_scan(db_rollback, ORG_A, connection_id, trigger="user", requested_by=USER)
    assert (scan.status, scan.trigger, scan.provider) == ("queued", "user", "m365")
    assert (scan.attempts, scan.requested_by) == (0, USER)
    assert (scan.engine, scan.engine_version) == ("prowler", ENGINE_VERSION)
    args = {"organization_id": str(ORG_A), "scan_id": str(scan.id)}
    assert jobs(db_rollback) == [(RUN_TASK, "scans", f"conn:{connection_id}", args)]
    assert requested(db_rollback) == [(str(scan.id), USER, {"provider": "m365", "trigger": "user"})]


def test_a_second_scan_of_the_connection_waits_until_the_first_is_done(
    db_rollback: Session,
) -> None:
    connection_id = connection(db_rollback)
    first = queue_scan(db_rollback, ORG_A, connection_id, trigger="user", requested_by=USER)
    for status in ("queued", "running"):
        db_rollback.execute(text("UPDATE scans SET status = :s"), {"s": status})
        with pytest.raises(AlreadyQueuedError):
            queue_scan(db_rollback, ORG_A, connection_id, trigger="schedule")
        # The refusal rolls back only its own insert: the caller's transaction goes on.
        assert scans(db_rollback) == [(status, "user")]
        assert len(jobs(db_rollback)) == 1
    db_rollback.execute(text("UPDATE scans SET status = 'collected'"))
    second = queue_scan(db_rollback, ORG_A, connection_id, trigger="schedule")
    assert second.id != first.id
    assert [(r[2]["trigger"]) for r in requested(db_rollback)] == ["user", "schedule"]


@pytest.mark.parametrize(
    "status", ["pending_setup", "verifying", "incomplete", "over_privileged", "disconnected"]
)
def test_only_an_active_connection_is_scanned(db_rollback: Session, status: str) -> None:
    connection_id = connection(db_rollback, status)
    with pytest.raises(ConnectionNotActiveError):
        queue_scan(db_rollback, ORG_A, connection_id, trigger="user", requested_by=USER)
    assert (scans(db_rollback), jobs(db_rollback), requested(db_rollback)) == ([], [], [])


def test_an_unknown_connection_is_not_found(db_rollback: Session) -> None:
    theirs = connection(db_rollback, org=ORG_B)
    as_org(db_rollback, ORG_A)
    for connection_id in (theirs, uuid.uuid4()):
        with pytest.raises(ConnectionNotFoundError):
            queue_scan(db_rollback, ORG_A, connection_id, trigger="user")


def test_google_scans_share_one_lock_and_m365_scans_lock_their_connection() -> None:
    connection_id = uuid.uuid4()
    assert scan_lock("m365", connection_id) == f"conn:{connection_id}"
    assert scan_lock("google_workspace", connection_id) == "gws-policy-api"


MADRID_MIDNIGHT = text(
    "SELECT date_trunc('day', now() AT TIME ZONE 'Europe/Madrid') AT TIME ZONE 'Europe/Madrid'"
)
NEXT_MADRID_MIDNIGHT = text(
    "SELECT (date_trunc('day', now() AT TIME ZONE 'Europe/Madrid') + interval '1 day')"
    " AT TIME ZONE 'Europe/Madrid'"
)


def finish_active(session: Session) -> None:
    session.execute(
        text(
            "UPDATE scans SET status = 'failed', finished_at = now()"
            " WHERE status IN ('queued', 'running')"
        )
    )


def test_the_seventh_manual_scan_of_a_madrid_day_is_refused(db_rollback: Session) -> None:
    """#265: 6 user scans per connection per Madrid day; schedule and activation never count."""
    connection_id = connection(db_rollback)
    for _ in range(MANUAL_SCANS_PER_DAY):
        queue_scan(db_rollback, ORG_A, connection_id, trigger="user", requested_by=USER)
        finish_active(db_rollback)
    with pytest.raises(DailyLimitError) as refused:
        queue_scan(db_rollback, ORG_A, connection_id, trigger="user", requested_by=USER)
    assert refused.value.retry_at == db_rollback.scalar(NEXT_MADRID_MIDNIGHT)
    assert len(scans(db_rollback)) == MANUAL_SCANS_PER_DAY  # nothing written for the 7th
    assert len(requested(db_rollback)) == MANUAL_SCANS_PER_DAY
    queue_scan(db_rollback, ORG_A, connection_id, trigger="schedule")
    finish_active(db_rollback)
    queue_scan(db_rollback, ORG_A, connection_id, trigger="activation")
    other = connection(db_rollback)  # the budget is per connection
    queue_scan(db_rollback, ORG_A, other, trigger="user", requested_by=USER)


def test_manual_scans_before_the_last_madrid_midnight_do_not_count(db_rollback: Session) -> None:
    connection_id = connection(db_rollback)
    for _ in range(MANUAL_SCANS_PER_DAY):
        queue_scan(db_rollback, ORG_A, connection_id, trigger="user", requested_by=USER)
        finish_active(db_rollback)
    yesterday = db_rollback.scalar(MADRID_MIDNIGHT) - timedelta(minutes=1)
    db_rollback.execute(text("UPDATE scans SET queued_at = :at"), {"at": yesterday})
    scan = queue_scan(db_rollback, ORG_A, connection_id, trigger="user", requested_by=USER)
    assert scan.status == "queued"
