"""Identity endpoints over HTTP with RLS on (identity-auth spec test plan)."""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

import pytest
from atesta_api.main import app
from atesta_api.modules.identity.api import Member, Role, require_member, require_role
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from .conftest import APP_PASSWORD, FakeProvider, auth, new_sub


@app.get("/test/orgs/{org_id}/member")
def _member(member: Annotated[Member, Depends(require_member)]) -> dict[str, str]:
    return {"role": member.role}


@app.get("/test/orgs/{org_id}/admin")
def _admin(member: Annotated[Member, Depends(require_role(Role.ADMIN))]) -> dict[str, str]:
    return {"role": member.role}


def test_missing_or_invalid_token_is_401(client: TestClient) -> None:
    for headers in ({}, {"Authorization": "Bearer garbage"}):
        response = client.get("/v1/me", headers=headers)
        assert response.status_code == 401
        assert response.json() == {"detail": {"code": "auth.invalid_token"}}


def test_first_call_provisions_and_me_refreshes_email(
    client: TestClient, provider: FakeProvider, superuser: Engine
) -> None:
    sub = new_sub()
    first = client.get("/v1/me", headers=auth(sub)).json()
    assert (first["email"], first["memberships"], provider.calls) == (f"{sub}@example.com", [], 1)
    provider.emails[sub] = "changed@example.com"
    assert client.get("/v1/me", headers=auth(sub)).json()["email"] == "changed@example.com"
    with superuser.connect() as conn:
        rows = conn.execute(text("SELECT count(*) FROM users WHERE cognito_sub = :s"), {"s": sub})
        assert rows.scalar_one() == 1


def test_concurrent_first_calls_create_one_user(client: TestClient, superuser: Engine) -> None:
    sub = new_sub()
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(
            pool.map(lambda _: client.get("/v1/me", headers=auth(sub)).status_code, range(4))
        )
    assert codes == [200] * 4
    with superuser.connect() as conn:
        rows = conn.execute(text("SELECT count(*) FROM users WHERE cognito_sub = :s"), {"s": sub})
        assert rows.scalar_one() == 1


def test_create_org_makes_caller_owner_and_audits(client: TestClient, superuser: Engine) -> None:
    sub = new_sub()
    created = client.post("/v1/orgs", json={"name": "Acme"}, headers=auth(sub))
    assert created.status_code == 201
    org_id = created.json()["id"]
    memberships = client.get("/v1/me", headers=auth(sub)).json()["memberships"]
    assert memberships == [
        {"organization_id": org_id, "organization_name": "Acme", "role": "owner"}
    ]
    assert client.get(f"/test/orgs/{org_id}/admin", headers=auth(sub)).json() == {"role": "owner"}
    with superuser.connect() as conn:
        events = conn.execute(
            text("SELECT action FROM audit_events WHERE organization_id = :o"), {"o": org_id}
        )
        assert events.scalars().all() == ["org.created"]


def test_non_member_gets_404_and_member_below_admin_gets_403(
    client: TestClient, superuser: Engine
) -> None:
    owner, outsider, member = new_sub(), new_sub(), new_sub()
    org_id = client.post("/v1/orgs", json={"name": "Beta"}, headers=auth(owner)).json()["id"]
    user_id = client.get("/v1/me", headers=auth(member)).json()["id"]
    with superuser.begin() as conn:
        conn.execute(
            text("INSERT INTO memberships VALUES (:o, :u, 'member')"), {"o": org_id, "u": user_id}
        )
    outsider_resp = client.get(f"/test/orgs/{org_id}/member", headers=auth(outsider))
    assert (outsider_resp.status_code, outsider_resp.json()["detail"]["code"]) == (
        404,
        "identity.not_found",
    )
    assert client.get(f"/test/orgs/{org_id}/member", headers=auth(member)).status_code == 200
    assert client.get(f"/test/orgs/{org_id}/admin", headers=auth(member)).status_code == 403


def test_tokens_never_reach_logs(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    sub = new_sub()
    client.get("/v1/me", headers=auth(sub))
    client.get("/v1/me", headers={"Authorization": "Bearer garbage-token-value"})
    client.post("/v1/orgs", json={"name": "Gamma"}, headers=auth(sub))
    assert f"tok-{sub}" not in caplog.text
    assert "garbage-token-value" not in caplog.text


@pytest.fixture
def cognito_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "ATESTA_COGNITO_REGION": "eu-south-2",
        "ATESTA_COGNITO_USER_POOL_ID": "eu-south-2_TEST",
        "ATESTA_COGNITO_APP_CLIENT_ID": "client-1",
        "ATESTA_COGNITO_DOMAIN": "auth.example.com",
        "ATESTA_DB_SSLMODE": "disable",
        "ATESTA_WEB_BASE_URL": "https://app.example.com",
    }.items():
        monkeypatch.setenv(name, value)


@pytest.mark.usefixtures("cognito_env", "probe")
def test_startup_runs_the_guard(database: URL, monkeypatch: pytest.MonkeyPatch) -> None:
    app_url = database.set(username="atesta_app", password=APP_PASSWORD)
    monkeypatch.setenv("ATESTA_DATABASE_URL", app_url.render_as_string(hide_password=False))
    with TestClient(app) as started:
        assert started.get("/health").status_code == 200
    monkeypatch.setenv("ATESTA_DATABASE_URL", database.render_as_string(hide_password=False))
    with pytest.raises(RuntimeError, match="unsafe database setup"), TestClient(app):
        pass
