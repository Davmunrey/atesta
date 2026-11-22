"""External auditor role with a mandatory access end date (rbac spec).

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_OLD = "role IN ('owner', 'admin', 'member')"
_NEW = "role IN ('owner', 'admin', 'member', 'auditor')"


def upgrade() -> None:
    op.add_column(
        "memberships", sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("invitations", sa.Column("access_expires_on", sa.Date(), nullable=True))
    for table, column in (
        ("memberships", "access_expires_at"),
        ("invitations", "access_expires_on"),
    ):
        op.drop_constraint(op.f(f"ck_{table}_role"), table, type_="check")
        op.create_check_constraint(op.f(f"ck_{table}_role"), table, _NEW)
        op.create_check_constraint(
            op.f(f"ck_{table}_auditor_end_date"),
            table,
            f"(role = 'auditor') = ({column} IS NOT NULL)",
        )


def downgrade() -> None:
    for table, column in (
        ("memberships", "access_expires_at"),
        ("invitations", "access_expires_on"),
    ):
        op.drop_constraint(op.f(f"ck_{table}_auditor_end_date"), table, type_="check")
        op.drop_constraint(op.f(f"ck_{table}_role"), table, type_="check")
        op.create_check_constraint(op.f(f"ck_{table}_role"), table, _OLD)
        op.drop_column(table, column)
