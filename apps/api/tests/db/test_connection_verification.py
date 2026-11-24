"""record_verification (scanner-connectors spec, Read-only verification; rule 1, fail closed)."""

import uuid
from typing import Any

import pytest
from atesta_api.modules.connections.api import (
    ConnectionStateError,
    TenantMismatchError,
    VerificationReport,
    create_connection,
    record_verification,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from .conftest import ORG_A
from .test_scan_queue import USER, as_org

TENANT = "44444444-4444-4444-8444-444444444444"
OTHER = "55555555-5555-4555-8555-555555555555"
GRANTED = {"app_roles": ["00000003-0000-0000-c000-000000000000/246dd0d5"]}
LIMITS = ("exchange_rbac_not_read",)


def report(verdict: str, tenant: str | None = TENANT, **extra: Any) -> VerificationReport:
    fields: dict[str, Any] = {
        "verdict": verdict,
        "tenant_id": tenant,
        "granted": GRANTED,
        "missing": (),
        "extra": (),
        "limits": LIMITS,
    }
    return VerificationReport(**(fields | extra))


@pytest.fixture
def connection_id(db_rollback: Session, monkeypatch: pytest.MonkeyPatch) -> uuid.UUID:
    monkeypatch.setenv("ATESTA_ENV", "test")
    as_org(db_rollback, ORG_A)
    made = create_connection(
        db_rollback, organization_id=ORG_A, provider="m365", display_name="M365", created_by=USER
    )
    made.status, made.ms_tenant_id = "verifying", TENANT  # after sign-in and consent
    db_rollback.flush()
    return made.id


def row(session: Session, connection_id: uuid.UUID) -> dict[str, Any]:
    query = text(
        "SELECT status, external_tenant_id, granted, verified_at IS NOT NULL AS verified,"
        " revoked_at IS NOT NULL AS revoked FROM connections WHERE id = :id"
    )
    return dict(session.execute(query, {"id": connection_id}).mappings().one())


def audit(session: Session, connection_id: uuid.UUID) -> list[tuple[str, dict[str, Any]]]:
    query = text(
        "SELECT action, metadata FROM audit_events WHERE target_type = 'connection'"
        " AND target_id = :id AND action <> 'connection.created' ORDER BY occurred_at, action"
    )
    return [tuple(r) for r in session.execute(query, {"id": str(connection_id)})]  # type: ignore[misc]


def test_the_first_ok_activates_and_pins_the_tenant(
    db_rollback: Session, connection_id: uuid.UUID
) -> None:
    assert record_verification(db_rollback, ORG_A, connection_id, report("ok")) == "active"
    assert row(db_rollback, connection_id) == {
        "status": "active",
        "external_tenant_id": TENANT,
        "granted": {
            "granted": GRANTED,
            "missing": [],
            "extra": [],
            "limits": list(LIMITS),
        },
        "verified": True,
        "revoked": False,
    }
    assert audit(db_rollback, connection_id) == [
        (
            "connection.verified",
            {"provider": "m365", "allowlist_version": "m365-v1", "missing": 0, "extra": 0},
        )
    ]


@pytest.mark.parametrize(
    ("verdict", "status", "action"),
    [
        ("incomplete", "incomplete", "connection.incomplete"),
        ("over_privileged", "over_privileged", "connection.over_privileged"),
        ("revoked", "revoked", "connection.revoked"),
    ],
)
def test_anything_but_ok_leaves_the_connection_unable_to_scan(
    db_rollback: Session, connection_id: uuid.UUID, verdict: str, status: str, action: str
) -> None:
    record_verification(db_rollback, ORG_A, connection_id, report("ok"))
    extra = ("app role 00000003-0000-0000-c000-000000000000/x",) if verdict != "ok" else ()
    got = record_verification(db_rollback, ORG_A, connection_id, report(verdict, extra=extra))
    assert got == status
    current = row(db_rollback, connection_id)
    assert (current["status"], current["external_tenant_id"]) == (status, TENANT)  # pin kept
    assert current["revoked"] == (verdict == "revoked")
    assert current["granted"]["extra"] == list(extra)
    [(name, details)] = [a for a in audit(db_rollback, connection_id) if a[0] == action]
    assert details["extra"] == len(extra)


def test_a_transient_verdict_changes_nothing(
    db_rollback: Session, connection_id: uuid.UUID
) -> None:
    assert record_verification(db_rollback, ORG_A, connection_id, report("transient")) == (
        "verifying"
    )
    assert row(db_rollback, connection_id)["verified"] is False
    assert audit(db_rollback, connection_id) == []


@pytest.mark.parametrize("pinned", [False, True])
def test_another_tenant_is_refused_before_and_after_the_pin(
    db_rollback: Session, connection_id: uuid.UUID, pinned: bool
) -> None:
    if pinned:
        record_verification(db_rollback, ORG_A, connection_id, report("ok"))
    with pytest.raises(TenantMismatchError):
        record_verification(db_rollback, ORG_A, connection_id, report("ok", tenant=OTHER))
    with pytest.raises(TenantMismatchError):
        record_verification(db_rollback, ORG_A, connection_id, report("ok", tenant=None))


def test_a_disconnected_connection_is_never_revived(
    db_rollback: Session, connection_id: uuid.UUID
) -> None:
    db_rollback.execute(
        text("UPDATE connections SET status = 'disconnected' WHERE id = :id"),
        {"id": connection_id},
    )
    with pytest.raises(ConnectionStateError):
        record_verification(db_rollback, ORG_A, connection_id, report("ok"))


def test_an_unknown_verdict_is_refused(db_rollback: Session, connection_id: uuid.UUID) -> None:
    with pytest.raises(ValueError, match="verdict"):
        record_verification(db_rollback, ORG_A, connection_id, report("passed"))


def test_a_local_credential_reference_is_refused_outside_development(
    db_rollback: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATESTA_ENV", "test")
    as_org(db_rollback, ORG_A)
    made = create_connection(
        db_rollback,
        organization_id=ORG_A,
        provider="google_workspace",
        display_name="Workspace",
        created_by=USER,
    )
    made.status = "verifying"
    made.credential_ref = f"local:google-{ORG_A}"
    db_rollback.flush()
    monkeypatch.setenv("ATESTA_ENV", "prod")
    with pytest.raises(RuntimeError, match="dev-only"):
        record_verification(db_rollback, ORG_A, made.id, report("ok", tenant="C0abc"))


def notify_jobs(session: Session) -> list[str]:
    """notify_event jobs this transaction queued, by the action of the event they name."""
    query = text(
        "SELECT a.action FROM procrastinate_jobs j JOIN audit_events a"
        " ON a.id = (j.args->>'event_id')::uuid"
        " WHERE j.task_name = 'notify_event' AND j.args->>'organization_id' = :o ORDER BY j.id"
    )
    return list(session.execute(query, {"o": str(ORG_A)}).scalars())


def test_a_revoked_or_over_privileged_connection_queues_a_notice_and_ok_does_not(
    db_rollback: Session, connection_id: uuid.UUID
) -> None:
    """notifications spec PR 2 (issue 386): the job exists only if the event does."""
    record_verification(db_rollback, ORG_A, connection_id, report("ok"))
    record_verification(db_rollback, ORG_A, connection_id, report("over_privileged", extra=["x"]))
    record_verification(db_rollback, ORG_A, connection_id, report("revoked"))
    assert notify_jobs(db_rollback) == ["connection.over_privileged", "connection.revoked"]
