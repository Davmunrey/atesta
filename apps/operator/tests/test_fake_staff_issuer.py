"""The local fake staff pool (apps/api/devtools/fake_cognito.py --staff): its tokens pass the
operator's token check with `auth_time` kept across a refresh, and the customer fake's do not."""

import base64
import hashlib
import importlib
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from atesta_api.modules.identity.api import (
    AccessToken,
    CognitoSettings,
    InvalidTokenError,
    TokenVerifier,
)
from fastapi.testclient import TestClient

API = Path(__file__).resolve().parents[2] / "api"
STAFF = "http://localhost:9001"
PORTAL = "http://localhost:3001"


def fake(issuer: str, client_id: str) -> TestClient:
    sys.path.insert(0, str(API))
    try:
        module: Any = importlib.import_module("devtools.fake_cognito")
    finally:
        sys.path.remove(str(API))
    return TestClient(module.create_app(issuer=issuer, client_id=client_id), base_url=issuer)


def settings(issuer: str, client_id: str) -> CognitoSettings:
    return CognitoSettings("eu-south-2", "local", client_id, "localhost", issuer, issuer)


def sign_in(client: TestClient, client_id: str) -> dict[str, Any]:
    verifier = "v" * 64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    form = {
        "client_id": client_id,
        "redirect_uri": f"{PORTAL}/auth/callback",
        "state": "st",
        "nonce": "nn",
        "code_challenge": challenge.rstrip(b"=").decode(),
    }
    done = client.post(
        "/login",
        data={**form, "email": "admin@atesta.test", "code": "123456"},
        follow_redirects=False,
    )
    code = parse_qs(urlsplit(done.headers["location"]).query)["code"][0]
    response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": f"{PORTAL}/auth/callback",
            "code_verifier": verifier,
        },
    )
    body: dict[str, Any] = response.json()
    return body


def verify(client: TestClient, issuer: str, client_id: str, token: str) -> AccessToken:
    return TokenVerifier(
        settings(issuer, client_id), lambda: client.get("/.well-known/jwks.json").json()
    ).verify(token)


def test_a_staff_fake_token_carries_auth_time_and_keeps_it_on_refresh() -> None:
    staff = fake(STAFF, "local-operator")
    tokens = sign_in(staff, "local-operator")
    first = verify(staff, STAFF, "local-operator", tokens["access_token"])
    assert first.auth_time is not None
    refreshed = staff.post(
        "/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "client_id": "local-operator",
            "refresh_token": tokens["refresh_token"],
        },
    ).json()
    again = verify(staff, STAFF, "local-operator", refreshed["access_token"])
    assert again.auth_time == first.auth_time and again.sub == first.sub


def test_a_customer_fake_token_is_refused_by_the_staff_check() -> None:
    customer = fake("http://localhost:9000", "local-web")
    staff = fake(STAFF, "local-operator")
    token = sign_in(customer, "local-web")["access_token"]
    with pytest.raises(InvalidTokenError):
        verify(staff, STAFF, "local-operator", token)


def test_the_portal_e2e_seed_derives_staff_subjects_as_the_fake_does() -> None:
    """prepare_e2e_db.py --operator seeds staff rows the fake staff pool signs in (#487)."""
    sys.path.insert(0, str(API))
    try:
        seed: Any = importlib.import_module("devtools.prepare_e2e_db")
        issuer: Any = importlib.import_module("devtools.fake_cognito")
    finally:
        sys.path.remove(str(API))
    assert seed._SUB_NAMESPACE == issuer._SUB_NAMESPACE
    assert "admin@atesta.test" in seed.STAFF
