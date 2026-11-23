"""Organization closure request and erasure receipts (organization-closure spec).

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("closure_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("organizations", sa.Column("closure_requested_by", sa.Uuid(), nullable=True))
    # Operator class (ADR-012 amendment 3): global, no RLS, no privilege for atesta_app.
    op.create_table(
        "erasure_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("closure_requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "erased_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("row_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_erasure_receipts")),
    )


def downgrade() -> None:
    op.drop_table("erasure_receipts")
    op.drop_column("organizations", "closure_requested_by")
    op.drop_column("organizations", "closure_requested_at")
