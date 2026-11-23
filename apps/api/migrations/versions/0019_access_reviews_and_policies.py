"""Access reviews and policies (recorded-routines spec, part A).

Tenant tables with the standard RLS policy. Append-only except access_reviews, which is updated
once, to close it.

Revision ID: 0019
Revises: 0018
"""

import rls_v1
import sqlalchemy as sa
from alembic import op

APPEND_ONLY = ("access_review_entries", "access_review_decisions", "policies", "policy_approvals")

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("system", sa.Text(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(closed_at IS NULL) = (closed_by IS NULL)",
            name=op.f("ck_access_reviews_closed_together"),
        ),
        sa.CheckConstraint(
            "length(btrim(system)) BETWEEN 1 AND 200", name=op.f("ck_access_reviews_system_length")
        ),
        sa.CheckConstraint(
            "length(btrim(title)) BETWEEN 1 AND 200", name=op.f("ck_access_reviews_title_length")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_access_reviews_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_reviews")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_access_reviews_organization_id_id")
        ),
    )
    op.create_index(
        op.f("ix_access_reviews_organization_id"),
        "access_reviews",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("location_url", sa.Text(), nullable=False),
        sa.Column("review_months", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "left(location_url, 8) = 'https://' AND length(location_url) <= 2000",
            name=op.f("ck_policies_location_https"),
        ),
        sa.CheckConstraint(
            "length(btrim(title)) BETWEEN 1 AND 200", name=op.f("ck_policies_title_length")
        ),
        sa.CheckConstraint(
            "review_months BETWEEN 1 AND 36", name=op.f("ck_policies_review_months")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_policies_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policies")),
        sa.UniqueConstraint("organization_id", "id", name=op.f("uq_policies_organization_id_id")),
    )
    op.create_index(
        op.f("ix_policies_organization_id"), "policies", ["organization_id"], unique=False
    )
    op.create_table(
        "access_review_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("account", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "length(btrim(account)) BETWEEN 1 AND 320",
            name=op.f("ck_access_review_entries_account_length"),
        ),
        sa.CheckConstraint(
            "length(detail) <= 200", name=op.f("ck_access_review_entries_detail_length")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_id"],
            ["access_reviews.organization_id", "access_reviews.id"],
            name=op.f("fk_access_review_entries_organization_id_review_id_access_reviews"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_access_review_entries_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_review_entries")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_access_review_entries_organization_id_id")
        ),
    )
    op.create_index(
        op.f("ix_access_review_entries_organization_id"),
        "access_review_entries",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "policy_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("sha256", sa.CHAR(length=64), nullable=True),
        sa.Column("approver_name", sa.Text(), nullable=False),
        sa.Column("approved_on", sa.Date(), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_policy_approvals_sha256_format"),
        ),
        sa.CheckConstraint(
            "length(btrim(approver_name)) BETWEEN 1 AND 200",
            name=op.f("ck_policy_approvals_approver_length"),
        ),
        sa.CheckConstraint(
            "length(btrim(version)) BETWEEN 1 AND 50",
            name=op.f("ck_policy_approvals_version_length"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "policy_id"],
            ["policies.organization_id", "policies.id"],
            name=op.f("fk_policy_approvals_organization_id_policy_id_policies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_policy_approvals_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_approvals")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_policy_approvals_organization_id_id")
        ),
    )
    op.create_index(
        "ix_policy_approvals_latest",
        "policy_approvals",
        ["organization_id", "policy_id", "recorded_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_policy_approvals_organization_id"),
        "policy_approvals",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "access_review_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('keep', 'revoke')", name=op.f("ck_access_review_decisions_decision")
        ),
        sa.CheckConstraint(
            "length(note) <= 1000", name=op.f("ck_access_review_decisions_note_length")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "entry_id"],
            ["access_review_entries.organization_id", "access_review_entries.id"],
            name=op.f("fk_access_review_decisions_organization_id_entry_id_access_review_entries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_access_review_decisions_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_review_decisions")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_access_review_decisions_organization_id_id")
        ),
    )
    op.create_index(
        "ix_access_review_decisions_latest",
        "access_review_decisions",
        ["organization_id", "entry_id", "decided_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_access_review_decisions_organization_id"),
        "access_review_decisions",
        ["organization_id"],
        unique=False,
    )
    for statement in rls_v1.tenant_rls("access_reviews"):
        op.execute(statement)
    op.execute(rls_v1.grant("access_reviews", "SELECT", "INSERT", "UPDATE"))  # closing only
    for table in APPEND_ONLY:
        for statement in rls_v1.tenant_rls(table):
            op.execute(statement)
        op.execute(rls_v1.grant(table, "SELECT", "INSERT"))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
