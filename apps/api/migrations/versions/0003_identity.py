"""Identity tables and per-command policies (identity-auth spec, ADR-012).

Revision ID: 0003
Revises: 0002
"""

import rls_v1
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

ROLES = "role IN ('owner', 'admin', 'member')"

# Read branches are FOR SELECT only; every write passes tenant_isolation or the self policy.
POLICIES = (
    "CREATE POLICY own_orgs_read ON organizations FOR SELECT USING (id IN (SELECT"
    " organization_id FROM memberships WHERE user_id = app_setting_uuid('app.user_id')))",
    "ALTER TABLE users ENABLE ROW LEVEL SECURITY",
    "CREATE POLICY self_or_comember_read ON users FOR SELECT USING ("
    "cognito_sub = app_setting_text('app.subject') OR id IN (SELECT user_id FROM memberships"
    " WHERE organization_id = app_setting_uuid('app.organization_id')))",
    "CREATE POLICY self_insert ON users FOR INSERT"
    " WITH CHECK (cognito_sub = app_setting_text('app.subject'))",
    "CREATE POLICY self_update ON users FOR UPDATE USING (cognito_sub ="
    " app_setting_text('app.subject')) WITH CHECK (cognito_sub = app_setting_text('app.subject'))",
    "CREATE POLICY own_memberships_read ON memberships FOR SELECT USING ("
    "app_setting_uuid('app.organization_id') IS NULL"
    " AND user_id = app_setting_uuid('app.user_id'))",
    "CREATE POLICY invitation_token_read ON invitations FOR SELECT"
    " USING (token_sha256 = app_setting_text('app.invitation_token_sha256'))",
)


def _ts(name: str, nullable: bool = False) -> sa.Column[object]:
    default = None if nullable else sa.func.now()
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=nullable)


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    name = f"fk_{table}_{column}_{target.split('.')[0]}"
    return sa.ForeignKeyConstraint([column], [target], name=name, ondelete="RESTRICT")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cognito_sub", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("locale", sa.Text(), server_default="es", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("locale IN ('es', 'en')", name="ck_users_locale"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("cognito_sub", name="uq_users_cognito_sub"),
    )
    op.create_index("ix_users_lower_email", "users", [sa.text("lower(email)")])
    op.create_table(
        "memberships",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        _ts("created_at"),
        sa.CheckConstraint(ROLES, name="ck_memberships_role"),
        _fk("memberships", "organization_id", "organizations.id"),
        _fk("memberships", "user_id", "users.id"),
        sa.PrimaryKeyConstraint("organization_id", "user_id", name="pk_memberships"),
    )
    op.create_index("ix_memberships_organization_id", "memberships", ["organization_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("token_sha256", sa.Text(), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _ts("accepted_at", nullable=True),
        _ts("revoked_at", nullable=True),
        _ts("created_at"),
        sa.CheckConstraint(ROLES, name="ck_invitations_role"),
        _fk("invitations", "organization_id", "organizations.id"),
        _fk("invitations", "invited_by", "users.id"),
        sa.PrimaryKeyConstraint("id", name="pk_invitations"),
        sa.UniqueConstraint("organization_id", "id", name="uq_invitations_organization_id_id"),
    )
    op.create_index("ix_invitations_organization_id", "invitations", ["organization_id"])
    op.create_index("ix_invitations_token_sha256", "invitations", ["token_sha256"])
    for table in ("memberships", "invitations"):
        for statement in rls_v1.tenant_rls(table):
            op.execute(statement)
        op.execute(rls_v1.grant(table, "SELECT", "INSERT", "UPDATE", "DELETE"))
    for statement in POLICIES:
        op.execute(statement)
    op.execute(rls_v1.grant("users", "SELECT", "INSERT", "UPDATE"))
    op.execute(rls_v1.grant("organizations", "INSERT", "UPDATE"))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
