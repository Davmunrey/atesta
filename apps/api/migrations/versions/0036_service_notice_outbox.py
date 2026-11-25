"""Service notice outbox (operator-portal spec, "Service notices"; ADR-012 amendment 12, #474).

Owner choice, 2026-11-24, relayed by the coordinator: "Bandeja de salida (Recomendado)". The
operator service cannot defer a job (it has no privilege on the queue tables), so it inserts a
row here, in the transaction of the action that owes the notice; the worker sends it.

- service_notices: ids, a kind and two times; no RLS and no organization foreign key, like the
  queue tables (ADR-012 amendment 2): it holds no customer content and outlives erasure.
- atesta_operator: INSERT of id, organization_id and kind only; no SELECT, UPDATE or DELETE.
- atesta_app (the worker): SELECT, and UPDATE of sent_at only.
- notification_deliveries.kind gains 'service_notice', so each send is claimed once per person.

Revision ID: 0036
Revises: 0035
"""

import operator_v1
import outbox_v1
import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

KINDS = (
    "organization_suspended",
    "organization_reactivated",
    "export_requested",
    "closure_started_by_operator",
)
DELIVERY_KINDS = (
    "connection_alert",
    "evidence_malware",
    "incident_clock",
    "scan_problem",
    "due_digest",
    "weekly_summary",
)


def _kinds(values: tuple[str, ...]) -> str:
    return "kind IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "service_notices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_kinds(KINDS), name=op.f("ck_service_notices_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_notices")),
    )
    op.create_index(
        "ix_service_notices_pending",
        "service_notices",
        ["created_at"],
        postgresql_where=sa.text("sent_at IS NULL"),
    )
    op.execute(operator_v1.grant("service_notices", "INSERT", "id organization_id kind"))
    for statement in outbox_v1.APP_GRANTS:
        op.execute(statement)

    op.drop_constraint("ck_notification_deliveries_kind", "notification_deliveries")
    op.create_check_constraint(
        op.f("ck_notification_deliveries_kind"),
        "notification_deliveries",
        _kinds((*DELIVERY_KINDS, "service_notice")),
    )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
