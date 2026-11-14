"""Global, read-only catalog tables (control-model spec, ADR-011, ADR-012).

The YAML in catalog/ is the source of truth; these tables are its projection, written only by
the catalog sync job as atesta_owner. No column, value or code path names a framework (rule 9).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from atesta_api.platform.db import Base, TenantMixin

_EMPTY_ARRAY = text("'{}'::text[]")
_EMPTY_JSON = text("'{}'::jsonb")


def _filled(column: str) -> CheckConstraint:
    return CheckConstraint(f"btrim({column}) <> ''", name=f"{column}_filled")


class _Retirable:
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Framework(_Retirable, Base):
    __tablename__ = "frameworks"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'reviewed', 'released')", name="status"),
        _filled("source"),
    )

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    jurisdiction: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    license_notes: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY_JSON)
    catalog_version: Mapped[str | None] = mapped_column(Text)


class Requirement(_Retirable, Base):
    __tablename__ = "requirements"
    __table_args__ = (PrimaryKeyConstraint("framework_key", "code"), _filled("source"))

    framework_key: Mapped[str] = mapped_column(ForeignKey("frameworks.key", ondelete="RESTRICT"))
    code: Mapped[str] = mapped_column(Text)
    title_es: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text)
    applies_to: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=_EMPTY_ARRAY)
    source: Mapped[str] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY_JSON)


class Control(_Retirable, Base):
    __tablename__ = "controls"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    title_es: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str] = mapped_column(Text)
    description_es: Mapped[str] = mapped_column(Text)
    description_en: Mapped[str] = mapped_column(Text)
    manual: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    remediation_refs: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=_EMPTY_ARRAY)


class Check(_Retirable, Base):
    __tablename__ = "checks"
    __table_args__ = (
        PrimaryKeyConstraint("engine", "check_id"),
        CheckConstraint("engine IN ('prowler', 'atesta')", name="engine"),
    )

    engine: Mapped[str] = mapped_column(Text)
    check_id: Mapped[str] = mapped_column(Text)
    engine_version: Mapped[str] = mapped_column(Text)


class ControlCheck(_Retirable, Base):
    __tablename__ = "control_checks"
    __table_args__ = (
        PrimaryKeyConstraint("control_key", "engine", "check_id"),
        ForeignKeyConstraint(
            ["engine", "check_id"], ["checks.engine", "checks.check_id"], ondelete="RESTRICT"
        ),
    )

    control_key: Mapped[str] = mapped_column(ForeignKey("controls.key", ondelete="RESTRICT"))
    engine: Mapped[str] = mapped_column(Text)
    check_id: Mapped[str] = mapped_column(Text)


class Mapping(_Retirable, Base):
    """MF-06: every mapping carries rationale and source; reviewed_by is NULL until signed."""

    __tablename__ = "mappings"
    __table_args__ = (
        PrimaryKeyConstraint("framework_key", "requirement_code", "control_key"),
        ForeignKeyConstraint(
            ["framework_key", "requirement_code"],
            ["requirements.framework_key", "requirements.code"],
            ondelete="RESTRICT",
        ),
        _filled("rationale"),
        _filled("source"),
        CheckConstraint("reviewed_by IS NULL OR btrim(reviewed_by) <> ''", name="reviewed_by"),
    )

    framework_key: Mapped[str] = mapped_column(Text)
    requirement_code: Mapped[str] = mapped_column(Text)
    control_key: Mapped[str] = mapped_column(ForeignKey("controls.key", ondelete="RESTRICT"))
    rationale: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(Text)


_LINEAGE = ("organization_id", "framework_key", "scan_id", "scope_key")
_SCOPE_KEY = "COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid)"


class ScoreSnapshot(TenantMixin, Base):
    """Append-only score of one framework for one scan and scope (FR-08). Corrections supersede."""

    __tablename__ = "score_snapshots"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint(*_LINEAGE, "id", name="uq_score_snapshots_lineage"),
        ForeignKeyConstraint(  # a correction stays in its framework, scan and scope
            [*_LINEAGE, "supersedes_id"],
            [f"score_snapshots.{c}" for c in (*_LINEAGE, "id")],
            name="fk_score_snapshots_lineage",
            ondelete="RESTRICT",
        ),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="score_range"),
        CheckConstraint(
            "passed >= 0 AND failed >= 0 AND manual >= 0 AND not_applicable >= 0", name="counters"
        ),
        CheckConstraint("jsonb_typeof(requirement_results) = 'object'", name="results_object"),
        Index(
            "uq_score_snapshots_one_original",
            "organization_id",
            "framework_key",
            "scan_id",
            "scope_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=text("supersedes_id IS NULL"),
        ),
        Index(  # one correction per snapshot: a linear chain, retried corrections are no-ops
            "uq_score_snapshots_one_correction",
            "organization_id",
            "supersedes_id",
            unique=True,
            postgresql_where=text("supersedes_id IS NOT NULL"),
        ),
        Index(
            "ix_score_snapshots_trend",
            "organization_id",
            "framework_key",
            "scope_id",
            text("computed_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    framework_key: Mapped[str] = mapped_column(ForeignKey("frameworks.key", ondelete="RESTRICT"))
    framework_version: Mapped[str] = mapped_column(Text)
    catalog_version: Mapped[str] = mapped_column(Text)
    scan_id: Mapped[uuid.UUID]
    scope_id: Mapped[uuid.UUID | None]
    scope_key: Mapped[uuid.UUID] = mapped_column(Computed(_SCOPE_KEY, persisted=True))
    applicability: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY_JSON)
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    passed: Mapped[int]
    failed: Mapped[int]
    manual: Mapped[int]
    not_applicable: Mapped[int]
    requirement_results: Mapped[dict[str, str]] = mapped_column(JSONB)
    group_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=_EMPTY_JSON)
    supersedes_id: Mapped[uuid.UUID | None]
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ControlReview(TenantMixin, Base):
    """A human decision on a manual control (manual-control-review spec, ADR-005).

    Append-only: the latest row for a control is its current review. control_key has no FK to
    the global catalog and reviewed_by none to users (ADR-008); both are checked at write time.
    """

    __tablename__ = "control_reviews"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("status IN ('pass', 'fail')", name="status"),
        CheckConstraint("char_length(rationale) BETWEEN 1 AND 2000", name="rationale_length"),
        Index(
            "ix_control_reviews_latest",
            "organization_id",
            "control_key",
            text("reviewed_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    control_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    valid_until: Mapped[date] = mapped_column(Date)
    reviewed_by: Mapped[uuid.UUID]
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
