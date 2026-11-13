"""Frozen RLS SQL, version 1 (tenant-data-layer spec).

Never edit after merge. A policy change is rls_v2.py plus a migration that reapplies it.
"""

import re

_IDENT = re.compile(r"[a-z_][a-z0-9_]*")
_PRIVILEGES = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})
_TENANT = "organization_id = app_setting_uuid('app.organization_id')"
_ROOT = "id = app_setting_uuid('app.organization_id')"

SETTING_FUNCTIONS = (
    "CREATE FUNCTION app_setting_uuid(name text) RETURNS uuid LANGUAGE sql STABLE"
    " AS $$ SELECT NULLIF(current_setting(name, true), '')::uuid $$",
    "CREATE FUNCTION app_setting_text(name text) RETURNS text LANGUAGE sql STABLE"
    " AS $$ SELECT NULLIF(current_setting(name, true), '') $$",
    "REVOKE ALL ON FUNCTION app_setting_uuid(text), app_setting_text(text) FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION app_setting_uuid(text), app_setting_text(text) TO atesta_app",
)


def _ident(name: str) -> str:
    if not _IDENT.fullmatch(name):
        raise ValueError(f"bad identifier: {name!r}")
    return name


def _policy(table: str, predicate: str) -> tuple[str, str]:
    t = _ident(table)
    return (
        f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY",
        f"CREATE POLICY tenant_isolation ON {t} USING ({predicate}) WITH CHECK ({predicate})",
    )


def tenant_rls(table: str) -> tuple[str, str]:
    """Standard policy for a tenant table."""
    return _policy(table, _TENANT)


def tenant_root_rls(table: str) -> tuple[str, str]:
    """Standard policy keyed on id, for the tenant root."""
    return _policy(table, _ROOT)


def grant(table: str, *privileges: str) -> str:
    """Explicit grants to atesta_app. Never ALL, never TRUNCATE, REFERENCES or TRIGGER."""
    if not privileges or set(privileges) - _PRIVILEGES:
        raise ValueError(f"privileges must come from {sorted(_PRIVILEGES)}")
    return f"GRANT {', '.join(privileges)} ON {_ident(table)} TO atesta_app"
