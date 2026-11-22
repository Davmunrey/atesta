"""Requirement owners and due dates (insights spec).

Revision ID: 0015
Revises: 0014
"""

import rls_v1
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = "requirement_assignments"
    op.create_table(
        table,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("framework_key", sa.Text(), nullable=False),
        sa.Column("requirement_code", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("assigned_by", sa.Uuid(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f(f"fk_{table}_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("organization_id", "id", name=op.f(f"uq_{table}_organization_id_id")),
    )
    op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
    op.create_index(
        f"ix_{table}_latest",
        table,
        ["organization_id", "framework_key", "requirement_code", "assigned_at"],
    )
    for statement in rls_v1.tenant_rls(table):
        op.execute(statement)
    op.execute(rls_v1.grant(table, "SELECT", "INSERT"))  # append-only


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
