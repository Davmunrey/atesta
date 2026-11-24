"""The organization's language for email (notifications spec PR 2, issue 386).

`es` or `en`, Spanish by default. The owner sets it in Ajustes. No new privilege: atesta_app
already updates organizations, under the tenant root policy.

Revision ID: 0028
Revises: 0027
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations", sa.Column("locale", sa.Text(), server_default="es", nullable=False)
    )
    op.create_check_constraint(
        op.f("ck_organizations_locale"), "organizations", "locale IN ('es', 'en')"
    )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
