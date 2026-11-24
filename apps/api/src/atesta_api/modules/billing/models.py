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


# Billing details (operator-portal spec): text columns and their longest accepted length.
# NULL means not recorded; blank text is refused. Format rules live in the operator API.
BILLING_FIELDS = {
    "legal_name": 200,
    "tax_id": 50,
    "address_line1": 200,
    "address_line2": 200,
    "postal_code": 20,
    "city": 100,
    "region": 100,
    "contact_email": 254,
}


class BillingProfile(Base):
    """One per organization. atesta_app only reads it; the operator writes it (ADR-012 am. 8)."""

    __tablename__ = "billing_profiles"
    __table_args__ = (
        *(
            CheckConstraint(f"length(btrim({name})) BETWEEN 1 AND {size}", name=name)
            for name, size in BILLING_FIELDS.items()
        ),
        CheckConstraint("country ~ '^[A-Z]{2}$'", name="country"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    legal_name: Mapped[str | None] = mapped_column(Text)
    tax_id: Mapped[str | None] = mapped_column(Text)
    address_line1: Mapped[str | None] = mapped_column(Text)
    address_line2: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)  # ISO 3166-1 alpha-2
    contact_email: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
