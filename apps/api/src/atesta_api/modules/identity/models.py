"""Identity tables (identity-auth spec). Private to the identity module."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from atesta_api.platform.db import Base, TenantMixin


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    AUDITOR = "auditor"  # read-only and time-boxed (rbac spec)


_ROLES = "role IN ('owner', 'admin', 'member', 'auditor')"


def _now(onupdate: bool = False) -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now() if onupdate else None,
    )


class User(Base):
    """Global identity (ADR-012). Identity is cognito_sub; email is a cache of Cognito."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("locale IN ('es', 'en')", name="locale"),
        Index("ix_users_lower_email", text("lower(email)")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cognito_sub: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str] = mapped_column(Text)
    email_verified: Mapped[bool] = mapped_column(Boolean)
    display_name: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text, server_default="es")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now(onupdate=True)


class Membership(TenantMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "user_id"),
        CheckConstraint(_ROLES, name="role"),
        CheckConstraint(
            "(role = 'auditor') = (access_expires_at IS NOT NULL)", name="auditor_end_date"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invitation(TenantMixin, Base):
    """token_sha256 is indexed, not unique: tenant unique keys lead with organization_id."""

    __tablename__ = "invitations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        CheckConstraint(_ROLES, name="role"),
        CheckConstraint(
            "(role = 'auditor') = (access_expires_on IS NOT NULL)", name="auditor_end_date"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    token_sha256: Mapped[str] = mapped_column(Text, index=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    access_expires_on: Mapped[date | None] = mapped_column(Date)
