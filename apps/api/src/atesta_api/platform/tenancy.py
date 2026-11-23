"""Tenant root and the only writer of app.* settings.

Only the identity module may import this module (ADR-012, import-linter).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, func, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from atesta_api.platform.context import SETTING_NAMES, TenantContext
from atesta_api.platform.db import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Organization-closure spec: erasure becomes possible 30 days after the request.
    closure_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closure_requested_by: Mapped[uuid.UUID | None]  # users.id; no FK, the user may be erased


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
