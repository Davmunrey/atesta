"""Tenant root and the only writer of app.* settings.

Only the identity module may import this module (ADR-012, import-linter).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Computed, DateTime, Text, func, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from atesta_api.platform.context import SETTING_NAMES, TenantContext
from atesta_api.platform.db import Base

SUSPENSION_REASONS = (
    "'non_payment', 'contract_ended', 'customer_request', 'security_review', 'other'"
)
CLOSURE_ORIGIN = (
    "CASE WHEN closure_requested_at IS NULL THEN NULL"
    " WHEN closure_requested_by IS NULL THEN 'operator' ELSE 'owner' END"
)


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("locale IN ('es', 'en')", name="locale"),
        # Operator portal (ADR-012 amendment 8, #445): suspension and closure origin.
        CheckConstraint(f"suspension_reason IN ({SUSPENSION_REASONS})", name="suspension_reason"),
        CheckConstraint(
            "(suspended_at IS NULL) = (suspension_reason IS NULL)", name="suspension_together"
        ),
        CheckConstraint(
            "closure_requested_by IS NULL OR closure_requested_at IS NOT NULL",
            name="closure_by_needs_at",
        ),
        CheckConstraint("trial_ends_at > created_at", name="trial_after_creation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text, server_default="es")  # notifications spec PR 2
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Organization-closure spec: erasure becomes possible 30 days after the request.
    closure_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closure_requested_by: Mapped[uuid.UUID | None]  # users.id; no FK, the user may be erased
    # Operator-portal spec: an owner's closure records the person, an operator closure does not.
    closure_origin: Mapped[str | None] = mapped_column(
        Text, Computed(CLOSURE_ORIGIN, persisted=True)
    )
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[str | None] = mapped_column(Text)
    # Owner answer 1 (2026-11-24): a 14-day full trial, then read-only until a plan is set.
    trial_ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now() + interval '14 days'")
    )


def set_tenant_context(session: Session, ctx: TenantContext) -> None:
    """Set the non-None fields as transaction-local settings (is_local = true).

    The values die with the transaction, so a pooled connection never carries a tenant.
    """
    for attr, name in SETTING_NAMES:
        value = getattr(ctx, attr)
        if value is not None:
            session.execute(
                text("SELECT set_config(:name, :value, true)"),
                {"name": name, "value": str(value)},
            )
