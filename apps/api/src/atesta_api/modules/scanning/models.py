"""Scanning tables (scanner-connectors spec, ADR-005, ADR-012).

Scans change status but are never deleted; check results and findings are append-only for
atesta_app. connection_id has no FK: connections belong to another module (ADR-008).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from atesta_api.modules.scanning.error_codes import SCAN_ERROR_CODES
from atesta_api.platform.db import Base, TenantMixin

ACTIVE_SCAN = "status IN ('queued', 'running')"
SCAN_CHECKS = {
    "provider": "provider IN ('m365', 'google_workspace')",
    "trigger": "trigger IN ('schedule', 'user', 'activation')",
    "status": (
        "status IN ('queued', 'running', 'collected', 'succeeded', 'partial', 'failed', 'blocked')"
    ),
    "engine": "engine = 'prowler'",
    "attempts_non_negative": "attempts >= 0",
    "coverage_bounded": "evaluated_checks BETWEEN 0 AND expected_checks",
    "manifest_sha256_format": "manifest_sha256 ~ '^[0-9a-f]{64}$'",
    # The worker writes only under its own org, scan and attempt (ADR-004).
    "output_prefix_in_tenant": (
        "output_prefix IS NULL OR output_prefix ~ ('^' || organization_id::text || '/scans/'"
        " || id::text || '/attempt-[1-9][0-9]*/out/$')"
    ),
}
RESULT_CHECKS = {
    "engine": "engine = 'prowler'",
    "status": "status IN ('pass', 'fail', 'manual', 'not_evaluated')",
    "reason": "reason IN ('no_findings', 'excluded', 'not_granted')",
    # A check that was not evaluated says why; one that was never pretends otherwise (ADR-005).
    "reason_iff_not_evaluated": "(status = 'not_evaluated') = (reason IS NOT NULL)",
    "counts_non_negative": "pass_count >= 0 AND fail_count >= 0 AND manual_count >= 0",
}
FINDING_CHECKS = {
    "engine": "engine = 'prowler'",
    "status": "status IN ('pass', 'fail', 'manual')",
}


class Scan(TenantMixin, Base):
    __tablename__ = "scans"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        Index(
            "uq_scans_one_active_per_connection",
            "organization_id",
            "connection_id",
            unique=True,
            postgresql_where=text(ACTIVE_SCAN),
        ),
        *(CheckConstraint(sql, name=name) for name, sql in SCAN_CHECKS.items()),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID]
    provider: Mapped[str] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    engine: Mapped[str] = mapped_column(Text)
    engine_version: Mapped[str] = mapped_column(Text)
    image_digest: Mapped[str | None] = mapped_column(Text)
    output_prefix: Mapped[str | None] = mapped_column(Text)
    manifest_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    error_code: Mapped[str | None] = mapped_column(Text)
    expected_checks: Mapped[int] = mapped_column(Integer, server_default="0")
    evaluated_checks: Mapped[int] = mapped_column(Integer, server_default="0")
    requested_by: Mapped[uuid.UUID | None]  # users.id; no cross-module FK (ADR-008)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @validates("error_code")
    def _known_error_code(self, _key: str, value: str | None) -> str | None:
        """GET /scans returns error_code: each one needs ES and EN text (#270)."""
        if value is not None and value not in SCAN_ERROR_CODES:
            raise ValueError(f"unknown scan error code: {value}")
        return value


class ScanCheckResult(TenantMixin, Base):
    """Coverage: one row per expected check of a scan, evaluated or not."""

    __tablename__ = "scan_check_results"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "scan_id", "engine", "check_id"),
        ForeignKeyConstraint(
            ["organization_id", "scan_id"],
            ["scans.organization_id", "scans.id"],
            ondelete="RESTRICT",
        ),
        *(CheckConstraint(sql, name=name) for name, sql in RESULT_CHECKS.items()),
    )

    scan_id: Mapped[uuid.UUID]
    engine: Mapped[str] = mapped_column(Text)
    check_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    pass_count: Mapped[int] = mapped_column(Integer, server_default="0")
    fail_count: Mapped[int] = mapped_column(Integer, server_default="0")
    manual_count: Mapped[int] = mapped_column(Integer, server_default="0")


class Finding(TenantMixin, Base):
    """One engine finding. message and resource_name may hold personal data: tenant data."""

    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "scan_id"],
            ["scans.organization_id", "scans.id"],
            ondelete="RESTRICT",
        ),
        Index(None, "organization_id", "scan_id", "check_id"),
        *(CheckConstraint(sql, name=name) for name, sql in FINDING_CHECKS.items()),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID]
    engine: Mapped[str] = mapped_column(Text)
    check_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    muted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    severity: Mapped[str] = mapped_column(Text)
    service: Mapped[str] = mapped_column(Text)
    resource_type: Mapped[str] = mapped_column(Text)
    resource_uid: Mapped[str] = mapped_column(Text)
    resource_name: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
