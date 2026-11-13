"""Schema linter: clean on head, and each fail-open object is caught (ADR-012)."""

import json
import os
from collections.abc import Iterator

import pytest
from atesta_api.platform.schema_check import SNAPSHOT, problems, snapshot
from sqlalchemy import Connection, Engine

PROBES = frozenset({"probe", "probe_child", "badfk"})


@pytest.fixture
def owner_tx(superuser: Engine, probe: object) -> Iterator[Connection]:
    """Superuser connection inside a transaction that is always rolled back (DDL included)."""
    with superuser.connect() as conn:
        tx = conn.begin()
        try:
            yield conn
        finally:
            tx.rollback()


def test_head_schema_is_clean(owner_tx: Connection) -> None:
    if os.environ.get("ATESTA_UPDATE_SCHEMA_SNAPSHOT") == "1":
        SNAPSHOT.write_text(json.dumps(snapshot(owner_tx, PROBES), indent=1) + "\n")
    assert problems(owner_tx, PROBES) == []


BAD_OBJECTS = {
    "extra permissive policy": ("CREATE POLICY leak ON audit_events USING (true)", "differ from"),
    "altered tenant policy": (
        "ALTER POLICY tenant_isolation ON audit_events USING (true)",
        "differ from",
    ),
    "truncate grant": ("GRANT TRUNCATE ON audit_events TO atesta_app", "differ from"),
    "column grant": ("GRANT UPDATE (action) ON audit_events TO atesta_app", "differ from"),
    "grant to PUBLIC": ("GRANT DELETE ON organizations TO PUBLIC", "differ from"),
    "grant option": ("GRANT SELECT ON controls TO atesta_app WITH GRANT OPTION", "differ from"),
    "unclassified table": ("CREATE TABLE stray (id int)", "stray is not classified"),
    "table outside public": (
        "CREATE SCHEMA side; CREATE TABLE side.t (id int)",
        "side.t is outside public",
    ),
    "view without security_invoker": ("CREATE VIEW v AS SELECT 1 AS x", "v lacks security_invoker"),
    "materialized view": ("CREATE MATERIALIZED VIEW mv AS SELECT 1 AS x", "mv is banned"),
    "security definer function": (
        "CREATE FUNCTION f() RETURNS int LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'",
        "function f is banned",
    ),
    "rls disabled": ("ALTER TABLE audit_events DISABLE ROW LEVEL SECURITY", "has RLS disabled"),
    "single-column tenant fk": (
        "CREATE TABLE badfk (id uuid PRIMARY KEY, organization_id uuid NOT NULL"
        " REFERENCES organizations(id), probe_id uuid REFERENCES probe(id));"
        " CREATE INDEX ON badfk (organization_id); ALTER TABLE badfk ENABLE ROW LEVEL SECURITY",
        "must be composite with organization_id",
    ),
    "unique key not led by tenant": (
        "CREATE UNIQUE INDEX bad_uq ON probe (v)",
        "must start with organization_id",
    ),
}


@pytest.mark.parametrize("name", sorted(BAD_OBJECTS))
def test_linter_catches_fail_open_object(owner_tx: Connection, name: str) -> None:
    ddl, expected = BAD_OBJECTS[name]
    owner_tx.exec_driver_sql(ddl)
    assert any(expected in p for p in problems(owner_tx, PROBES)), problems(owner_tx, PROBES)
