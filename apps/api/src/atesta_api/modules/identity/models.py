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
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
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


# API key scopes (api-keys-v2 spec). Reads never imply writes; there is no default for new keys.
READ_SCOPES = ("compliance:read", "incidents:read")
WRITE_SCOPES = ("evidence:write", "assessment:propose", "routines:write")
SCOPES = READ_SCOPES + WRITE_SCOPES
_SCOPE_LIST = ", ".join(f"'{s}'" for s in SCOPES)


class ApiToken(TenantMixin, Base):
    """An API key for a customer's own tools and agents (api-keys-v2 spec). Only the SHA-256
    is kept, indexed and not unique: tenant unique keys lead with organization_id."""

    __tablename__ = "api_tokens"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 100", name="name_length"),
        CheckConstraint("token_sha256 ~ '^[0-9a-f]{64}$'", name="token_format"),
        CheckConstraint("length(prefix) = 12", name="prefix_length"),
        CheckConstraint(
            f"cardinality(scopes) >= 1 AND scopes <@ ARRAY[{_SCOPE_LIST}]::text[]",
            name="scopes_known",
        ),
        CheckConstraint("rate_limit_per_minute BETWEEN 1 AND 600", name="rate_limit_range"),
        CheckConstraint("expires_at > created_at", name="expires_after_creation"),
        CheckConstraint("(revoked_at IS NULL) = (revoked_by IS NULL)", name="revoked_together"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    prefix: Mapped[str] = mapped_column(Text)
    token_sha256: Mapped[str] = mapped_column(Text, index=True)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{evidence:write}'::text[]")
    )
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, server_default="60")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )


class ApiTokenUsage(TenantMixin, Base):
    """One accepted request of a key (api-keys-v2 spec): the route template and the scope, never
    a body, query or customer content (rule 2). Never updated; deleted once 90 days old (ADR-012
    amendment 9). The rate limit counts these rows."""

    __tablename__ = "api_token_usage"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "token_id"],
            ["api_tokens.organization_id", "api_tokens.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')", name="method"),
        CheckConstraint(
            "route ~ '^/api/v1/[a-z0-9/{}_.-]+$' AND length(route) <= 200", name="route_template"
        ),
        Index(
            "ix_api_token_usage_organization_id_token_id_at", "organization_id", "token_id", "at"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_id: Mapped[uuid.UUID]
    at: Mapped[datetime] = _now()
    method: Mapped[str] = mapped_column(Text)
    route: Mapped[str] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
