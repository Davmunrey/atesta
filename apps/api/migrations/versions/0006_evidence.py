"""Append-only evidence and evidence-control links (control-model spec, NFR-05).

Revision ID: 0006
Revises: 0005
"""

import rls_v1
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("sha256", sa.CHAR(length=64), nullable=True),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "kind = 'attestation' OR storage_key IS NOT NULL",
            name=op.f("ck_evidence_file_required"),
        ),
        sa.CheckConstraint(
            "kind IN ('scan_output', 'document', 'attestation')", name=op.f("ck_evidence_kind")
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_evidence_sha256_format")),
        sa.CheckConstraint(
            "source_type <> 'scan' OR source_id IS NOT NULL", name=op.f("ck_evidence_scan_named")
        ),
        sa.CheckConstraint(
            "source_type = 'scan' OR created_by IS NOT NULL", name=op.f("ck_evidence_author_named")
        ),
        sa.CheckConstraint(
            "source_type IN ('scan', 'upload', 'user')", name=op.f("ck_evidence_source_type")
        ),
        sa.CheckConstraint(
            "storage_key IS NULL OR (left(storage_key, 37) = organization_id::text || '/'"
            " AND storage_key ~ '^[0-9a-f-]{36}(/[A-Za-z0-9_.-]+)+$'"
            " AND storage_key !~ '(^|/)\\.{1,2}(/|$)')",
            name=op.f("ck_evidence_storage_key_in_tenant_prefix"),
        ),
        sa.CheckConstraint(
            "num_nulls(storage_key, sha256, media_type, size_bytes) IN (0, 4)",
            name=op.f("ck_evidence_file_described"),
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_evidence_size_positive")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_evidence_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
        sa.UniqueConstraint("organization_id", "id", name=op.f("uq_evidence_organization_id_id")),
    )
    op.create_index(
        op.f("ix_evidence_organization_id"), "evidence", ["organization_id"], unique=False
    )
    op.create_table(
        "evidence_controls",
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("control_key", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "evidence_id"],
            ["evidence.organization_id", "evidence.id"],
            name=op.f("fk_evidence_controls_organization_id_evidence_id_evidence"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_evidence_controls_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "evidence_id", "control_key", name=op.f("pk_evidence_controls")
        ),
    )
    op.create_index(
        op.f("ix_evidence_controls_organization_id"),
        "evidence_controls",
        ["organization_id"],
        unique=False,
    )
    for table in ("evidence", "evidence_controls"):
        for statement in rls_v1.tenant_rls(table):
            op.execute(statement)
        op.execute(rls_v1.grant(table, "SELECT", "INSERT"))  # append-only


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
