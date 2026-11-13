"""Append-only audit events, written in the caller's transaction (FR-13)."""

import re
import uuid
from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import DateTime, Text, func, text
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
) -> None:
    """Record one event. Scalar metadata only, so no blob (token, document) can slip in."""
    if not _ACTION.fullmatch(action):
        raise ValueError(f"audit action must be a dotted code, got {action!r}")
    details = dict(metadata or {})
    for key, value in details.items():
        if not isinstance(key, str) or not (value is None or isinstance(value, str | int | bool)):
            raise TypeError(f"audit metadata must map str to scalars, bad key {key!r}")
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            request_id=request_id,
        )
    )
    session.flush()
