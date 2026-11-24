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
    }
)
APPEND_ONLY = frozenset(
    {
        "audit_events",
        "score_snapshots",
        "evidence",
        "evidence_controls",
        "evidence_statements",
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
        "api_token_usage",
    }
)
GLOBAL_IDENTITY = frozenset({"users"})
# ADR-012 amendment 3: written only by the operator's erasure command, as atesta_owner. No RLS and
# no privilege for atesta_app; the receipt outlives the organization it records.
OPERATOR = frozenset({"erasure_receipts"})
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
