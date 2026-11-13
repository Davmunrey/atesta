"""Setting helpers and the tenant root.

Revision ID: 0001
Revises:
"""

import rls_v1
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _ts(name: str) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    for statement in rls_v1.SETTING_FUNCTIONS:
        op.execute(statement)

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
    )
    for statement in rls_v1.tenant_root_rls("organizations"):
        op.execute(statement)
    op.execute(rls_v1.grant("organizations", "SELECT"))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
