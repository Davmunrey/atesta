"""Append-only audit events, written in the caller's transaction (FR-13)."""

import re
import uuid
from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    column,
    func,
    insert,
    table,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from atesta_api.platform.db import Base, TenantMixin

Scalar = str | int | bool | None
_ACTION = re.compile(r"[a-z][a-z_]*(\.[a-z][a-z_]*)+")


class AuditEvent(TenantMixin, Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None]
    action: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Scalar]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )
    request_id: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OperatorAuditEvent(Base):
    """The operator trail (ADR-017, "Audit"): every staff write and read, append-only.

    An operator table (ADR-012 amendment 8): no RLS, no privilege for atesta_app, and no foreign
    key to organizations, so it outlives erasure. Billing values are never stored, only field
    names; the staff id and role are NULL only for the erasure runner's `erasure.executed`.
    """

    __tablename__ = "operator_audit_events"
    __table_args__ = (
        CheckConstraint("(staff_id IS NULL) = (staff_role IS NULL)", name="staff_together"),
        CheckConstraint(
            "staff_id IS NOT NULL OR action = 'erasure.executed'", name="staff_unless_runner"
        ),
        CheckConstraint("staff_role IN ('admin', 'billing', 'support')", name="staff_role"),
        CheckConstraint(r"action ~ '^[a-z][a-z_]*(\.[a-z][a-z_]*)+$'", name="action"),
        CheckConstraint("length(reason) BETWEEN 1 AND 500", name="reason"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operator_staff.id", ondelete="RESTRICT"), index=True
    )
    staff_role: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    target_id: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Scalar]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )


def _checked(action: str, metadata: Mapping[str, Scalar] | None) -> dict[str, Scalar]:
    if not _ACTION.fullmatch(action):
        raise ValueError(f"audit action must be a dotted code, got {action!r}")
    details = dict(metadata or {})
    for key, value in details.items():
        if not isinstance(key, str) or not (value is None or isinstance(value, str | int | bool)):
            raise TypeError(f"audit metadata must map str to scalars, bad key {key!r}")
    return details


def record(
    session: Session,
    *,
    organization_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: str,
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
    metadata: Mapping[str, Scalar] | None = None,
) -> uuid.UUID:
    """Record one event and return its id. Scalar metadata only, so no blob can slip in."""
    details = _checked(action, metadata)
    event = AuditEvent(
        id=uuid.uuid4(),
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        request_id=request_id,
    )
    session.add(event)
    session.flush()
    return event.id


# --- the operator service (operator-portal spec, "Audit events"), on an atesta_operator session --

# The columns atesta_operator may insert (ADR-012 amendment 8): never actor_user_id or occurred_at.
_BY_ATESTA = table(
    "audit_events",
    *map(column, ("id", "organization_id", "action", "target_type", "target_id", "request_id")),
    column("metadata", JSONB),
)


def record_by_atesta(
    session: Session,
    *,
    organization_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: str,
    request_id: str,
    metadata: Mapping[str, Scalar] | None = None,
) -> uuid.UUID:
    """A customer-visible event the Atesta team caused: Activity shows "Equipo de Atesta".

    No actor column is named at all, so the insert stays inside the role's column grant; the
    database's `operator_audit_write` policy also holds the `operator.` prefix and the NULL actor.
    """
    if not action.startswith("operator."):
        raise ValueError(f"an Atesta event's action starts with operator., got {action!r}")
    event_id = uuid.uuid4()
    session.execute(
        insert(_BY_ATESTA).values(
            id=event_id,
            organization_id=organization_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            request_id=request_id,
            metadata=_checked(action, metadata),
        )
    )
    return event_id


def record_operator(
    session: Session,
    *,
    staff_id: uuid.UUID,
    staff_role: str,
    action: str,
    request_id: str,
    organization_id: uuid.UUID | None = None,
    target_id: str | None = None,
    reason: str | None = None,
    metadata: Mapping[str, Scalar] | None = None,
) -> uuid.UUID:
    """One row of the operator trail, in the caller's transaction. A write carries its reason; a
    read carries none. Billing values never come here, only field names."""
    row = OperatorAuditEvent(
        id=uuid.uuid4(),
        staff_id=staff_id,
        staff_role=staff_role,
        action=action,
        organization_id=organization_id,
        target_id=target_id,
        reason=reason,
        request_id=request_id,
        details=_checked(action, metadata),
    )
    session.add(row)
    session.flush()
    return row.id
