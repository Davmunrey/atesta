"""A manual review cites the evidence it rests on (manual-control-review spec, #262).

control_reviews gains evidence_ids: at most 20 evidence ids of the same org, checked through
evidence.api at write time. Reviews recorded before this read as citing none.

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "control_reviews",
        sa.Column(
            "evidence_ids",
            postgresql.ARRAY(sa.Uuid()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_control_reviews_evidence_ids_bounded"),
        "control_reviews",
        "cardinality(evidence_ids) <= 20",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_control_reviews_evidence_ids_bounded"), "control_reviews", type_="check"
    )
    op.drop_column("control_reviews", "evidence_ids")
