"""Startup guard: one misconfiguration per test, each must be refused."""

from collections.abc import Iterator

import pytest
from atesta_api.platform.db import make_engine
from atesta_api.platform.guard import assert_safe_runtime_role
from sqlalchemy import Engine
from sqlalchemy.engine import URL

from .conftest import APP_PASSWORD

APP = "atesta_app"
# name: (apply, undo, expected problems)
MISCONFIGURATIONS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "owner role inherited": (
        f"GRANT atesta_owner TO {APP}",
        f"REVOKE atesta_owner FROM {APP}",
        ("member of another role", "owner privileges"),
    ),
    "bypassrls role via SET": (
        f"CREATE ROLE guard_bypass NOLOGIN BYPASSRLS; GRANT guard_bypass TO {APP}"
        " WITH INHERIT FALSE, SET TRUE",
        "DROP ROLE guard_bypass",
        ("member of another role",),
    ),
    "role has BYPASSRLS": (
        f"ALTER ROLE {APP} BYPASSRLS",
        f"ALTER ROLE {APP} NOBYPASSRLS",
        ("superuser or has BYPASSRLS",),
    ),
    "role owns a table": (  # a throwaway table: an owner round trip on probe drops its grants
        f"CREATE TABLE guard_owned (x int); ALTER TABLE guard_owned OWNER TO {APP}",
        "DROP TABLE guard_owned",
        ("owner privileges",),
    ),
    "pg_write_all_data": (
        f"GRANT pg_write_all_data TO {APP}",
        f"REVOKE pg_write_all_data FROM {APP}",
        ("can write an append-only", "privilege on alembic_version"),
    ),
    "update on audit_events": (
        f"GRANT UPDATE ON audit_events TO {APP}",
        f"REVOKE UPDATE ON audit_events FROM {APP}",
        ("can write an append-only",),
    ),
    "column update on audit_events": (
        f"GRANT UPDATE (action) ON audit_events TO {APP}",
        f"REVOKE UPDATE (action) ON audit_events FROM {APP}",
        ("can write an append-only",),
    ),
    "update on a retention table": (
        f"GRANT UPDATE ON api_token_usage TO {APP}",
        f"REVOKE UPDATE ON api_token_usage FROM {APP}",
        ("retention table",),
    ),
    "column update on a retention table": (
        f"GRANT UPDATE (at) ON api_token_usage TO {APP}",
        f"REVOKE UPDATE (at) ON api_token_usage FROM {APP}",
        ("retention table",),
    ),
    "retention table without its age limit": (
        "DROP POLICY retention ON api_token_usage",
        "CREATE POLICY retention ON api_token_usage AS RESTRICTIVE FOR DELETE"
        " USING (at < now() - interval '90 days')",
        ("retention table",),
    ),
    "column insert on a catalog table": (
        f"GRANT INSERT (key, title_es, title_en, description_es, description_en) ON controls"
        f" TO {APP}",
        f"REVOKE INSERT (key, title_es, title_en, description_es, description_en) ON controls"
        f" FROM {APP}",
        ("can write an append-only",),
    ),
    "select on alembic_version": (
        f"GRANT SELECT ON alembic_version TO {APP}",
        f"REVOKE SELECT ON alembic_version FROM {APP}",  # noqa: S608
        ("privilege on alembic_version",),
    ),
    "column select on alembic_version": (
        f"GRANT SELECT (version_num) ON alembic_version TO {APP}",
        f"REVOKE SELECT (version_num) ON alembic_version FROM {APP}",  # noqa: S608
        ("privilege on alembic_version",),
    ),
    "truncate on tenant table": (
        f"GRANT TRUNCATE ON probe TO {APP}",
        f"REVOKE TRUNCATE ON probe FROM {APP}",
        ("TRUNCATE",),
    ),
    "column references on tenant table": (
        f"GRANT REFERENCES (id) ON probe TO {APP}",
        f"REVOKE REFERENCES (id) ON probe FROM {APP}",
        ("TRUNCATE, REFERENCES or TRIGGER",),
    ),
    "create on public": (
        f"GRANT CREATE ON SCHEMA public TO {APP}",
        f"REVOKE CREATE ON SCHEMA public FROM {APP}",
        ("CREATE on schema public",),
    ),
    "role default setting": (
        f"ALTER ROLE {APP} SET app.organization_id = 'aaaaaaaa-0000-4000-8000-000000000001'",
        f"ALTER ROLE {APP} RESET app.organization_id",
        ("app.* default",),
    ),
}


@pytest.fixture
def app_url(database: URL, probe: object) -> URL:
    return database.set(username="atesta_app", password=APP_PASSWORD)


def _engine(url: URL, **kwargs: object) -> Engine:
    return make_engine(url, sslmode="disable", null_pool=True, **kwargs)  # type: ignore[arg-type]


def test_clean_setup_passes(app_url: URL) -> None:
    assert_safe_runtime_role(_engine(app_url), require_tls=False)


@pytest.fixture(params=sorted(MISCONFIGURATIONS))
def misconfigured(request: pytest.FixtureRequest, superuser: Engine) -> Iterator[str]:
    apply, undo, _ = MISCONFIGURATIONS[request.param]
    with superuser.begin() as conn:
        conn.exec_driver_sql(apply)
    try:
        yield request.param
    finally:
        with superuser.begin() as conn:
            conn.exec_driver_sql(undo)


def test_misconfiguration_is_refused(misconfigured: str, app_url: URL) -> None:
    with pytest.raises(RuntimeError) as refused:
        assert_safe_runtime_role(_engine(app_url), require_tls=False)
    for expected in MISCONFIGURATIONS[misconfigured][2]:
        assert expected in str(refused.value)


def test_setting_in_connection_options_is_refused(app_url: URL) -> None:
    url = app_url.update_query_dict(
        {"options": "-c app.user_id=11111111-0000-4000-8000-000000000001"}
    )
    with pytest.raises(RuntimeError, match=r"carries app\.user_id"):
        assert_safe_runtime_role(_engine(url), require_tls=False)


def test_plaintext_connection_is_refused_when_tls_required(app_url: URL) -> None:
    with pytest.raises(RuntimeError, match="not TLS"):
        assert_safe_runtime_role(_engine(app_url), require_tls=True)
