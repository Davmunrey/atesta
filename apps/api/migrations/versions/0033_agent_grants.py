"""An AI agent's OAuth authorization is a row of api_tokens (mcp-oauth spec, issue 354).

ADR-016 amendment 1 and ADR-012 amendment 11: an authorization is a key without a secret.
`kind` tells them apart and `oauth_client_id` names the approved client. No table, policy or
privilege changes: atesta_app already holds SELECT, INSERT and UPDATE on api_tokens, and the row
is found through the existing api_token_read policy.

Revision ID: 0033
Revises: 0032
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_tokens", sa.Column("kind", sa.Text(), server_default="key", nullable=False))
    op.add_column("api_tokens", sa.Column("oauth_client_id", sa.Text(), nullable=True))
    op.create_check_constraint(op.f("ck_api_tokens_kind"), "api_tokens", "kind IN ('key', 'oauth')")
    op.create_check_constraint(
        op.f("ck_api_tokens_oauth_client"),
        "api_tokens",
        "(kind = 'oauth') = (oauth_client_id IS NOT NULL)"
        " AND (oauth_client_id IS NULL OR oauth_client_id ~ '^[A-Za-z0-9_+.-]{1,128}$')",
    )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
