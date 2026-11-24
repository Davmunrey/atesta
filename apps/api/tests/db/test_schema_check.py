"""Schema linter: clean on head, and each fail-open object is caught (ADR-012)."""

import json
import os
from collections.abc import Iterator

import pytest
from atesta_api.platform import tables
from atesta_api.platform.schema_check import SNAPSHOT, problems, snapshot
from sqlalchemy import Connection, Engine

PROBES = frozenset({"probe", "probe_child", "badfk", "nofk"})


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
    "operator column grant": (
        "GRANT SELECT (display_name) ON connections TO atesta_operator",
        "differ from",
    ),
    "operator table grant": ("GRANT SELECT ON evidence TO atesta_operator", "differ from"),
    "operator policy": (
        "CREATE POLICY operator_metadata_read ON evidence FOR SELECT TO atesta_operator"
        " USING (true)",
        "differ from",
    ),
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
    "tenant only in INCLUDE": (
        "CREATE UNIQUE INDEX uq_ci ON probe (lower(v)) INCLUDE (organization_id)",
        "must start with organization_id",
    ),
    "unique key on an expression only": (
        "CREATE UNIQUE INDEX uq_expr ON probe (lower(v))",
        "must start with organization_id",
    ),
    "exclusion constraint not led by tenant": (
        "ALTER TABLE probe ADD CONSTRAINT ex_v EXCLUDE USING btree (v WITH =)",
        "must start with organization_id",
    ),
    "exclusion constraint comparing tenant with <>": (
        "CREATE EXTENSION btree_gist; ALTER TABLE probe ADD CONSTRAINT ex_ne"
        " EXCLUDE USING gist (organization_id WITH <>, v WITH =)",
        "must start with organization_id",
    ),
    "rewrite rule on a table": (
        "CREATE RULE r1 AS ON INSERT TO audit_events DO ALSO NOTHING",
        "rule r1 on public.audit_events is banned",
    ),
    "rewrite rule on a security_invoker view": (
        "CREATE VIEW vi WITH (security_invoker = true) AS SELECT id FROM probe;"
        " CREATE RULE vi_ins AS ON INSERT TO vi DO INSTEAD NOTHING",
        "rule vi_ins on public.vi is banned",
    ),
    "cascading fk": (
        "ALTER TABLE probe_child ADD CONSTRAINT casc FOREIGN KEY (organization_id, probe_id)"
        " REFERENCES probe (organization_id, id) ON DELETE CASCADE",
        "FK casc on public.probe_child must be NO ACTION or RESTRICT",
    ),
    "set default fk on update": (
        "ALTER TABLE evidence ADD COLUMN probe_id uuid;"
        " ALTER TABLE evidence ADD CONSTRAINT setdef FOREIGN KEY (organization_id, probe_id)"
        " REFERENCES probe (organization_id, id) ON UPDATE SET DEFAULT",
        "FK setdef on public.evidence must be NO ACTION or RESTRICT",
    ),
    "cascade from a tenant table into a queue table": (
        "ALTER TABLE evidence ADD COLUMN job_id bigint;"
        " ALTER TABLE evidence ADD CONSTRAINT jobfk FOREIGN KEY (job_id)"
        " REFERENCES procrastinate_jobs (id) ON DELETE CASCADE",
        "FK jobfk on public.evidence must be NO ACTION or RESTRICT",
    ),
    "unclassified queue-like table": (
        "CREATE TABLE procrastinate_extra (id bigint)",
        "procrastinate_extra is not classified",
    ),
    "tenant table without FK to organizations": (
        "CREATE TABLE nofk (id uuid PRIMARY KEY, organization_id uuid NOT NULL);"
        " CREATE INDEX ON nofk (organization_id); ALTER TABLE nofk ENABLE ROW LEVEL SECURITY",
        "tenant table nofk lacks an FK from organization_id to organizations(id)",
    ),
}


@pytest.mark.parametrize("name", sorted(BAD_OBJECTS))
def test_linter_catches_fail_open_object(owner_tx: Connection, name: str) -> None:
    ddl, expected = BAD_OBJECTS[name]
    owner_tx.exec_driver_sql(ddl)
    assert any(expected in p for p in problems(owner_tx, PROBES)), problems(owner_tx, PROBES)


def test_tenant_led_and_id_keys_are_clean(owner_tx: Connection) -> None:
    owner_tx.exec_driver_sql("CREATE UNIQUE INDEX uq_ok ON probe (organization_id, lower(v))")
    owner_tx.exec_driver_sql("CREATE UNIQUE INDEX uq_id_inc ON probe (id) INCLUDE (v)")
    owner_tx.exec_driver_sql(
        "ALTER TABLE probe ADD CONSTRAINT ex_ok"
        " EXCLUDE USING btree (organization_id WITH =, v WITH =)"
    )
    assert problems(owner_tx, PROBES) == []


def test_table_in_two_classes_is_reported(
    owner_tx: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tables, "GLOBAL_IDENTITY", tables.GLOBAL_IDENTITY | {"evidence"})
    assert "table evidence is in more than one class (ADR-012)" in problems(owner_tx, PROBES)
