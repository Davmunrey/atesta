"""Notification preferences and the delivery log (notifications spec PR 1, #379).

Two tenant tables with the standard policy (ADR-012 amendment 7). A preference row exists only
for an optional type a person turned off or back on. A delivery row is claimed once per person,
type and dedupe key; only its status, provider message id and sent time ever change. No subject,
body or address is stored (rule 2).

Revision ID: 0027
Revises: 0026
"""

import rls_v1
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

KINDS = (
    "kind IN ('connection_alert', 'incident_clock', 'scan_problem', 'due_digest', 'weekly_summary')"
)
IDENTITY_FIXED = (
    "CREATE FUNCTION notification_deliveries_fixed() RETURNS trigger LANGUAGE plpgsql"
    " SET search_path = pg_catalog AS $$ BEGIN"
    " IF NEW.organization_id IS DISTINCT FROM OLD.organization_id"
    " OR NEW.id IS DISTINCT FROM OLD.id"
    " OR NEW.user_id IS DISTINCT FROM OLD.user_id"
    " OR NEW.kind IS DISTINCT FROM OLD.kind"
    " OR NEW.dedupe_key IS DISTINCT FROM OLD.dedupe_key"
    " OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN"
    " RAISE EXCEPTION 'notification_deliveries: only the delivery status may change'"
    " USING ERRCODE = 'check_violation'; END IF; RETURN NEW; END $$"
)


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('scan_problem', 'due_digest', 'weekly_summary')",
            name=op.f("ck_notification_preferences_kind_optional"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_notification_preferences_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "user_id", "kind", name=op.f("pk_notification_preferences")
        ),
    )
    op.create_index(
        op.f("ix_notification_preferences_organization_id"),
        "notification_preferences",
        ["organization_id"],
        unique=False,
    )
    for statement in rls_v1.tenant_rls("notification_preferences"):
        op.execute(statement)
    op.execute(rls_v1.grant("notification_preferences", "SELECT", "INSERT", "UPDATE"))

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(KINDS, name=op.f("ck_notification_deliveries_kind")),
        sa.CheckConstraint(
            "status IN ('queued', 'sent', 'failed', 'suppressed')",
            name=op.f("ck_notification_deliveries_status"),
        ),
        sa.CheckConstraint(
            "char_length(dedupe_key) BETWEEN 1 AND 200",
            name=op.f("ck_notification_deliveries_dedupe_key_length"),
        ),
        sa.CheckConstraint(
            "(status = 'sent') = (sent_at IS NOT NULL)",
            name=op.f("ck_notification_deliveries_sent_at_when_sent"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_notification_deliveries_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_deliveries")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_notification_deliveries_organization_id_id")
        ),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            "kind",
            "dedupe_key",
            name=op.f("uq_notification_deliveries_organization_id_user_id_kind_dedupe_key"),
        ),
    )
    op.create_index(
        op.f("ix_notification_deliveries_organization_id"),
        "notification_deliveries",
        ["organization_id"],
        unique=False,
    )
    for statement in rls_v1.tenant_rls("notification_deliveries"):
        op.execute(statement)
    op.execute(rls_v1.grant("notification_deliveries", "SELECT", "INSERT", "UPDATE"))
    op.execute(IDENTITY_FIXED)
    op.execute(
        "CREATE TRIGGER notification_deliveries_fixed BEFORE UPDATE ON notification_deliveries"
        " FOR EACH ROW EXECUTE FUNCTION notification_deliveries_fixed()"
    )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
