"""Preferences and the delivery log (notifications spec, PR 1; ADR-012 amendment 7)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from atesta_api.platform.db import Base, TenantMixin

OPTIONAL_SQL = "kind IN ('scan_problem', 'due_digest', 'weekly_summary')"
KIND_SQL = (
    "kind IN ('connection_alert', 'evidence_malware', 'incident_clock', 'scan_problem',"
    " 'due_digest', 'weekly_summary')"
)


class NotificationPreference(TenantMixin, Base):
    """A person's choice for one optional type in one organization; no row means enabled."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "user_id", "kind"),
        CheckConstraint(OPTIONAL_SQL, name="kind_optional"),
    )

    user_id: Mapped[uuid.UUID]  # users.id; no FK (ADR-008)
    kind: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationDelivery(TenantMixin, Base):
    """One email to one person; the dedupe key makes a retried job send it once.

    No subject, body or address is stored (data minimization, rule 2).
    """

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "user_id", "kind", "dedupe_key"),
        CheckConstraint(KIND_SQL, name="kind"),
        CheckConstraint("status IN ('queued', 'sent', 'failed', 'suppressed')", name="status"),
        CheckConstraint("char_length(dedupe_key) BETWEEN 1 AND 200", name="dedupe_key_length"),
        CheckConstraint("(status = 'sent') = (sent_at IS NOT NULL)", name="sent_at_when_sent"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID]  # users.id; no FK (ADR-008)
    kind: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
