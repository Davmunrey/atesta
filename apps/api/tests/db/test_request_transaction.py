"""DbSession commits before the response; bound values never reach errors or logs."""

import logging
import uuid
from collections.abc import Iterator

import pytest
from atesta_api.platform import db
from atesta_api.platform.context import TenantContext
from atesta_api.platform.db import DbSession, make_engine
from atesta_api.platform.tenancy import set_tenant_context
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .conftest import ORG_A, ORG_B

MARKER = "MARKER-7f3a-customer-text"


class _Base(DeclarativeBase):
    pass


class Probe(_Base):
    __tablename__ = "probe"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID]
    v: Mapped[str | None]


app = FastAPI()


@app.post("/probe/{org}")
def add_probe(org: uuid.UUID, session: DbSession) -> dict[str, str]:
    set_tenant_context(session, TenantContext(organization_id=ORG_A))
    session.add(Probe(organization_id=org, v=MARKER))  # flushed only at commit
    return {"status": "created"}


@pytest.fixture
def client(app_engine: Engine, superuser: Engine, probe: object) -> Iterator[TestClient]:
    db.configure(app_engine)
    yield TestClient(app, raise_server_exceptions=False)
    db._factory = None
    with superuser.begin() as conn:
        conn.execute(text("DELETE FROM probe WHERE v = :m"), {"m": MARKER})


def _stored(superuser: Engine) -> int:
    with superuser.connect() as conn:
        query = text("SELECT count(*) FROM probe WHERE v = :m")
        return int(conn.execute(query, {"m": MARKER}).scalar_one())


def test_success_is_committed_before_the_response(client: TestClient, superuser: Engine) -> None:
    assert client.post(f"/probe/{ORG_A}").status_code == 200
    assert _stored(superuser) == 1


def test_failed_commit_never_returns_2xx(client: TestClient, superuser: Engine) -> None:
    assert client.post(f"/probe/{ORG_B}").status_code == 500
    assert _stored(superuser) == 0


def test_bound_values_stay_out_of_errors_and_logs(
    app_engine: Engine, probe: object, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    with (
        Session(app_engine) as session,
        pytest.raises(DBAPIError, match="row-level security") as exc,
    ):
        set_tenant_context(session, TenantContext(organization_id=ORG_A))
        session.add(Probe(organization_id=ORG_B, v=MARKER))
        session.flush()
    assert MARKER not in str(exc.value)
    assert MARKER not in caplog.text


def test_engine_ignores_tls_settings_in_the_url(database: URL) -> None:
    """The URL asks for no TLS; make_engine's default (verify-full) demands it, so the plaintext
    test server refuses: against a real server, not only in the captured parameters."""
    url = database.update_query_dict({"sslmode": "disable"})
    with pytest.raises(OperationalError, match="SSL"), make_engine(url).connect():
        pass
