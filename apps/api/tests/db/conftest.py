"""DB fixtures: fresh database, bootstrap as superuser, migrate as atesta_owner, test as atesta_app.

db_rollback: one outer transaction rolled back; for tests with a single app transaction.
db_commit: real commits, as in production; for context-lifetime and multi-transaction tests.
"""

import importlib.util
import os
import secrets
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from atesta_api.main import app
from atesta_api.modules.identity.cognito import AccessToken, InvalidTokenError, UserInfo
from atesta_api.platform import db
from atesta_api.platform.db import make_engine
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

API_DIR = Path(__file__).resolve().parents[2]
APP_PASSWORD = "atesta-test-only"  # noqa: S105  local test role, never deployed
ORG_A = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
ORG_B = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")


def load_rls() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rls_v1", API_DIR / "migrations" / "rls_v1.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def database() -> Iterator[URL]:
    admin_url = os.environ.get("ATESTA_TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("ATESTA_TEST_DATABASE_URL not set")
    os.environ.setdefault("ATESTA_DB_SSLMODE", "disable")
    admin = make_url(admin_url)
    name = f"atesta_test_{secrets.token_hex(4)}"
    server = make_engine(admin, sslmode="disable", null_pool=True)
    with server.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    url = admin.set(database=name)
    with make_engine(url, sslmode="disable", null_pool=True).begin() as conn:
        conn.exec_driver_sql((API_DIR / "migrations" / "bootstrap.sql").read_text())
        conn.exec_driver_sql(f"ALTER ROLE atesta_app LOGIN PASSWORD '{APP_PASSWORD}'")
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    config.attributes["role"] = "atesta_owner"
    command.upgrade(config, "head")
    yield url
    with server.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


@pytest.fixture(scope="session")
def superuser(database: URL) -> Engine:
    return make_engine(database, sslmode="disable", null_pool=True)


@pytest.fixture(scope="session")
def app_engine(database: URL) -> Engine:
    url = database.set(username="atesta_app", password=APP_PASSWORD)
    return make_engine(url, sslmode="disable", pool_size=1, max_overflow=0)


@pytest.fixture(scope="session")
def probe(superuser: Engine) -> dict[uuid.UUID, uuid.UUID]:
    """Two orgs and probe tables (parent, child with a composite FK), seeded for A and B."""
    rls = load_rls()
    with superuser.begin() as conn:
        conn.exec_driver_sql("SET ROLE atesta_owner")
        conn.exec_driver_sql(
            "CREATE TABLE probe (id uuid PRIMARY KEY, organization_id uuid NOT NULL"
            " REFERENCES organizations(id), v text, UNIQUE (organization_id, id))"
        )
        conn.exec_driver_sql(
            "CREATE TABLE probe_child (organization_id uuid NOT NULL, probe_id uuid NOT NULL,"
            " PRIMARY KEY (organization_id, probe_id), FOREIGN KEY (organization_id, probe_id)"
            " REFERENCES probe (organization_id, id))"
        )
        for table in ("probe", "probe_child"):
            for statement in (*rls.tenant_rls(table), rls.grant(table, "SELECT", "INSERT")):
                conn.exec_driver_sql(statement)
        conn.exec_driver_sql(rls.grant("probe", "UPDATE", "DELETE"))
        conn.exec_driver_sql("RESET ROLE")
        ids = {ORG_A: uuid.uuid4(), ORG_B: uuid.uuid4()}
        for org, label in ((ORG_A, "a"), (ORG_B, "b")):
            conn.execute(
                text("INSERT INTO organizations (id, name) VALUES (:o, :n)"), {"o": org, "n": label}
            )
            conn.execute(
                text("INSERT INTO probe VALUES (:i, :o, :v)"),
                {"i": ids[org], "o": org, "v": label},
            )
    return ids


@pytest.fixture
def db_rollback(app_engine: Engine, probe: object) -> Iterator[Session]:
    with app_engine.connect() as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


@pytest.fixture
def db_commit(app_engine: Engine, probe: object) -> Iterator[sessionmaker[Session]]:
    """Tests using it clean up their committed rows as superuser."""
    yield sessionmaker(bind=app_engine)


# HTTP fixtures: fake Cognito, real database with RLS.


class FakeVerifier:
    def verify(self, token: str) -> AccessToken:
        if not token.startswith("tok-"):
            raise InvalidTokenError
        return AccessToken(sub=token.removeprefix("tok-"), scopes=frozenset({"openid"}))


class FakeProvider:
    def __init__(self) -> None:
        self.emails: dict[str, str] = {}
        self.unverified: set[str] = set()
        self.calls = 0

    def userinfo(self, access_token: str) -> UserInfo:
        self.calls += 1
        sub = access_token.removeprefix("tok-")
        email = self.emails.get(sub, f"{sub}@example.com")
        return UserInfo(sub=sub, email=email, email_verified=sub not in self.unverified)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def client(database: URL, probe: object, provider: FakeProvider) -> Iterator[TestClient]:
    engine = db.make_engine(
        database.set(username="atesta_app", password=APP_PASSWORD), sslmode="disable", pool_size=4
    )
    db.configure(engine)
    app.state.token_verifier = FakeVerifier()
    app.state.identity_provider = provider
    yield TestClient(app)  # no lifespan: wiring is done above
    db._factory = None
    engine.dispose()


def auth(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer tok-{sub}"}


def new_sub() -> str:
    return f"sub-{uuid.uuid4().hex[:8]}"
