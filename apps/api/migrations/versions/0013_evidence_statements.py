"""Immutable declared evidence. Revision 0013, follows manual reviews 0012."""

import rls_v1
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_statements",
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("payload_hash", sa.CHAR(64), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("reference_url", sa.Text()),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("organization_id", "evidence_id"),
        sa.UniqueConstraint("organization_id", "submission_id"),
        sa.ForeignKeyConstraint(
            ["organization_id", "evidence_id"],
            ["evidence.organization_id", "evidence.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("length(btrim(statement)) BETWEEN 1 AND 10000", name="statement_length"),
        sa.CheckConstraint(
            "reference_url IS NULL OR length(reference_url) <= 2048", name="url_length"
        ),
        sa.CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="payload_hash"),
    )
    op.create_index(
        op.f("ix_evidence_statements_organization_id"), "evidence_statements", ["organization_id"]
    )
    for statement in rls_v1.tenant_rls("evidence_statements"):
        op.execute(statement)
    op.execute(rls_v1.grant("evidence_statements", "SELECT", "INSERT"))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
