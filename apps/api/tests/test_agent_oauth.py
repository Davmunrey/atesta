"""OAuth for the hosted MCP server (mcp-oauth spec, issue 354): settings, the Protected
Resource Metadata and the token rules, with tokens signed by a throwaway key. No network."""

import json
import time
from typing import Any

import jwt
import pytest
from atesta_api.modules.identity.agent_oauth import AgentOAuth, grant_digest
from atesta_api.modules.identity.cognito import (
    CognitoSettings,
    ExpiredTokenError,
    InvalidTokenError,
    TokenVerifier,
)
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://cognito-idp.eu-south-2.amazonaws.com/eu-south-2_test"
RESOURCE = "https://app.example.com/mcp"
WEB_CLIENT = "web-client"
AGENT_CLIENT = "agent-client-1"
ENV = {
    "ATESTA_MCP_REMOTE": "1",
    "ATESTA_MCP_RESOURCE_URL": RESOURCE,
    "ATESTA_MCP_OAUTH_CLIENTS": f"{AGENT_CLIENT}=Agente Uno, other-client=Otro agente",
}
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SETTINGS = CognitoSettings("eu-south-2", "eu-south-2_test", WEB_CLIENT, "auth.example.com", ISSUER)


def oauth() -> AgentOAuth:
    found = AgentOAuth.from_env(ENV, ISSUER)
    assert found is not None
    return found


def verifier() -> TokenVerifier:
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
    return TokenVerifier(SETTINGS, lambda: {"keys": [{**public, "kid": "k1", "alg": "RS256"}]})


def token(key: Any = KEY, **overrides: Any) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": "person-1",
        "aud": RESOURCE,
        "client_id": AGENT_CLIENT,
        "token_use": "access",
        "scope": f"openid {RESOURCE}/agent",
        "iat": now,
        "exp": now + 600,
        **overrides,
    }
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def test_oauth_is_off_unless_the_server_the_resource_and_a_client_are_set() -> None:
    assert AgentOAuth.from_env({}, ISSUER) is None
    for missing in ENV:
        assert AgentOAuth.from_env({k: v for k, v in ENV.items() if k != missing}, ISSUER) is None
    assert AgentOAuth.from_env({**ENV, "ATESTA_MCP_REMOTE": "0"}, ISSUER) is None
    on = oauth()
    assert on.resource == RESOURCE and on.scope == f"{RESOURCE}/agent"
    assert on.clients == {AGENT_CLIENT: "Agente Uno", "other-client": "Otro agente"}


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ATESTA_MCP_RESOURCE_URL", "http://app.example.com/mcp"),  # not https
        ("ATESTA_MCP_RESOURCE_URL", "https://app.example.com/mcp/"),  # trailing slash
        ("ATESTA_MCP_RESOURCE_URL", "https://app.example.com/mcp?x=1"),
        ("ATESTA_MCP_RESOURCE_URL", "https://app.example.com/mcp#f"),
        ("ATESTA_MCP_OAUTH_CLIENTS", "no-name"),
        ("ATESTA_MCP_OAUTH_CLIENTS", "id=Nombre, id=Otra vez"),
        ("ATESTA_MCP_OAUTH_CLIENTS", "bad id=Nombre"),
        ("ATESTA_MCP_OAUTH_CLIENTS", f"{WEB_CLIENT}=La web"),  # the web app's own client
    ],
)
def test_a_malformed_setting_stops_the_start(name: str, value: str) -> None:
    with pytest.raises(ValueError, match=name):
        AgentOAuth.from_env({**ENV, name: value}, ISSUER, web_client_id=WEB_CLIENT)


def test_the_metadata_names_the_resource_its_authorization_server_and_its_scope() -> None:
    assert oauth().metadata() == {
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": [f"{RESOURCE}/agent"],
        "bearer_methods_supported": ["header"],
        "resource_name": "Atesta",
    }
    assert oauth().challenge() == (
        'Bearer resource_metadata="https://app.example.com/.well-known/oauth-protected-resource/mcp",'
        f' scope="{RESOURCE}/agent"'
    )


def test_a_token_for_this_server_from_an_approved_client_is_accepted() -> None:
    found = verifier().verify_agent(token(), oauth())
    assert (found.sub, found.client_id) == ("person-1", AGENT_CLIENT)


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "https://other.example.com/mcp"},  # issued for another resource
        {"aud": None},  # a web session token carries no audience
        {"client_id": "unknown-client"},
        {"client_id": WEB_CLIENT},  # the web app is not an agent
        {"scope": "openid"},  # without the agent scope
        {"token_use": "id"},
        {"iss": "https://cognito-idp.eu-south-2.amazonaws.com/another-pool"},
        {"sub": None},
    ],
    ids=[
        "other-aud",
        "no-aud",
        "unknown-client",
        "web-client",
        "no-scope",
        "id-token",
        "iss",
        "sub",
    ],
)
def test_any_other_token_is_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(InvalidTokenError):
        verifier().verify_agent(token(**overrides), oauth())


def test_a_forged_and_an_expired_token_are_refused() -> None:
    with pytest.raises(InvalidTokenError):
        verifier().verify_agent(token(key=OTHER_KEY), oauth())
    with pytest.raises(ExpiredTokenError):
        verifier().verify_agent(token(exp=int(time.time()) - 3600), oauth())


def test_an_agent_token_is_not_a_web_session_and_a_session_is_not_an_agent_token() -> None:
    with pytest.raises(InvalidTokenError):
        verifier().verify(token())  # another client id
    session = token(aud=None, client_id=WEB_CLIENT, scope="openid")
    assert verifier().verify(session).sub == "person-1"
    with pytest.raises(InvalidTokenError):
        verifier().verify_agent(session, oauth())


def test_the_grant_digest_separates_issuer_client_and_person() -> None:
    base = grant_digest(ISSUER, AGENT_CLIENT, "person-1")
    assert len(base) == 64 and base == grant_digest(ISSUER, AGENT_CLIENT, "person-1")
    assert base != grant_digest(ISSUER, "other-client", "person-1")
    assert base != grant_digest(ISSUER, AGENT_CLIENT, "person-2")
    assert base != grant_digest(ISSUER + "x", AGENT_CLIENT, "person-1")
    # Fields cannot run into each other: "a" + "bc" is not "ab" + "c".
    assert grant_digest("i", "a", "bc") != grant_digest("i", "ab", "c")
