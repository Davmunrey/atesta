"""Procrastinate 3.10.0 queue tables (ADR-003, ADR-012 amendment 2, scanner-connectors spec).

The schema SQL ships in the pinned procrastinate wheel. Its sha256 is checked first, so this
migration can never apply another version's schema; upgrading procrastinate needs a new
migration with that release's migration scripts.

atesta_app gets table privileges on the four queue tables and EXECUTE on Procrastinate's
functions, which are revoked from PUBLIC. Procrastinate defines no SECURITY DEFINER function
(the schema linter checks).

Revision ID: 0009
Revises: 0008
"""

import hashlib
from pathlib import Path

import procrastinate
import queue_v1
import rls_v1
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SCHEMA = Path(procrastinate.__file__).with_name("sql") / "schema.sql"
SCHEMA_SHA256 = "c70ec4b400a60ad9592787653aae5ae77ae41bf801d56b5bd2712751a07f2009"


def schema_sql() -> str:
    raw = SCHEMA.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SCHEMA_SHA256:
        raise RuntimeError(f"procrastinate schema.sql is not 3.10.0 (sha256 {digest})")
    return raw.decode("utf-8")


def upgrade() -> None:
    # psycopg with no parameters sends the text unparsed (the schema has literal % signs), on
    # the migration's own connection and transaction. Pinned, hash-checked file only.
    driver = op.get_bind().connection.driver_connection
    if driver is None:
        raise RuntimeError("migration connection has no driver connection")
    driver.execute(schema_sql())
    for table in queue_v1.TABLES:
        op.execute(rls_v1.grant(table, "SELECT", "INSERT", "UPDATE", "DELETE"))
    op.execute(queue_v1.SEQUENCES)
    op.execute(queue_v1.FUNCTIONS)


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
