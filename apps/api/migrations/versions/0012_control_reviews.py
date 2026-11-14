"""Append-only human reviews of manual controls (manual-control-review spec, FR-07, ADR-005).

Revision ID: 0012
Revises: 0011
"""

import rls_v1
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "control_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("control_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("status IN ('pass', 'fail')", name=op.f("ck_control_reviews_status")),
        sa.CheckConstraint(
            "char_length(rationale) BETWEEN 1 AND 2000",
            name=op.f("ck_control_reviews_rationale_length"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_control_reviews_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_control_reviews")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_control_reviews_organization_id_id")
        ),
    )
    op.create_index(
        op.f("ix_control_reviews_organization_id"),
        "control_reviews",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_reviews_latest",
        "control_reviews",
        ["organization_id", "control_key", sa.text("reviewed_at DESC")],
        unique=False,
    )
    for statement in rls_v1.tenant_rls("control_reviews"):
        op.execute(statement)
    op.execute(rls_v1.grant("control_reviews", "SELECT", "INSERT"))  # append-only


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
