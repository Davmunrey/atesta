"""API tokens and evidence ingestion (evidence-ingestion-api spec).

api_tokens is a tenant table with the standard RLS policy plus the named read policy
api_token_read (ADR-012 amendment 5); it is updated only to record last use or revocation.
api_ingestions is append-only. Evidence gains the source type "api", which names its token.

Revision ID: 0021
Revises: 0020
"""

import rls_v1
import sqlalchemy as sa
from alembic import op

READ_POLICY = (
    "CREATE POLICY api_token_read ON api_tokens FOR SELECT"
    " USING (token_sha256 = app_setting_text('app.api_token_sha256'))"
)

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("token_sha256", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), server_default="evidence:write", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("scope = 'evidence:write'", name=op.f("ck_api_tokens_scope")),
        sa.CheckConstraint(
            "token_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_api_tokens_token_format")
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by IS NULL)",
            name=op.f("ck_api_tokens_revoked_together"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_api_tokens_expires_after_creation")
        ),
        sa.CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 100", name=op.f("ck_api_tokens_name_length")
        ),
        sa.CheckConstraint("length(prefix) = 12", name=op.f("ck_api_tokens_prefix_length")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_api_tokens_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_api_tokens_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"],
            ["users.id"],
            name=op.f("fk_api_tokens_revoked_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
        sa.UniqueConstraint("organization_id", "id", name=op.f("uq_api_tokens_organization_id_id")),
    )
    op.create_index(
        op.f("ix_api_tokens_organization_id"), "api_tokens", ["organization_id"], unique=False
    )
    op.create_index(
        op.f("ix_api_tokens_token_sha256"), "api_tokens", ["token_sha256"], unique=False
    )
    op.create_table(
        "api_ingestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "external_id IS NULL OR length(external_id) BETWEEN 1 AND 200",
            name=op.f("ck_api_ingestions_external_id_length"),
        ),
        sa.CheckConstraint(
            "length(btrim(source)) BETWEEN 1 AND 50", name=op.f("ck_api_ingestions_source_length")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "evidence_id"],
            ["evidence.organization_id", "evidence.id"],
            name=op.f("fk_api_ingestions_organization_id_evidence_id_evidence"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_api_ingestions_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_ingestions")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_api_ingestions_organization_id_id")
        ),
        sa.UniqueConstraint(
            "organization_id",
            "token_id",
            "external_id",
            name=op.f("uq_api_ingestions_organization_id_token_id_external_id"),
        ),
    )
    op.create_index(
        op.f("ix_api_ingestions_organization_id"),
        "api_ingestions",
        ["organization_id"],
        unique=False,
    )
    op.drop_constraint(op.f("ck_evidence_source_type"), "evidence", type_="check")
    op.create_check_constraint(
        op.f("ck_evidence_source_type"),
        "evidence",
        "source_type IN ('scan', 'upload', 'user', 'api')",
    )
    op.create_check_constraint(
        op.f("ck_evidence_api_named"), "evidence", "source_type <> 'api' OR source_id IS NOT NULL"
    )
    for statement in rls_v1.tenant_rls("api_tokens"):
        op.execute(statement)
    op.execute(READ_POLICY)
    op.execute(rls_v1.grant("api_tokens", "SELECT", "INSERT", "UPDATE"))  # last use, revocation
    for statement in rls_v1.tenant_rls("api_ingestions"):
        op.execute(statement)
    op.execute(rls_v1.grant("api_ingestions", "SELECT", "INSERT"))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
