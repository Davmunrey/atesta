"""Subscriptions table (billing-entitlements spec; ADR-012 tenant table, read-only for the app)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from atesta_api.platform.db import Base


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (CheckConstraint("plan IN ('starter', 'pro', 'business')", name="plan"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    plan: Mapped[str] = mapped_column(Text)
    addons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    note: Mapped[str] = mapped_column(Text, server_default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
