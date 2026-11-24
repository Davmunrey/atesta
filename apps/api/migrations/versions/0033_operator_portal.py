"""Operator portal database layer (operator-portal spec, ADR-017, ADR-012 amendment 8, #445).

- organizations: suspension, a derived closure origin and the trial end. Adding trial_ends_at
  with its default gives every existing organization a trial ending 14 days after this runs.
- billing_profiles: a tenant table; atesta_app reads it, atesta_operator writes it.
- atesta_operator (created by bootstrap.sql): column grants on the closed list only, and named
  policies scoped to it. It never sets a tenant context; no content table gives it anything.
- atesta_app keeps UPDATE on organizations only for the columns customers change.

Revision ID: 0033
Revises: 0032
"""

import operator_v1
import rls_v1
import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

REASONS = "'non_payment', 'contract_ended', 'customer_request', 'security_review', 'other'"
CLOSURE_ORIGIN = (
    "CASE WHEN closure_requested_at IS NULL THEN NULL"
    " WHEN closure_requested_by IS NULL THEN 'operator' ELSE 'owner' END"
)
BILLING_FIELDS = {
    "legal_name": 200,
    "tax_id": 50,
    "address_line1": 200,
    "address_line2": 200,
    "postal_code": 20,
    "city": 100,
    "region": 100,
    "contact_email": 254,
}
BILLING_COLUMNS = f"{' '.join(BILLING_FIELDS)} country updated_at"
# ADR-012 amendment 8, closed list: (table, privilege, columns).
OPERATOR_GRANTS = (
    (
        "organizations",
        "SELECT",
        "id name locale created_at trial_ends_at closure_requested_at closure_origin"
        " suspended_at suspension_reason",
    ),
    ("organizations", "UPDATE", "suspended_at suspension_reason closure_requested_at"),
    ("subscriptions", "SELECT", "organization_id plan addons note updated_at"),
    ("subscriptions", "INSERT", "organization_id plan addons note updated_at"),
    ("subscriptions", "UPDATE", "plan addons note updated_at"),
    ("billing_profiles", "SELECT", f"organization_id {BILLING_COLUMNS}"),
    ("billing_profiles", "INSERT", f"organization_id {BILLING_COLUMNS}"),
    ("billing_profiles", "UPDATE", BILLING_COLUMNS),
    ("memberships", "SELECT", "organization_id role"),
    ("invitations", "SELECT", "organization_id expires_at accepted_at revoked_at"),
    ("connections", "SELECT", "organization_id provider status"),
    ("scans", "SELECT", "organization_id status queued_at finished_at"),
    ("api_tokens", "SELECT", "organization_id expires_at revoked_at"),
    ("api_token_usage", "SELECT", "organization_id at"),
    ("audit_events", "SELECT", "organization_id action occurred_at"),
    (
        "audit_events",
        "INSERT",
        "id organization_id action target_type target_id metadata request_id",
    ),
    ("erasure_receipts", "SELECT", "id organization_id closure_requested_at erased_at row_counts"),
)
METADATA_READ = (
    "organizations",
    "subscriptions",
    "billing_profiles",
    "memberships",
    "invitations",
    "connections",
    "scans",
    "api_tokens",
    "api_token_usage",
    "audit_events",
)
AUDIT_RULE = "action LIKE 'operator.%' AND actor_user_id IS NULL"
POLICIES = (
    *(
        f"CREATE POLICY operator_metadata_read ON {t} FOR SELECT TO atesta_operator USING (true)"
        for t in METADATA_READ
    ),
    *(
        f"CREATE POLICY operator_insert ON {t} FOR INSERT TO atesta_operator WITH CHECK (true)"
        for t in ("subscriptions", "billing_profiles")
    ),
    *(
        f"CREATE POLICY operator_update ON {t} FOR UPDATE TO atesta_operator"
        " USING (true) WITH CHECK (true)"
        for t in ("organizations", "subscriptions", "billing_profiles")
    ),
    "CREATE POLICY operator_audit_write ON audit_events FOR INSERT TO atesta_operator"
    f" WITH CHECK ({AUDIT_RULE})",
    # tenant_isolation applies to every role, so the role needs EXECUTE on the setting functions
    # for its INSERT check; this keeps the rule even if it sets app.organization_id itself.
    "CREATE POLICY operator_audit_only ON audit_events AS RESTRICTIVE FOR INSERT"
    f" TO atesta_operator WITH CHECK ({AUDIT_RULE})",
)


def _ts(name: str, *, now: bool = False) -> "sa.Column[object]":
    """A timestamptz column: NOT NULL DEFAULT now() when `now`, else nullable."""
    default = sa.text("now()") if now else None
    return sa.Column(name, sa.DateTime(timezone=True), server_default=default, nullable=not now)


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("closure_origin", sa.Text(), sa.Computed(CLOSURE_ORIGIN, persisted=True)),
    )
    op.add_column("organizations", _ts("suspended_at"))
    op.add_column("organizations", sa.Column("suspension_reason", sa.Text(), nullable=True))
    op.add_column(
        "organizations",
        sa.Column(
            "trial_ends_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now() + interval '14 days'"),
            nullable=False,
        ),
    )
    for name, check in (
        ("suspension_reason", f"suspension_reason IN ({REASONS})"),
        ("suspension_together", "(suspended_at IS NULL) = (suspension_reason IS NULL)"),
        ("closure_by_needs_at", "closure_requested_by IS NULL OR closure_requested_at IS NOT NULL"),
        ("trial_after_creation", "trial_ends_at > created_at"),
    ):
        op.create_check_constraint(op.f(f"ck_organizations_{name}"), "organizations", check)

    op.create_table(
        "billing_profiles",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        *(sa.Column(name, sa.Text(), nullable=True) for name in [*BILLING_FIELDS, "country"]),
        _ts("updated_at", now=True),
        *(
            sa.CheckConstraint(
                f"length(btrim({name})) BETWEEN 1 AND {size}",
                name=op.f(f"ck_billing_profiles_{name}"),
            )
            for name, size in BILLING_FIELDS.items()
        ),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name=op.f("ck_billing_profiles_country")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_billing_profiles_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_billing_profiles")),
    )
    for statement in rls_v1.tenant_rls("billing_profiles"):
        op.execute(statement)
    op.execute(rls_v1.grant("billing_profiles", "SELECT"))

    # Customers cannot lift a suspension or move a trial end (ADR-012 amendment 8, #445).
    for statement in operator_v1.APP_ORGANIZATIONS_UPDATE:
        op.execute(statement)
    for table, privilege, columns in OPERATOR_GRANTS:
        op.execute(operator_v1.grant(table, privilege, columns))
    op.execute(operator_v1.SETTING_FUNCTIONS)
    for statement in POLICIES:
        op.execute(statement)


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
