"""Table classes from ADR-012 that runtime checks need. The schema linter extends this."""

TENANT_ROOT = "organizations"
APPEND_ONLY = frozenset({"audit_events"})
CATALOG: frozenset[str] = frozenset()
