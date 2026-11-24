"""Malware scan results of uploaded evidence files (evidence-malware-scanning spec, #429).

One tenant table with the standard policy, append-only for atesta_app (SELECT and INSERT): the
first result recorded for a file is final (D4). `evidence` stays append-only; a result arrives
after its row, from the worker, so it cannot be a column there (D3). No row means pending.

Revision ID: 0031
Revises: 0030
"""

import rls_v1
import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

STATUSES = (
    "status IN ('no_threats_found', 'threats_found', 'unsupported', 'access_denied', 'failed',"
    " 'not_scanned')"
)


def upgrade() -> None:
    op.create_table(
        "evidence_file_scans",
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("object_version", sa.Text()),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("organization_id", "evidence_id"),
        sa.ForeignKeyConstraint(
            ["organization_id", "evidence_id"],
            ["evidence.organization_id", "evidence.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(STATUSES, name="status"),
        sa.CheckConstraint(
            "object_version IS NULL OR length(object_version) BETWEEN 1 AND 1024",
            name="object_version_length",
        ),
    )
    op.create_index(
        op.f("ix_evidence_file_scans_organization_id"),
        "evidence_file_scans",
        ["organization_id"],
        unique=False,
    )
    for statement in rls_v1.tenant_rls("evidence_file_scans"):
        op.execute(statement)
    op.execute(rls_v1.grant("evidence_file_scans", "SELECT", "INSERT"))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
