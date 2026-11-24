"""OAuth grants for AI agents (mcp-oauth spec, issue 354), on real PostgreSQL.

A grant is an API key without a secret: one person, one approved client, one organization.
The hosted MCP server verifies the token and hands the identity to the API in-process; here
that hand-off is `as_agent`, which no request from outside can imitate.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest
from atesta_api.main import create_app
from atesta_api.modules.identity.api import AgentOAuth, AgentToken, as_agent, grant_digest
from atesta_api.modules.identity.cognito import InvalidTokenError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import Engine, text

from .conftest import FakeVerifier, auth
from .test_mcp_contract import framed
from .test_members import events, org_with
from .test_rbac import _add, _future

ISSUER = "https://cognito-idp.eu-south-2.amazonaws.com/eu-south-2_test"
RESOURCE = "https://testserver/mcp"
CLIENT_ID = "agent-client-1"
KEY = "/api/v1/key"
OAUTH = AgentOAuth(RESOURCE, ISSUER, {CLIENT_ID: "Agente Uno", "agent-client-2": "Agente Dos"})


def agent_token(sub: str, client_id: str = CLIENT_ID) -> str:
    """Shaped like a JWT (three parts), as the hosted server's gate expects."""
    return f"agent.{client_id}.{sub}"


class AgentVerifier(FakeVerifier):
    """`agent.<client>.<sub>` is a verified token of the hosted server; `tok-<sub>` a session."""

    def verify_agent(self, token: str, oauth: AgentOAuth) -> AgentToken:
        kind, _, rest = token.partition(".")
        client_id, _, sub = rest.partition(".")
        if kind != "agent" or client_id not in oauth.clients or not sub:
            raise InvalidTokenError
        return AgentToken(sub=sub, client_id=client_id)


@pytest.fixture
def oauth_on(client: TestClient) -> Iterator[TestClient]:
    client.app.state.agent_oauth = OAUTH  # type: ignore[attr-defined]  # Starlette state is dynamic
    client.app.state.token_verifier = AgentVerifier()  # type: ignore[attr-defined]  # as above
    yield client
    client.app.state.agent_oauth = None  # type: ignore[attr-defined]  # as above


def grant(client: TestClient, org: str, sub: str, **changes: Any) -> Any:
    body = {
        "client_id": CLIENT_ID,
        "scopes": ["compliance:read"],
        "expires_in_days": 30,
        **changes,
    }
    return client.post(f"/api/v1/orgs/{org}/agent-grants", json=body, headers=auth(sub))


def agent(client: TestClient, sub: str, client_id: str = CLIENT_ID) -> TestClient:
    """The API as the hosted server calls it after verifying that person's token."""
    wrapped = as_agent(client.app, grant_digest(ISSUER, client_id, sub))
    return TestClient(wrapped, base_url="https://testserver")


def test_an_admin_grants_an_approved_client_and_the_agent_acts_within_the_grant(
    oauth_on: TestClient, superuser: Engine
) -> None:
    client = oauth_on
    org, subs = org_with(client, superuser, ana="admin")
    listed = client.get(f"/api/v1/orgs/{org}/agent-clients", headers=auth(subs["ana"]))
    assert listed.json() == [
        {"client_id": CLIENT_ID, "name": "Agente Uno"},
        {"client_id": "agent-client-2", "name": "Agente Dos"},
    ]
    created = grant(client, org, subs["ana"], rate_limit_per_minute=2)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["kind"], body["client_id"], body["name"]) == ("oauth", CLIENT_ID, "Agente Uno")
    assert body["scopes"] == ["compliance:read"] and body["rate_limit_per_minute"] == 2
    assert "token" not in body  # nothing secret exists to show
    assert events(superuser, org, "agent_grant.created") == 1

    as_ana = agent(client, subs["ana"])
    me = as_ana.get(KEY)
    assert me.status_code == 200, me.text
    assert me.json()["scopes"] == ["compliance:read"] and me.json()["prefix"] == body["prefix"]
    # The grant's scopes and limit are a key's: 403 names the scope, the third call is 429.
    refused = as_ana.post("/api/v1/ingest/evidence", json={})
    assert refused.status_code == 403 and refused.json()["detail"]["scope"] == "evidence:write"
    assert as_ana.get(KEY).status_code == 200
    limited = as_ana.get(KEY)
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    usage = client.get(
        f"/api/v1/orgs/{org}/api-tokens/{body['id']}/usage", headers=auth(subs["owner"])
    ).json()
    assert usage["last_24h"] == 2

    keys = client.get(f"/api/v1/orgs/{org}/api-tokens", headers=auth(subs["owner"])).json()
    assert [(k["kind"], k["client_id"]) for k in keys] == [("oauth", CLIENT_ID)]
    # Any owner or admin revokes it, and the next request is refused at once.
    revoked = client.delete(
        f"/api/v1/orgs/{org}/api-tokens/{body['id']}", headers=auth(subs["owner"])
    )
    assert revoked.status_code == 204
    assert events(superuser, org, "agent_grant.revoked") == 1
    assert events(superuser, org, "api_token.revoked") == 0
    assert agent(client, subs["ana"]).get(KEY).status_code == 401


def test_only_owners_and_admins_grant_and_only_approved_clients(
    oauth_on: TestClient, superuser: Engine
) -> None:
    client = oauth_on
    org, subs = org_with(client, superuser, ana="member")
    auditor = _add(superuser, client, org, "auditor", _future())
    for sub in (subs["ana"], auditor):
        assert grant(client, org, sub).status_code == 403
        assert client.get(f"/api/v1/orgs/{org}/agent-clients", headers=auth(sub)).status_code == 403
    other, other_subs = org_with(client, superuser)
    assert grant(client, org, other_subs["owner"]).status_code == 404
    unknown = grant(client, org, subs["owner"], client_id="unknown-client")
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "identity.agent_client_unknown"
    for wrong in ({"scopes": []}, {"scopes": ["admin:all"]}, {"expires_in_days": 366}):
        assert grant(client, org, subs["owner"], **wrong).status_code == 422
    assert grant(client, org, subs["owner"]).status_code == 201
    again = grant(client, org, subs["owner"])
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "identity.agent_grant_exists"
    # Another client is another grant.
    assert grant(client, org, subs["owner"], client_id="agent-client-2").status_code == 201


def test_with_oauth_off_nothing_is_offered(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser)
    owner = auth(subs["owner"])
    assert client.get(f"/api/v1/orgs/{org}/agent-clients", headers=owner).json() == []
    off = grant(client, org, subs["owner"])
    assert off.status_code == 409 and off.json()["detail"]["code"] == "identity.agent_oauth_off"
    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
    ):
        assert client.get(path).status_code == 404


def test_the_metadata_is_public_and_names_the_authorization_server(oauth_on: TestClient) -> None:
    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
    ):
        found = oauth_on.get(path)
        assert found.status_code == 200, path
        assert found.json() == OAUTH.metadata()
    assert oauth_on.get("/.well-known/oauth-protected-resource/other").status_code == 404


def test_a_grant_stops_when_it_expires_or_its_person_is_no_longer_an_admin(
    oauth_on: TestClient, superuser: Engine
) -> None:
    client = oauth_on
    org, subs = org_with(client, superuser, ana="admin", leo="admin")
    assert grant(client, org, subs["ana"]).status_code == 201
    assert grant(client, org, subs["leo"]).status_code == 201
    assert agent(client, subs["ana"]).get(KEY).status_code == 200
    assert agent(client, subs["owner"]).get(KEY).status_code == 401  # the owner granted nothing
    assert agent(client, subs["ana"], "agent-client-2").get(KEY).status_code == 401

    with superuser.begin() as conn:  # ana is demoted; leo's grant runs out
        conn.execute(
            text(
                "UPDATE memberships SET role = 'member' WHERE organization_id = :o AND user_id ="
                " (SELECT id FROM users WHERE cognito_sub = :s)"
            ),
            {"o": org, "s": subs["ana"]},
        )
        conn.execute(
            text(
                "UPDATE api_tokens SET created_at = :then, expires_at = :past WHERE"
                " organization_id = :o AND created_by ="
                " (SELECT id FROM users WHERE cognito_sub = :s)"
            ),
            {
                "o": org,
                "s": subs["leo"],
                "then": datetime.now(UTC) - timedelta(days=2),
                "past": datetime.now(UTC) - timedelta(days=1),
            },
        )
    assert agent(client, subs["ana"]).get(KEY).status_code == 401
    assert agent(client, subs["leo"]).get(KEY).status_code == 401
    # An expired grant no longer blocks a new one.
    assert grant(client, org, subs["leo"]).status_code == 201
    assert agent(client, subs["leo"]).get(KEY).status_code == 200


def test_the_same_person_and_client_in_two_organizations_is_refused_until_one_is_revoked(
    oauth_on: TestClient, superuser: Engine
) -> None:
    client = oauth_on
    first, subs = org_with(client, superuser)
    ana = subs["owner"]
    second = client.post("/api/v1/orgs", json={"name": "Otra"}, headers=auth(ana)).json()["id"]
    one = grant(client, first, ana)
    two = grant(client, second, ana)
    assert (one.status_code, two.status_code) == (201, 201)
    assert agent(client, ana).get(KEY).status_code == 401  # which organization is not decided
    client.delete(f"/api/v1/orgs/{second}/api-tokens/{two.json()['id']}", headers=auth(ana))
    assert agent(client, ana).get(KEY).status_code == 200
    assert agent(client, ana).get(KEY).json()["prefix"] == one.json()["prefix"]


def test_an_oauth_token_and_the_hand_off_header_open_nothing_from_outside(
    oauth_on: TestClient, superuser: Engine
) -> None:
    client = oauth_on
    org, subs = org_with(client, superuser)
    assert grant(client, org, subs["owner"]).status_code == 201
    digest = grant_digest(ISSUER, CLIENT_ID, subs["owner"])
    token = agent_token(subs["owner"])
    assert client.get(KEY, headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get(KEY, headers={"X-Atesta-Agent": digest}).status_code == 401
    # A key's secret never matches a grant: the digest is not a usable key either.
    assert client.get(KEY, headers={"Authorization": f"Bearer atesta_{digest}"}).status_code == 401


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def remote(oauth_on: TestClient, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("ATESTA_MCP_REMOTE", "1")
    monkeypatch.setenv("ATESTA_MCP_ALLOWED_HOSTS", "testserver")
    app = create_app()
    app.state._state.update(oauth_on.app.state._state)  # type: ignore[attr-defined]  # noqa: SLF001  # the fixture's fakes
    return app


@pytest.mark.anyio
async def test_the_hosted_server_challenges_then_serves_a_verified_agent(
    oauth_on: TestClient, superuser: Engine, remote: FastAPI
) -> None:
    client = oauth_on
    org, subs = org_with(client, superuser)
    created = grant(client, org, subs["owner"])
    assert created.status_code == 201
    transport = httpx2.ASGITransport(app=remote)
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    async with remote.state.mcp_session_manager():
        async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as bare:
            nothing = await bare.post("/mcp/", json=ping)
            forged = await bare.post(
                "/mcp/",
                json=ping,
                headers={"Authorization": "Bearer agent.unknown-client.sub-x"},
            )
            smuggled = await bare.post(
                "/mcp/",
                json=ping,
                headers={"X-Atesta-Agent": grant_digest(ISSUER, CLIENT_ID, subs["owner"])},
            )
        for refused in (nothing, forged, smuggled):
            assert refused.status_code == 401
            assert refused.headers["www-authenticate"] == OAUTH.challenge()
        http = httpx2.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={
                "Authorization": f"Bearer {agent_token(subs['owner'])}",
                "X-Atesta-Agent": "0" * 64,  # ignored: the gate strips it before verifying
            },
        )
        async with Client(streamable_http_client("http://testserver/mcp/", http_client=http)) as s:
            body = framed(await s.call_tool("get_key", {}))
    assert created.json()["prefix"] in body and "compliance:read" in body
