"""Subscriptions: each organization's plan (billing-entitlements spec).

A tenant table with the standard RLS policy (ADR-012). The app role only reads it: the operator
sets a plan with the migration role. An organization with no row has billing's default plan.

Revision ID: 0022
Revises: 0021
"""

import rls_v1
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("addons", ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "plan IN ('starter', 'pro', 'business')", name=op.f("ck_subscriptions_plan")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_subscriptions_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_subscriptions")),
    )
    for statement in rls_v1.tenant_rls("subscriptions"):
        op.execute(statement)
    op.execute(rls_v1.grant("subscriptions", "SELECT"))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
