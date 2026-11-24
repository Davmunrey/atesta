"""Operator tables (operator-portal spec, ADR-017, ADR-012 amendments 3 and 8, #449).

- operator_staff: staff and their role. The account itself lives in the staff Cognito pool.
- operator_audit_events: the operator trail, append-only for atesta_operator, reads included.
- erasure_requests: a second admin approves within 7 days, or a sole admin after 72 hours
  (owner answer 3). requested_at is always the database's: the role cannot insert it. Only the
  erasure runner, as atesta_owner, sets executed_at and the receipt link.

Operator tables: no RLS, no foreign key to organizations (they outlive erasure), and no privilege
for atesta_app.

Revision ID: 0034
Revises: 0033
"""

import operator_v1
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

# ADR-012 amendment 8: (table, privilege, columns); no columns means the whole table.
OPERATOR_GRANTS = (
    ("operator_staff", "SELECT", ""),
    ("operator_staff", "INSERT", ""),
    ("operator_staff", "UPDATE", "role disabled_at"),
    ("operator_audit_events", "SELECT", ""),
    ("operator_audit_events", "INSERT", ""),
    ("erasure_requests", "SELECT", ""),
    ("erasure_requests", "INSERT", "id organization_id requested_by"),
    ("erasure_requests", "UPDATE", "approved_by approved_at cancelled_by cancelled_at"),
)


def _ts(name: str, *, now: bool = False) -> "sa.Column[object]":
    """A timestamptz column: NOT NULL DEFAULT now() when `now`, else nullable."""
    default = sa.text("now()") if now else None
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=not now)


def _staff_fk(column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        ["operator_staff.id"],
        name=op.f(f"fk_erasure_requests_{column}_operator_staff"),
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        "operator_staff",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cognito_sub", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        _ts("created_at", now=True),
        _ts("disabled_at"),
        sa.CheckConstraint(
            "role IN ('admin', 'billing', 'support')", name=op.f("ck_operator_staff_role")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operator_staff")),
        sa.UniqueConstraint("cognito_sub", name=op.f("uq_operator_staff_cognito_sub")),
    )
    op.create_table(
        "operator_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        _ts("occurred_at", now=True),
        sa.Column("staff_id", sa.Uuid(), nullable=True),
        sa.Column("staff_role", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(staff_id IS NULL) = (staff_role IS NULL)",
            name=op.f("ck_operator_audit_events_staff_together"),
        ),
        sa.CheckConstraint(
            "staff_id IS NOT NULL OR action = 'erasure.executed'",
            name=op.f("ck_operator_audit_events_staff_unless_runner"),
        ),
        sa.CheckConstraint(
            "staff_role IN ('admin', 'billing', 'support')",
            name=op.f("ck_operator_audit_events_staff_role"),
        ),
        sa.CheckConstraint(
            r"action ~ '^[a-z][a-z_]*(\.[a-z][a-z_]*)+$'",
            name=op.f("ck_operator_audit_events_action"),
        ),
        sa.CheckConstraint(
            "length(reason) BETWEEN 1 AND 500", name=op.f("ck_operator_audit_events_reason")
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["operator_staff.id"],
            name=op.f("fk_operator_audit_events_staff_id_operator_staff"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operator_audit_events")),
    )
    for column in ("organization_id", "staff_id"):
        op.create_index(
            op.f(f"ix_operator_audit_events_{column}"), "operator_audit_events", [column]
        )
    op.create_table(
        "erasure_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        _ts("requested_at", now=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        _ts("approved_at"),
        sa.Column("cancelled_by", sa.Uuid(), nullable=True),
        _ts("cancelled_at"),
        _ts("executed_at"),
        sa.Column("receipt_id", sa.Uuid(), nullable=True),
        *(
            sa.CheckConstraint(check, name=op.f(f"ck_erasure_requests_{name}"))
            for name, check in (
                ("approved_together", "(approved_by IS NULL) = (approved_at IS NULL)"),
                ("cancelled_together", "(cancelled_by IS NULL) = (cancelled_at IS NULL)"),
                ("executed_together", "(executed_at IS NULL) = (receipt_id IS NULL)"),
                (
                    "executed_only_approved",
                    "executed_at IS NULL OR (approved_at IS NOT NULL AND cancelled_at IS NULL)",
                ),
                (
                    "approval_window",
                    "approved_at IS NULL OR (approved_at >= requested_at"
                    " AND approved_at <= requested_at + interval '7 days')",
                ),
                (
                    "second_admin_or_cooling_off",
                    "approved_by IS NULL OR approved_by <> requested_by"
                    " OR approved_at >= requested_at + interval '72 hours'",
                ),
                (
                    "not_approved_after_cancel",
                    "approved_at IS NULL OR cancelled_at IS NULL OR approved_at <= cancelled_at",
                ),
            )
        ),
        *(_staff_fk(c) for c in ("requested_by", "approved_by", "cancelled_by")),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["erasure_receipts.id"],
            name=op.f("fk_erasure_requests_receipt_id_erasure_receipts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_erasure_requests")),
    )
    op.create_index(
        "ux_erasure_requests_open",
        "erasure_requests",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("cancelled_at IS NULL AND executed_at IS NULL"),
    )

    for table, privilege, columns in OPERATOR_GRANTS:
        op.execute(operator_v1.grant(table, privilege, columns))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
