"""Procrastinate queue schema migrations (issue #123): verbatim release SQL, pinned by digest."""

import hashlib
from pathlib import Path

import procrastinate
from sqlalchemy import Engine, text

SQL = Path(__file__).resolve().parents[2] / "migrations" / "sql"
PINNED = {
    # Copied from the procrastinate wheels on PyPI (3.10.0: sha256 949ad25b…, 3.11.0: 97e143ad…).
    "procrastinate-3.10.0-schema.sql": (
        "c70ec4b400a60ad9592787653aae5ae77ae41bf801d56b5bd2712751a07f2009"
    ),
    "procrastinate-3.11.0-03.11.00_01_pre_fetch_job_skip_null_lock.sql": (
        "0d305a337820e3b2369b06e82df462094fdfbb417808fb982c9b91d0c42a0de6"
    ),
}


def test_vendored_queue_sql_is_the_release_text() -> None:
    assert sorted(p.name for p in SQL.glob("*.sql")) == sorted(PINNED)
    for name, digest in PINNED.items():
        assert hashlib.sha256((SQL / name).read_bytes()).hexdigest() == digest, name


APPLIED_UP_TO = "03.11.00"  # the newest procrastinate migration script an Alembic migration applies


def test_the_installed_procrastinate_ships_no_queue_migration_we_have_not_applied() -> None:
    """A version bump that changes the queue schema fails here until a migration vendors it."""
    shipped = (Path(procrastinate.__file__).with_name("sql") / "migrations").glob("*.sql")
    newer = sorted(p.name for p in shipped if p.name[:8] > APPLIED_UP_TO)
    assert newer == [], (
        f"procrastinate ships queue migrations without an Alembic migration: {newer}"
    )
    vendored = {
        name.split("-", 2)[2] for name in PINNED if name.count("-") >= 2 and "schema" not in name
    }
    latest = {
        p.name
        for p in (Path(procrastinate.__file__).with_name("sql") / "migrations").glob("*.sql")
        if p.name.startswith(APPLIED_UP_TO)
    }
    assert latest <= vendored


def test_a_fresh_database_runs_the_3_11_fetch_function_with_frozen_grants(
    superuser: Engine,
) -> None:
    with superuser.connect() as conn:
        source = conn.scalar(
            text("SELECT prosrc FROM pg_proc WHERE proname = 'procrastinate_fetch_job_v2'")
        )
        assert source is not None and "jobs.lock IS NULL" in source
        signature = "procrastinate_fetch_job_v2(character varying[], bigint)"
        assert conn.scalar(
            text("SELECT has_function_privilege('atesta_app', :f, 'EXECUTE')"), {"f": signature}
        )
        public = conn.scalar(
            text(
                "SELECT bool_or(a.grantee = 0) FROM pg_proc p,"
                " aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a"
                " WHERE p.proname = 'procrastinate_fetch_job_v2'"
            )
        )
        assert public is False
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) >= "0018"
