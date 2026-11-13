"""Global read-only catalog tables (control-model spec, ADR-011, ADR-012).

Revision ID: 0004
Revises: 0003
"""

import rls_v1
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None
CATALOG = ("frameworks", "requirements", "controls", "checks", "control_checks", "mappings")


def upgrade() -> None:
    op.create_table(
        "checks",
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("check_id", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("engine IN ('prowler', 'atesta')", name=op.f("ck_checks_engine")),
        sa.PrimaryKeyConstraint("engine", "check_id", name=op.f("pk_checks")),
    )
    op.create_table(
        "controls",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("title_es", sa.Text(), nullable=False),
        sa.Column("title_en", sa.Text(), nullable=False),
        sa.Column("description_es", sa.Text(), nullable=False),
        sa.Column("description_en", sa.Text(), nullable=False),
        sa.Column("manual", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "remediation_refs",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_controls")),
    )
    op.create_table(
        "frameworks",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("jurisdiction", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("license_notes", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("catalog_version", sa.Text(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("btrim(source) <> ''", name=op.f("ck_frameworks_source_filled")),
        sa.CheckConstraint(
            "status IN ('draft', 'reviewed', 'released')", name=op.f("ck_frameworks_status")
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_frameworks")),
    )
    op.create_table(
        "control_checks",
        sa.Column("control_key", sa.Text(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("check_id", sa.Text(), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["control_key"],
            ["controls.key"],
            name=op.f("fk_control_checks_control_key_controls"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["engine", "check_id"],
            ["checks.engine", "checks.check_id"],
            name=op.f("fk_control_checks_engine_check_id_checks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "control_key", "engine", "check_id", name=op.f("pk_control_checks")
        ),
    )
    op.create_table(
        "requirements",
        sa.Column("framework_key", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title_es", sa.Text(), nullable=False),
        sa.Column("title_en", sa.Text(), nullable=True),
        sa.Column(
            "applies_to",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("btrim(source) <> ''", name=op.f("ck_requirements_source_filled")),
        sa.ForeignKeyConstraint(
            ["framework_key"],
            ["frameworks.key"],
            name=op.f("fk_requirements_framework_key_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("framework_key", "code", name=op.f("pk_requirements")),
    )
    op.create_table(
        "mappings",
        sa.Column("framework_key", sa.Text(), nullable=False),
        sa.Column("requirement_code", sa.Text(), nullable=False),
        sa.Column("control_key", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("btrim(rationale) <> ''", name=op.f("ck_mappings_rationale_filled")),
        sa.CheckConstraint("btrim(source) <> ''", name=op.f("ck_mappings_source_filled")),
        sa.CheckConstraint(
            "reviewed_by IS NULL OR btrim(reviewed_by) <> ''", name=op.f("ck_mappings_reviewed_by")
        ),
        sa.ForeignKeyConstraint(
            ["control_key"],
            ["controls.key"],
            name=op.f("fk_mappings_control_key_controls"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["framework_key", "requirement_code"],
            ["requirements.framework_key", "requirements.code"],
            name=op.f("fk_mappings_framework_key_requirement_code_requirements"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "framework_key", "requirement_code", "control_key", name=op.f("pk_mappings")
        ),
    )
    for table in CATALOG:
        op.execute(rls_v1.grant(table, "SELECT"))  # written only by the sync job as owner


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
