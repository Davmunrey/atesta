"""Schema linter (ADR-012, tenant-data-layer spec). Run as owner or superuser.

Used by the test suite and, after `alembic upgrade`, by the deploy job against the target DB.
"""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

from atesta_api.platform.tables import table_classes

SNAPSHOT = Path(__file__).with_name("schema_snapshot.json")
_TRUE = ("true", "on", "1", "yes")
# Catalog queries: constant SQL, no external input.
_RELATIONS = (
    "SELECT n.nspname, c.relname, c.relkind, c.relrowsecurity,"
    " coalesce(array_to_string(c.reloptions, ','), '')"
    " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
    " WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')"
    " AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')"
    " AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')"
    " AND n.nspname NOT LIKE 'pg\\_%temp%'"
)
_DEFINER = (
    "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
    " WHERE p.prosecdef"
    " AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')"
    " AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')"
    " AND n.nspname NOT LIKE 'pg\\_%temp%'"
)
_FKS = (
    "SELECT con.conname, cr.relname, fr.relname,"
    " (SELECT array_agg(a.attname ORDER BY k.i) FROM unnest(con.conkey) WITH ORDINALITY"
    "  AS k(n, i) JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.n),"
    " (SELECT array_agg(a.attname ORDER BY k.i) FROM unnest(con.confkey) WITH ORDINALITY"
    "  AS k(n, i) JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.n)"
    " FROM pg_constraint con JOIN pg_class cr ON cr.oid = con.conrelid"
    " JOIN pg_class fr ON fr.oid = con.confrelid WHERE con.contype = 'f'"
)
_UNIQUES = (
    "SELECT c.relname,"
    " (SELECT array_agg(a.attname ORDER BY k.i) FROM unnest(i.indkey::int2[]) WITH ORDINALITY"
    "  AS k(n, i) JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.n)"
    " FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid WHERE i.indisunique"
)
# Literal SQL only (no f-strings or variables), so static analysis sees constant queries.
_GRANTS = (
    "SELECT c.relname, '', CASE x.grantee WHEN 0 THEN 'PUBLIC' ELSE x.grantee::regrole::text END,"
    " string_agg(x.privilege_type || CASE WHEN x.is_grantable THEN '+grant' ELSE '' END,"
    " ',' ORDER BY x.privilege_type)"
    " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(c.relacl) x"
    " WHERE n.nspname = 'public' AND x.grantee IN (0, 'atesta_app'::regrole) GROUP BY 1, 2, 3"
    " UNION ALL SELECT c.relname, a.attname,"
    " CASE x.grantee WHEN 0 THEN 'PUBLIC' ELSE x.grantee::regrole::text END,"
    " string_agg(x.privilege_type || CASE WHEN x.is_grantable THEN '+grant' ELSE '' END,"
    " ',' ORDER BY x.privilege_type)"
    " FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid"
    " JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(a.attacl) x"
    " WHERE n.nspname = 'public' AND a.attnum > 0 AND NOT a.attisdropped"
    " AND x.grantee IN (0, 'atesta_app'::regrole) GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"
)
_ORG_COLUMN = (
    "SELECT a.attnotnull AND a.atttypid = 'uuid'::regtype,"
    " EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = a.attrelid AND i.indkey[0] = a.attnum)"
    " FROM pg_attribute a WHERE a.attrelid = to_regclass(:t) AND a.attname = 'organization_id'"
    " AND NOT a.attisdropped"
)


def snapshot(conn: Connection, exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Policies and grants to atesta_app or PUBLIC in public: what a reviewed PR may change.

    Grants come from the ACLs, table and column level, so a column grant, a grant to PUBLIC
    (which every role inherits) or a grant option shows up as a diff.
    """
    policies = conn.execute(
        text(
            "SELECT tablename, policyname, cmd, permissive, array_to_string(roles, ','),"
            " coalesce(qual, ''), coalesce(with_check, '') FROM pg_policies"
            " WHERE schemaname = 'public' ORDER BY 1, 2"
        )
    ).all()
    grants = conn.execute(text(_GRANTS)).all()
    return {
        "policies": [list(r) for r in policies if r[0] not in exclude],
        "grants": [list(r) for r in grants if r[0] not in exclude],
    }


def problems(conn: Connection, extra_tenant: frozenset[str] = frozenset()) -> list[str]:
    classes = table_classes(extra_tenant)
    found: list[str] = []
    relations = conn.execute(text(_RELATIONS)).all()
    existing = {r[1] for r in relations if r[0] == "public"}
    found += [
        f"table {name} is registered but does not exist"
        for name in sorted(set(table_classes()) - existing)
    ]
    for schema, name, kind, rls, options in relations:
        if kind == "m":
            found.append(f"materialized view {schema}.{name} is banned")
        elif kind == "v" and not any(f"security_invoker={v}" in options for v in _TRUE):
            found.append(f"view {schema}.{name} lacks security_invoker")
        elif schema != "public":
            found.append(f"relation {schema}.{name} is outside public")
        elif kind != "v" and name not in classes:
            found.append(f"table {name} is not classified in platform.tables (ADR-012)")
        elif classes.get(name) in ("tenant", "root", "identity") and not rls:
            found.append(f"table {name} has RLS disabled")
    for name in sorted(n for n, c in classes.items() if c == "tenant" and n in existing):
        row = conn.execute(text(_ORG_COLUMN), {"t": f"public.{name}"}).first()
        if row is None or not row[0]:
            found.append(f"tenant table {name} lacks organization_id uuid NOT NULL")
        elif not row[1]:
            found.append(f"tenant table {name} lacks an index leading with organization_id")
    for con, child, parent, cols, ref in conn.execute(text(_FKS)).all():
        both_tenant = classes.get(child) == classes.get(parent) == "tenant"
        paired = (
            "organization_id" in cols and ref[cols.index("organization_id")] == "organization_id"
        )
        if both_tenant and not paired:
            found.append(f"FK {con} on {child} must be composite with organization_id")
    for table, cols in conn.execute(text(_UNIQUES)).all():
        if classes.get(table) == "tenant" and cols != ["id"] and cols[0] != "organization_id":
            found.append(f"unique key {cols} on {table} must start with organization_id")
    found += [f"SECURITY DEFINER function {f} is banned" for (f,) in conn.execute(text(_DEFINER))]
    expected = json.loads(SNAPSHOT.read_text())
    if snapshot(conn, exclude=extra_tenant) != expected:
        found.append(f"policies or grants differ from {SNAPSHOT.name}; review and update it")
    return found
