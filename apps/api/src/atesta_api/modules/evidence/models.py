"""Evidence tables (control-model spec, NFR-05, ADR-005). Append-only for atesta_app."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from atesta_api.platform.db import Base, TenantMixin

# A stored file always has hash, type and size; scan evidence names its scan; uploads and
# attestations name their human author. The key lives under the tenant's S3 prefix (ADR-004).
EVIDENCE_CHECKS = {
    "kind": "kind IN ('scan_output', 'document', 'attestation')",
    "source_type": "source_type IN ('scan', 'upload', 'user', 'api')",
    "file_described": "num_nulls(storage_key, sha256, media_type, size_bytes) IN (0, 4)",
    "file_required": "kind = 'attestation' OR storage_key IS NOT NULL",
    "sha256_format": "sha256 ~ '^[0-9a-f]{64}$'",
    "size_positive": "size_bytes >= 0",
    "scan_named": "source_type <> 'scan' OR source_id IS NOT NULL",
    "api_named": "source_type <> 'api' OR source_id IS NOT NULL",
    "author_named": "source_type = 'scan' OR created_by IS NOT NULL",
    "storage_key_in_tenant_prefix": (
        "storage_key IS NULL OR (left(storage_key, 37) = organization_id::text || '/'"
        " AND storage_key ~ '^[0-9a-f-]{36}(/[A-Za-z0-9_.-]+)+$'"
        " AND storage_key !~ '(^|/)\\.{1,2}(/|$)')"
    ),
}


class Evidence(TenantMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        *(CheckConstraint(sql, name=name) for name, sql in EVIDENCE_CHECKS.items()),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(CHAR(64))
    media_type: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    source_type: Mapped[str] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None]
    created_by: Mapped[uuid.UUID | None]  # users.id; no cross-module FK (ADR-008)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceControl(TenantMixin, Base):
    """One piece of evidence serves every framework mapped to the control (MF-02)."""

    __tablename__ = "evidence_controls"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "evidence_id", "control_key"),
        ForeignKeyConstraint(
            ["organization_id", "evidence_id"],
            ["evidence.organization_id", "evidence.id"],
            ondelete="RESTRICT",
        ),
    )

    evidence_id: Mapped[uuid.UUID]
    control_key: Mapped[str] = mapped_column(Text)  # validated through compliance.api


SCAN_STATUSES = (
    "no_threats_found",
    "threats_found",
    "unsupported",
    "access_denied",
    "failed",
    "not_scanned",
)


class EvidenceFileScan(TenantMixin, Base):
    """The malware scan result of one uploaded file (evidence-malware-scanning spec). Append-only:
    the first result is final (D4); no row means the file is still pending."""

    __tablename__ = "evidence_file_scans"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "evidence_id"),
        ForeignKeyConstraint(
            ["organization_id", "evidence_id"],
            ["evidence.organization_id", "evidence.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in SCAN_STATUSES) + ")", name="status"
        ),
        CheckConstraint(
            "object_version IS NULL OR length(object_version) BETWEEN 1 AND 1024",
            name="object_version_length",
        ),
    )

    evidence_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(Text)
    object_version: Mapped[str | None] = mapped_column(Text)  # the S3 version GuardDuty read
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EvidenceStatement(TenantMixin, Base):
    __tablename__ = "evidence_statements"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "evidence_id"),
        UniqueConstraint("organization_id", "submission_id"),
        ForeignKeyConstraint(
            ["organization_id", "evidence_id"],
            ["evidence.organization_id", "evidence.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(btrim(statement)) BETWEEN 1 AND 10000", name="statement_length"),
        CheckConstraint(
            "reference_url IS NULL OR length(reference_url) <= 2048", name="url_length"
        ),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="payload_hash"),
    )

    evidence_id: Mapped[uuid.UUID]
    submission_id: Mapped[uuid.UUID]
    payload_hash: Mapped[str] = mapped_column(CHAR(64))
    statement: Mapped[str] = mapped_column(Text)
    reference_url: Mapped[str | None] = mapped_column(Text)


class ApiIngestion(TenantMixin, Base):
    """Evidence written through an API token (evidence-ingestion-api spec). Append-only; the
    external id makes a tool's retries idempotent per token. token_id has no FK to the identity
    module's table (ADR-008); it comes from an accepted token."""

    __tablename__ = "api_ingestions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "token_id", "external_id"),
        ForeignKeyConstraint(
            ["organization_id", "evidence_id"],
            ["evidence.organization_id", "evidence.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(btrim(source)) BETWEEN 1 AND 50", name="source_length"),
        CheckConstraint(
            "external_id IS NULL OR length(external_id) BETWEEN 1 AND 200",
            name="external_id_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_id: Mapped[uuid.UUID]
    evidence_id: Mapped[uuid.UUID]
    source: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
