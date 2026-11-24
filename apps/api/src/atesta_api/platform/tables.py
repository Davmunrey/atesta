"""Table classes from ADR-012. Adding a table means adding it here (the schema linter checks)."""

from collections import Counter

TENANT_ROOT = "organizations"
MIGRATIONS = "alembic_version"
TENANT = frozenset(
    {
        "audit_events",
        "memberships",
        "invitations",
        "score_snapshots",
        "evidence",
        "evidence_controls",
        "evidence_statements",
        "evidence_file_scans",
        "connections",
        "scans",
        "scan_check_results",
        "findings",
        "control_reviews",
        "framework_scopes",
        "requirement_assessments",
        "assessment_reviews",
        "requirement_assignments",
        "access_reviews",
        "access_review_entries",
        "access_review_decisions",
        "policies",
        "policy_approvals",
        "training_campaigns",
        "training_acknowledgements",
        "incidents",
        "incident_updates",
        "api_tokens",
        "api_ingestions",
        "api_token_usage",
        "assessment_proposals",
        "notification_preferences",
        "notification_deliveries",
        "subscriptions",  # billing: read-only for atesta_app, set by the operator
        "billing_profiles",  # billing: read-only for atesta_app, set by the operator
    }
)
APPEND_ONLY = frozenset(
    {
        "audit_events",
        "score_snapshots",
        "evidence",
        "evidence_controls",
        "evidence_statements",
        "evidence_file_scans",
        "scan_check_results",
        "findings",
        "control_reviews",
        "framework_scopes",
        "requirement_assessments",
        "assessment_reviews",
        "requirement_assignments",
        "access_review_entries",
        "access_review_decisions",
        "policies",
        "policy_approvals",
        "training_acknowledgements",
        "incidents",
        "incident_updates",
        "api_ingestions",
    }
)
# ADR-012 amendment 9: insert-only until a row reaches this age in days, then atesta_app may
# delete it. A restrictive DELETE policy named `retention` holds the limit in the database.
RETENTION_DAYS = {"api_token_usage": 90}
GLOBAL_IDENTITY = frozenset({"users"})
# ADR-012 amendment 3: written only by the operator's erasure command, as atesta_owner. No RLS and
# no privilege for atesta_app; the receipt outlives the organization it records.
OPERATOR = frozenset({"erasure_receipts"})
OPERATOR_APPEND_ONLY = frozenset({"erasure_receipts"})
# ADR-012 amendment 8: the closed list of columns atesta_operator may read, through column grants.
# Every other table and column gives it nothing. Changing it needs that amendment and both
# snapshots changed in the same reviewed pull request.
OPERATOR_READ: dict[str, frozenset[str]] = {
    name: frozenset(columns.split())
    for name, columns in {
        "organizations": "id name locale created_at trial_ends_at closure_requested_at"
        " closure_origin suspended_at suspension_reason",
        "subscriptions": "organization_id plan addons note updated_at",
        "billing_profiles": "organization_id legal_name tax_id address_line1 address_line2"
        " postal_code city region country contact_email updated_at",
        "memberships": "organization_id role",
        "invitations": "organization_id expires_at accepted_at revoked_at",
        "connections": "organization_id provider status",
        "scans": "organization_id status queued_at finished_at",
        "api_tokens": "organization_id expires_at revoked_at",
        "api_token_usage": "organization_id at",
        "audit_events": "organization_id action occurred_at",
        "erasure_receipts": "id organization_id closure_requested_at erased_at row_counts",
    }.items()
}
CATALOG = frozenset(
    {"frameworks", "requirements", "controls", "checks", "control_checks", "mappings"}
)
# Procrastinate 3.10.0 (ADR-012 amendment 2): no organization_id, no RLS, job arguments are ids.
QUEUE = frozenset(
    {
        "procrastinate_jobs",
        "procrastinate_events",
        "procrastinate_periodic_defers",
        "procrastinate_workers",
    }
)


def class_sets(extra_tenant: frozenset[str] = frozenset()) -> dict[str, frozenset[str]]:
    return {
        "root": frozenset({TENANT_ROOT}),
        "migrations": frozenset({MIGRATIONS}),
        "tenant": TENANT | extra_tenant,
        "identity": GLOBAL_IDENTITY,
        "catalog": CATALOG,
        "queue": QUEUE,
        "operator": OPERATOR,
    }


def duplicated(extra_tenant: frozenset[str] = frozenset()) -> list[str]:
    """Tables registered in more than one class: each must be in exactly one."""
    counts = Counter(name for names in class_sets(extra_tenant).values() for name in names)
    return sorted(name for name, count in counts.items() if count > 1)


def table_classes(extra_tenant: frozenset[str] = frozenset()) -> dict[str, str]:
    return {name: c for c, names in class_sets(extra_tenant).items() for name in names}
