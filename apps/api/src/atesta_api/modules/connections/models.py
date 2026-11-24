"""Connections table (scanner-connectors spec, Data model; ADR-012).

A connection never holds a secret: only references to secrets that the scanner container
resolves. The database rejects a key, a secret outside eu-south-2 and another org's Google
secret. external_tenant_id is the tenant pin: set by the first successful verification, then
immutable (trigger in the migration), like the provider.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from atesta_api.platform.db import Base, TenantMixin

STATUSES = (
    "pending_provisioning",
    "pending_setup",
    "verifying",
    "incomplete",
    "active",
    "over_privileged",
    "revoked",
    "disconnected",
)
_GUID = "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'"
_REF = (
    "'^(aws-sm:arn:aws:secretsmanager:eu-south-2:[0-9]{12}:secret:[A-Za-z0-9/_+=.@-]+"
    "|local:[a-z0-9][a-z0-9-]{0,62})$'"
)


def _google_ref(column: str, name: str) -> str:
    """A Google ref names this org's own secret (Secrets Manager appends six characters)."""
    return (
        f"provider <> 'google_workspace' OR {column} IS NULL OR {column} ~ ("
        "'^(aws-sm:arn:aws:secretsmanager:eu-south-2:[0-9]{12}:secret:atesta/[a-z0-9-]+/"
        f"{name}/' || organization_id::text || '-[A-Za-z0-9]{{6}}|local:{name}-'"
        " || organization_id::text || ')$')"
    )


# OAuth client ids and IAM uniqueIds of the org's scan and verifier service accounts (issue 398).
GOOGLE_IDS = (
    "google_client_id",
    "google_verifier_client_id",
    "google_unique_id",
    "google_verifier_unique_id",
)
CONNECTION_CHECKS = {
    "provider": "provider IN ('m365', 'google_workspace')",
    "status": "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")",
    "display_name_filled": "btrim(display_name) <> '' AND length(display_name) <= 200",
    "granted_object": "jsonb_typeof(granted) = 'object'",
    # Postgres caps regex repetition at 255, so the spec's {1,512} secret name is a length bound:
    # 61 characters of aws-sm ARN prefix plus at most 512 of name.
    "credential_ref_format": f"credential_ref ~ {_REF} AND char_length(credential_ref) <= 573",
    "verifier_credential_ref_format": (
        f"verifier_credential_ref ~ {_REF} AND char_length(verifier_credential_ref) <= 573"
    ),
    "google_ref_in_tenant": _google_ref("credential_ref", "google"),
    "google_verifier_ref_in_tenant": _google_ref("verifier_credential_ref", "google-verifier"),
    # The M365 credential is the platform's, never per connection.
    "m365_no_refs": (
        "provider <> 'm365' OR (credential_ref IS NULL AND verifier_credential_ref IS NULL)"
    ),
    "m365_tenant_guid": f"provider <> 'm365' OR external_tenant_id ~ {_GUID}",
    "ms_tenant_guid": f"ms_tenant_id ~ {_GUID}",
    "active_has_tenant": "status <> 'active' OR external_tenant_id IS NOT NULL",
    "google_ids_numeric": " AND ".join(
        f"({c} IS NULL OR {c} ~ '^[0-9]{{6,30}}$')" for c in GOOGLE_IDS
    ),
    "m365_no_google": (
        "provider <> 'm365' OR num_nonnulls("
        + ", ".join(GOOGLE_IDS)
        + ", google_subject_email) = 0"
    ),
    "active_google_complete": (
        "provider <> 'google_workspace' OR status <> 'active' OR num_nulls(credential_ref,"
        " verifier_credential_ref, " + ", ".join(GOOGLE_IDS) + ", google_subject_email) = 0"
    ),
}


class Connection(TenantMixin, Base):
    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        Index(
            "uq_connections_one_live_per_tenant",
            "organization_id",
            "provider",
            "external_tenant_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        *(CheckConstraint(sql, name=name) for name, sql in CONNECTION_CHECKS.items()),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    external_tenant_id: Mapped[str | None] = mapped_column(Text)
    ms_tenant_id: Mapped[str | None] = mapped_column(Text)
    consented_by_oid: Mapped[str | None] = mapped_column(Text)
    allowlist_version: Mapped[str | None] = mapped_column(Text)
    primary_domain: Mapped[str | None] = mapped_column(Text)
    google_subject_email: Mapped[str | None] = mapped_column(Text)
    google_client_id: Mapped[str | None] = mapped_column(Text)
    credential_ref: Mapped[str | None] = mapped_column(Text)
    google_verifier_client_id: Mapped[str | None] = mapped_column(Text)
    verifier_credential_ref: Mapped[str | None] = mapped_column(Text)
    google_unique_id: Mapped[str | None] = mapped_column(Text)
    google_verifier_unique_id: Mapped[str | None] = mapped_column(Text)
    verifying_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    granted: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID]  # users.id; no cross-module FK (ADR-008)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
