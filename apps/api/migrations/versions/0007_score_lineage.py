"""Score corrections: one linear chain within one framework, scan and scope.

A correction may supersede only a snapshot of the same framework, scan and scope (composite FK on
a generated scope_key, because MATCH SIMPLE skips an FK whose scope_id is NULL), and each snapshot
has at most one correction, so a retried correction job is idempotent (control-model spec).

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None
LINEAGE = ["organization_id", "framework_key", "scan_id", "scope_key"]


def upgrade() -> None:
    op.add_column(
        "score_snapshots",
        sa.Column(
            "scope_key",
            sa.Uuid(),
            sa.Computed(
                "COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid)", persisted=True
            ),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        op.f("uq_score_snapshots_lineage"), "score_snapshots", [*LINEAGE, "id"]
    )
    op.drop_constraint(  # name as created by 0005 (truncated with a hash suffix)
        op.f("fk_score_snapshots_organization_id_supersedes_id_score__da80"),
        "score_snapshots",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_score_snapshots_lineage"),
        "score_snapshots",
        "score_snapshots",
        [*LINEAGE, "supersedes_id"],
        [*LINEAGE, "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_score_snapshots_one_correction",
        "score_snapshots",
        ["organization_id", "supersedes_id"],
        unique=True,
        postgresql_where=sa.text("supersedes_id IS NOT NULL"),
    )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
