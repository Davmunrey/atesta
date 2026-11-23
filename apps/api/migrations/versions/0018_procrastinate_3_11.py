"""Procrastinate 3.10.0 -> 3.11.0 queue schema (ADR-003, ADR-012 amendment 2, issue #123).

Applies the release's own migration script, copied verbatim from the procrastinate 3.11.0 wheel
(sha256 97e143ad84c149ad115147b375d6478d871243e40d1db353deb4fe7a4619128d on PyPI) into
migrations/sql and checked by digest, so no hand-written queue SQL ever runs. The script only
replaces procrastinate_fetch_job_v2; CREATE OR REPLACE keeps the function's owner and grants, and
the frozen grants are re-applied to prove it. A fresh 3.10.0 schema plus this script was compared
with the 3.11.0 schema.sql through pg_dump: identical.

Revision ID: 0018
Revises: 0017
"""

import hashlib
from pathlib import Path

import queue_v1
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "sql"
    / "procrastinate-3.11.0-03.11.00_01_pre_fetch_job_skip_null_lock.sql"
)
SCRIPT_SHA256 = "0d305a337820e3b2369b06e82df462094fdfbb417808fb982c9b91d0c42a0de6"


def script_sql() -> str:
    raw = SCRIPT.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SCRIPT_SHA256:
        raise RuntimeError(f"procrastinate 3.11.0 migration script changed (sha256 {digest})")
    return raw.decode("utf-8")


def upgrade() -> None:
    driver = op.get_bind().connection.driver_connection
    if driver is None:
        raise RuntimeError("migration connection has no driver connection")
    driver.execute(script_sql())
    op.execute(queue_v1.FUNCTIONS)


def downgrade() -> None:
    raise NotImplementedError("Forward-only migrations: roll back with a new migration")
