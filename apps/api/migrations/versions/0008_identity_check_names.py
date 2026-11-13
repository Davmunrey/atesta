"""Rename the identity CHECKs that 0003 created with a doubled prefix.

0003 passed plain names such as name="ck_users_locale"; env.py's metadata applies the
"ck_%(table_name)s_%(constraint_name)s" convention on top, so the database got
ck_users_ck_users_locale. Raw SQL here, so the result does not depend on the convention.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users RENAME CONSTRAINT ck_users_ck_users_locale TO ck_users_locale")
    op.execute(
        "ALTER TABLE memberships RENAME CONSTRAINT ck_memberships_ck_memberships_role"
        " TO ck_memberships_role"
    )
    op.execute(
        "ALTER TABLE invitations RENAME CONSTRAINT ck_invitations_ck_invitations_role"
        " TO ck_invitations_role"
    )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
