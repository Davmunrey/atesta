"""Table classes from ADR-012. Adding a table means adding it here (the schema linter checks)."""

TENANT_ROOT = "organizations"
MIGRATIONS = "alembic_version"
TENANT = frozenset({"audit_events", "memberships", "invitations"})
APPEND_ONLY = frozenset({"audit_events"})
GLOBAL_IDENTITY = frozenset({"users"})
CATALOG: frozenset[str] = frozenset()


def table_classes(extra_tenant: frozenset[str] = frozenset()) -> dict[str, str]:
    classes = {TENANT_ROOT: "root", MIGRATIONS: "migrations"}
    classes |= dict.fromkeys(TENANT | extra_tenant, "tenant")
    classes |= dict.fromkeys(GLOBAL_IDENTITY, "identity")
    classes |= dict.fromkeys(CATALOG, "catalog")
    return classes
