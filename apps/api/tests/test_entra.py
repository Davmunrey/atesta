"""Entra sign-in for M365 onboarding (#314): ID token checks against a fake Microsoft, no network.

Tokens are signed here with a throwaway RSA key, served from a fake JWKS endpoint.
"""

import json
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from atesta_api.modules.connections.entra import (
    AUTHORITY,
    EntraSettings,
    EntraSignIn,
    MicrosoftUnavailableError,
    SignInError,
)
from cryptography.hazmat.primitives.asymmetric import rsa

TENANT = "11111111-2222-4333-8444-555555555555"
OID = "66666666-7777-4888-8999-aaaaaaaaaaaa"
CLIENT = "signin-client-id"
SECRET = "x" * 24  # no entropy: never looks like a real secret to the scanner
NONCE = "synthetic-nonce"
SETTINGS = EntraSettings(CLIENT, SECRET, "scanner-client-id", "https://app.example.com")
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks() -> dict[str, Any]:
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
    return {"keys": [{**public, "kid": "k1", "use": "sig", "alg": "RS256"}]}


def token(key: Any = KEY, kid: str = "k1", **overrides: Any) -> str:
    now = int(time.time())
    claims = {
        "aud": CLIENT,
        "iss": f"{AUTHORITY}/{TENANT}/v2.0",
        "iat": now,
        "exp": now + 600,
        "tid": TENANT,
        "oid": OID,
        "sub": "pairwise-subject",
        "nonce": NONCE,
        **overrides,
    }
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


class FakeMicrosoft:
    def __init__(self, id_token: str = "", status: int = 200) -> None:
        self.id_token, self.status = id_token, status
        self.token_requests: list[dict[str, list[str]]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/discovery/v2.0/keys"):
            return httpx.Response(200, json=jwks())
        self.token_requests.append(parse_qs(request.content.decode()))
        return httpx.Response(self.status, json={"id_token": self.id_token})


def entra(fake: FakeMicrosoft) -> EntraSignIn:
    return EntraSignIn(SETTINGS, httpx.Client(transport=httpx.MockTransport(fake.handle)))


def test_a_valid_sign_in_binds_the_tenant_and_the_admin_object_id() -> None:
    fake = FakeMicrosoft(token())
    signed_in = entra(fake).sign_in(code="the-code", verifier="the-verifier", nonce=NONCE)
    assert (signed_in.tenant_id, signed_in.object_id) == (TENANT, OID)
    form = fake.token_requests[0]
    assert form["client_secret"] == [SECRET] and form["code_verifier"] == ["the-verifier"]
    assert form["redirect_uri"] == ["https://app.example.com/auth/m365/signin-callback"]
    assert form["grant_type"] == ["authorization_code"] and form["scope"] == ["openid profile"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"oid": None},  # an ID token without oid cannot bind an admin
        {"tid": None},
        {"aud": "another-app"},
        {"nonce": "replayed-nonce"},
        {"iss": f"{AUTHORITY}/{uuid.uuid4()}/v2.0"},  # issued for another tenant
        {"exp": int(time.time()) - 3600},
        {"oid": "not-a-guid"},
    ],
)
def test_an_id_token_that_fails_a_check_is_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(SignInError):
        entra(FakeMicrosoft(token(**overrides))).sign_in(code="c", verifier="v", nonce=NONCE)


def test_a_token_signed_with_another_key_is_refused() -> None:
    for forged in (token(key=OTHER_KEY), token(key=OTHER_KEY, kid="unknown")):
        with pytest.raises(SignInError):
            entra(FakeMicrosoft(forged)).sign_in(code="c", verifier="v", nonce=NONCE)


def test_a_refused_code_and_an_outage_are_told_apart() -> None:
    with pytest.raises(SignInError):
        entra(FakeMicrosoft(status=400)).sign_in(code="c", verifier="v", nonce=NONCE)
    with pytest.raises(MicrosoftUnavailableError):
        entra(FakeMicrosoft(status=503)).sign_in(code="c", verifier="v", nonce=NONCE)


def test_the_urls_use_pkce_the_organizations_endpoint_and_the_tenant_for_consent() -> None:
    client = entra(FakeMicrosoft())
    authorize = urlsplit(client.authorize_url(state="s", nonce="n", challenge="c"))
    query = parse_qs(authorize.query)
    assert authorize.path == "/organizations/oauth2/v2.0/authorize"
    assert query["code_challenge_method"] == ["S256"] and query["scope"] == ["openid profile"]
    assert query["client_id"] == [CLIENT] and "client_secret" not in query
    consent = urlsplit(client.consent_url(tenant_id=TENANT, state="s2"))
    assert consent.path == f"/{TENANT}/adminconsent"
    assert parse_qs(consent.query)["client_id"] == ["scanner-client-id"]
    assert parse_qs(consent.query)["redirect_uri"] == [
        "https://app.example.com/auth/m365/consent-callback"
    ]


def test_settings_are_optional_and_never_show_the_secret() -> None:
    assert EntraSettings.from_env({"ATESTA_WEB_BASE_URL": "https://x"}) is None
    assert SECRET not in repr(SETTINGS)
