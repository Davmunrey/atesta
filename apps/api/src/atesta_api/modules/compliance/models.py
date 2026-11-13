"""Global, read-only catalog tables (control-model spec, ADR-011, ADR-012).

The YAML in catalog/ is the source of truth; these tables are its projection, written only by
the catalog sync job as atesta_owner. No column, value or code path names a framework (rule 9).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from atesta_api.platform.db import Base

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
