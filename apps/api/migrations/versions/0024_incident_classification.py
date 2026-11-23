"""When an incident is classified as significant (recorded-routines spec, issue #224).

incident_updates gains the kind 'classified' and its time, classified_at, once per incident.
Reporting clocks that start at classification (Delegated Regulation (EU) 2025/301, Art. 5) read
it. Existing rows are notes, clocks and closings, so the new CHECK holds for them.

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "incident_updates",
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(op.f("ck_incident_updates_kind"), "incident_updates")
    op.create_check_constraint(
        op.f("ck_incident_updates_kind"),
        "incident_updates",
        "kind IN ('note', 'clock', 'closed', 'classified')",
    )
    op.create_check_constraint(
        op.f("ck_incident_updates_classified_at_for_classified"),
        "incident_updates",
        "(kind = 'classified') = (classified_at IS NOT NULL)",
    )
    op.create_index(
        "uq_incident_updates_classified",
        "incident_updates",
        ["organization_id", "incident_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'classified'"),
    )


def downgrade() -> None:
    op.drop_index("uq_incident_updates_classified", table_name="incident_updates")
    op.drop_constraint(op.f("ck_incident_updates_classified_at_for_classified"), "incident_updates")
    op.execute("DELETE FROM incident_updates WHERE kind = 'classified'")
    op.drop_constraint(op.f("ck_incident_updates_kind"), "incident_updates")
    op.create_check_constraint(
        op.f("ck_incident_updates_kind"),
        "incident_updates",
        "kind IN ('note', 'clock', 'closed')",
    )
    op.drop_column("incident_updates", "classified_at")
