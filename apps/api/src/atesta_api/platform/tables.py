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
    }
)
APPEND_ONLY = frozenset({"audit_events", "score_snapshots", "evidence", "evidence_controls"})
GLOBAL_IDENTITY = frozenset({"users"})
CATALOG = frozenset(
    {"frameworks", "requirements", "controls", "checks", "control_checks", "mappings"}
)


def class_sets(extra_tenant: frozenset[str] = frozenset()) -> dict[str, frozenset[str]]:
    return {
        "root": frozenset({TENANT_ROOT}),
        "migrations": frozenset({MIGRATIONS}),
        "tenant": TENANT | extra_tenant,
        "identity": GLOBAL_IDENTITY,
        "catalog": CATALOG,
    }


def duplicated(extra_tenant: frozenset[str] = frozenset()) -> list[str]:
    """Tables registered in more than one class: each must be in exactly one."""
    counts = Counter(name for names in class_sets(extra_tenant).values() for name in names)
    return sorted(name for name, count in counts.items() if count > 1)


def table_classes(extra_tenant: frozenset[str] = frozenset()) -> dict[str, str]:
    return {name: c for c, names in class_sets(extra_tenant).items() for name in names}
