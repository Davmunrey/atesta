"""The real Cognito client code against the local fake (local-dev-auth spec)."""

import base64
import hashlib
import importlib
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from atesta_api.modules.identity.cognito import (
    CognitoOAuth,
    CognitoSettings,
    CognitoUserInfo,
    InvalidTokenError,
    TokenVerifier,
    jwks_fetcher,
)
from fastapi.testclient import TestClient

BASE = "http://localhost:9000"
WEB = "http://localhost:3000"
ENV = {
    "ATESTA_COGNITO_REGION": "eu-south-2",
    "ATESTA_COGNITO_USER_POOL_ID": "local",
    "ATESTA_COGNITO_APP_CLIENT_ID": "local-web",
    "ATESTA_COGNITO_DOMAIN": "localhost:9000",
    "ATESTA_COGNITO_ISSUER": BASE,
    "ATESTA_COGNITO_BASE_URL": BASE,
}


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ATESTA_ENV", "test")  # the overrides are honoured in development only
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    module: Any = importlib.import_module("devtools.fake_cognito")
    return TestClient(module.create_app(issuer=BASE, client_id="local-web"), base_url=BASE)


def challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


def sign_in(fake: TestClient, oauth: CognitoOAuth, email: str, verifier: str) -> str:
    url = oauth.authorize_url(state="st", nonce="nn", challenge=challenge(verifier), lang="es")
    page = fake.get(url)
    assert page.status_code == 200 and 'name="code"' in page.text  # TOTP stand-in field
    form = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    done = fake.post(
        "/login", data={**form, "email": email, "code": "123456"}, follow_redirects=False
    )
    target = urlsplit(done.headers["location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == f"{WEB}/auth/callback"
    query = parse_qs(target.query)
    assert query["state"] == ["st"]
    return query["code"][0]


def test_full_sign_in_refresh_and_userinfo(fake: TestClient) -> None:
    settings = CognitoSettings.from_env()
    verifier = TokenVerifier(settings, jwks_fetcher(settings, fake))
    oauth = CognitoOAuth(settings, fake, verifier, WEB)
    code = sign_in(fake, oauth, "Ana@Example.com", "v" * 50)
    tokens = oauth.exchange_code(code, "v" * 50)
    sub = verifier.verify(tokens.access_token).sub
    assert oauth.id_token_nonce(tokens.id_token or "") == "nn"
    info = CognitoUserInfo(settings, fake).userinfo(tokens.access_token)
    assert (info.sub, info.email, info.email_verified) == (sub, "ana@example.com", True)
    assert verifier.verify(oauth.refresh(tokens.refresh_token or "").access_token).sub == sub
    with pytest.raises(InvalidTokenError):
        oauth.exchange_code(code, "v" * 50)  # codes are single use


def test_a_revoked_refresh_token_no_longer_refreshes(fake: TestClient) -> None:
    """The fake revokes like Cognito, so e2e sign-out exercises revocation (#324)."""
    settings = CognitoSettings.from_env()
    oauth = CognitoOAuth(settings, fake, TokenVerifier(settings, jwks_fetcher(settings, fake)), WEB)
    tokens = oauth.exchange_code(sign_in(fake, oauth, "ana@example.com", "v" * 50), "v" * 50)
    refresh_token = tokens.refresh_token or ""
    oauth.revoke(refresh_token)
    oauth.revoke(refresh_token)  # already revoked: still 200, like Cognito
    with pytest.raises(InvalidTokenError):
        oauth.refresh(refresh_token)


def test_pkce_mismatch_is_refused(fake: TestClient) -> None:
    settings = CognitoSettings.from_env()
    oauth = CognitoOAuth(settings, fake, TokenVerifier(settings, jwks_fetcher(settings, fake)), WEB)
    code = sign_in(fake, oauth, "ana@example.com", "v" * 50)
    with pytest.raises(InvalidTokenError):
        oauth.exchange_code(code, "w" * 50)


@pytest.mark.parametrize("env", [None, "", "prod", "production", "staging"])
def test_overrides_are_refused_outside_development(
    monkeypatch: pytest.MonkeyPatch, env: str | None
) -> None:
    """Fails closed: an unset or unknown ATESTA_ENV must not trust a substitute issuer."""
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    if env is None:
        monkeypatch.delenv("ATESTA_ENV", raising=False)
    else:
        monkeypatch.setenv("ATESTA_ENV", env)
    with pytest.raises(RuntimeError, match="override"):
        CognitoSettings.from_env()
    monkeypatch.delenv("ATESTA_COGNITO_BASE_URL")
    with pytest.raises(RuntimeError, match="override"):  # either override alone is refused
        CognitoSettings.from_env()
    monkeypatch.delenv("ATESTA_COGNITO_ISSUER")
    assert CognitoSettings.from_env().issuer.startswith("https://cognito-idp.eu-south-2.")


@pytest.mark.parametrize("env", ["local", "dev", "test"])
def test_overrides_are_honoured_in_development(monkeypatch: pytest.MonkeyPatch, env: str) -> None:
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ATESTA_ENV", env)
    settings = CognitoSettings.from_env()
    assert (settings.issuer, settings.base_url) == (BASE, BASE)
