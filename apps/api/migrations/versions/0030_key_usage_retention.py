"""The API key usage log keeps 90 days (api-keys-v2 spec, issue 353, ADR-012 amendment 9).

atesta_app gains DELETE on api_token_usage, so each organization's daily job can remove old
rows. The restrictive policy `retention` is ANDed with tenant_isolation: the runtime role can
delete a row only in its own organization and only once the row is 90 days old. UPDATE stays
refused, so a row's time cannot be moved to make it deletable.

rls_v1 is not changed: the standard tenant policy stays as it is, and this is one more named
policy on one table.

Revision ID: 0030
Revises: 0029
"""

import rls_v1
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE POLICY retention ON api_token_usage AS RESTRICTIVE FOR DELETE"
        " USING (at < now() - interval '90 days')"
    )
    op.execute(rls_v1.grant("api_token_usage", "DELETE"))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
