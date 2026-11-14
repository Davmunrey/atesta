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
    "source_type": "source_type IN ('scan', 'upload', 'user')",
    "file_described": "num_nulls(storage_key, sha256, media_type, size_bytes) IN (0, 4)",
    "file_required": "kind = 'attestation' OR storage_key IS NOT NULL",
    "sha256_format": "sha256 ~ '^[0-9a-f]{64}$'",
    "size_positive": "size_bytes >= 0",
    "scan_named": "source_type <> 'scan' OR source_id IS NOT NULL",
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
