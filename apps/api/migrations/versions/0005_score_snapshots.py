"""Append-only score snapshots (control-model spec, FR-08).

Revision ID: 0005
Revises: 0004
"""

import rls_v1
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "score_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("framework_key", sa.Text(), nullable=False),
        sa.Column("framework_version", sa.Text(), nullable=False),
        sa.Column("catalog_version", sa.Text(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column(
            "applicability",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("passed", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("manual", sa.Integer(), nullable=False),
        sa.Column("not_applicable", sa.Integer(), nullable=False),
        sa.Column("requirement_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "group_scores",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(requirement_results) = 'object'",
            name=op.f("ck_score_snapshots_results_object"),
        ),
        sa.CheckConstraint(
            "passed >= 0 AND failed >= 0 AND manual >= 0 AND not_applicable >= 0",
            name=op.f("ck_score_snapshots_counters"),
        ),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 100", name=op.f("ck_score_snapshots_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["framework_key"],
            ["frameworks.key"],
            name=op.f("fk_score_snapshots_framework_key_frameworks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supersedes_id"],
            ["score_snapshots.organization_id", "score_snapshots.id"],
            name=op.f("fk_score_snapshots_organization_id_supersedes_id_score_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_score_snapshots_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_score_snapshots")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_score_snapshots_organization_id_id")
        ),
    )
    op.create_index(
        op.f("ix_score_snapshots_organization_id"),
        "score_snapshots",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_score_snapshots_trend",
        "score_snapshots",
        ["organization_id", "framework_key", "scope_id", sa.literal_column("computed_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_score_snapshots_one_original",
        "score_snapshots",
        ["organization_id", "framework_key", "scan_id", "scope_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("supersedes_id IS NULL"),
    )
    for statement in rls_v1.tenant_rls("score_snapshots"):
        op.execute(statement)
    op.execute(rls_v1.grant("score_snapshots", "SELECT", "INSERT"))  # append-only


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
