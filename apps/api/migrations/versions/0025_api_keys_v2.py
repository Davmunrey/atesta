"""API keys v2: scopes, a rate limit per key, and the usage log (api-keys-v2 spec, ADR-016).

api_tokens trades its single `scope` for a `scopes` array, backfilled to exactly
{evidence:write}, and gains rate_limit_per_minute (default 60). api_token_usage is a tenant
table with the standard policy, append-only: one row per accepted request, holding the route
template and the scope, never a body, query or customer content (rule 2). ADR-012 amendment 6.

Revision ID: 0025
Revises: 0024
"""

import rls_v1
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

SCOPES = (
    "'compliance:read', 'incidents:read', 'evidence:write', 'assessment:propose', 'routines:write'"
)

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_tokens",
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{evidence:write}'::text[]"),
            nullable=False,
        ),
    )
    op.add_column(
        "api_tokens",
        sa.Column("rate_limit_per_minute", sa.Integer(), server_default="60", nullable=False),
    )
    op.execute("UPDATE api_tokens SET scopes = ARRAY[scope]")
    op.drop_constraint(op.f("ck_api_tokens_scope"), "api_tokens", type_="check")
    op.drop_column("api_tokens", "scope")
    op.create_check_constraint(
        op.f("ck_api_tokens_scopes_known"),
        "api_tokens",
        f"cardinality(scopes) >= 1 AND scopes <@ ARRAY[{SCOPES}]::text[]",
    )
    op.create_check_constraint(
        op.f("ck_api_tokens_rate_limit_range"),
        "api_tokens",
        "rate_limit_per_minute BETWEEN 1 AND 600",
    )
    op.create_table(
        "api_token_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_id", sa.Uuid(), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')",
            name=op.f("ck_api_token_usage_method"),
        ),
        sa.CheckConstraint(
            "route ~ '^/api/v1/[a-z0-9/{}_.-]+$' AND length(route) <= 200",
            name=op.f("ck_api_token_usage_route_template"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "token_id"],
            ["api_tokens.organization_id", "api_tokens.id"],
            name=op.f("fk_api_token_usage_organization_id_token_id_api_tokens"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_api_token_usage_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_token_usage")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_api_token_usage_organization_id_id")
        ),
    )
    op.create_index(
        op.f("ix_api_token_usage_organization_id"),
        "api_token_usage",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_api_token_usage_organization_id_token_id_at"),
        "api_token_usage",
        ["organization_id", "token_id", "at"],
        unique=False,
    )
    for statement in rls_v1.tenant_rls("api_token_usage"):
        op.execute(statement)
    op.execute(rls_v1.grant("api_token_usage", "SELECT", "INSERT"))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
