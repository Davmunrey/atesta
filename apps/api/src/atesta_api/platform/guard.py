"""Startup guard: refuse to run with a runtime role that could bypass tenant isolation.

Conditions are listed in the tenant-data-layer spec ("Startup guard").
"""

from sqlalchemy import Connection, Engine, text

from atesta_api.platform.context import SETTING_NAMES
from atesta_api.platform.tables import APPEND_ONLY, CATALOG

_PUBLIC = "SELECT c.oid, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
_CHECKS = {
    "is superuser or has BYPASSRLS": (
        "SELECT 1 FROM pg_roles WHERE rolname = current_user AND (rolsuper OR rolbypassrls)"
    ),
    "is a member of another role": (
        "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member"
        " WHERE r.rolname = current_user"
    ),
    "has owner privileges on objects in public": (
        f"SELECT 1 FROM ({_PUBLIC} WHERE n.nspname = 'public'"  # noqa: S608
        "   AND pg_has_role(current_user, c.relowner, 'USAGE')) t"
        " UNION ALL SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
        " WHERE n.nspname = 'public' AND pg_has_role(current_user, p.proowner, 'USAGE')"
        " UNION ALL SELECT 1 FROM pg_namespace WHERE nspname = 'public'"
        "   AND pg_has_role(current_user, nspowner, 'USAGE')"
    ),
    "has CREATE on schema public": "SELECT 1 WHERE has_schema_privilege('public', 'CREATE')",
    "holds TRUNCATE, REFERENCES or TRIGGER on a table": (
        f"{_PUBLIC} WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')"  # noqa: S608
        " AND has_table_privilege(c.oid, 'TRUNCATE, REFERENCES, TRIGGER')"
    ),
    "can write an append-only or catalog table": (
        f"{_PUBLIC} WHERE n.nspname = 'public' AND ("  # noqa: S608
        " (c.relname = ANY(:append_only) AND has_table_privilege(c.oid, 'UPDATE, DELETE'))"
        " OR (c.relname = ANY(:catalog) AND has_table_privilege(c.oid, 'INSERT, UPDATE, DELETE')))"
    ),
    "has a privilege on alembic_version": (
        f"{_PUBLIC} WHERE n.nspname = 'public' AND c.relname = 'alembic_version'"  # noqa: S608
        " AND has_table_privilege(c.oid, 'SELECT, INSERT, UPDATE, DELETE')"
    ),
    "has an app.* default for its role or database": (
        "SELECT 1 FROM pg_db_role_setting s, unnest(s.setconfig) AS cfg"
        " WHERE cfg LIKE 'app.%'"
        " AND s.setrole IN (0, (SELECT oid FROM pg_roles WHERE rolname = current_user))"
        " AND s.setdatabase IN"
        "   (0, (SELECT oid FROM pg_database WHERE datname = current_database()))"
    ),
}


def startup_problems(conn: Connection, *, require_tls: bool) -> list[str]:
    params = {"append_only": sorted(APPEND_ONLY), "catalog": sorted(CATALOG)}
    problems = [
        f"runtime role {label}"
        for label, sql in _CHECKS.items()
        if conn.execute(text(sql), params).first() is not None
    ]
    for _, name in SETTING_NAMES:
        if conn.execute(text("SELECT current_setting(:n, true)"), {"n": name}).scalar() not in (
            None,
            "",
        ):
            problems.append(f"fresh connection already carries {name}")
    if require_tls:
        version = conn.execute(
            text("SELECT version FROM pg_stat_ssl WHERE pid = pg_backend_pid() AND ssl")
        ).scalar()
        if version not in ("TLSv1.2", "TLSv1.3"):
            problems.append("connection is not TLS 1.2 or later")
    return problems


def assert_safe_runtime_role(engine: Engine, *, require_tls: bool) -> None:
    """Raise at startup if isolation could be bypassed. Run on a fresh pooled connection."""
    with engine.connect() as conn:
        problems = startup_problems(conn, require_tls=require_tls)
        conn.rollback()
    if problems:
        raise RuntimeError("unsafe database setup: " + "; ".join(problems))
