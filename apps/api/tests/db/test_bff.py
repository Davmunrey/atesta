"""BFF: sign-in, sealed session cookies, refresh and Origin check (web-shell spec)."""

import base64
import hashlib
import json
import logging
from urllib.parse import parse_qs, urlsplit

import pytest
from atesta_api.modules.identity.bff import (
    ACCESS_COOKIE,
    AUTH_COOKIE,
    REFRESH_COOKIE,
    SessionCrypto,
)
from fastapi.testclient import TestClient

from .conftest import SESSION_KEY, WEB_ORIGIN, FakeOAuth, new_sub

CRYPTO = SessionCrypto(SESSION_KEY)


def login(client: TestClient, query: str = "") -> tuple[dict[str, str], dict[str, str]]:
    """Start sign-in; return the authorize URL query and the decrypted pending-login state."""
    response = client.get(f"/auth/login{query}", follow_redirects=False)
    assert response.status_code == 302
    params = {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}
    state = json.loads(CRYPTO.open(AUTH_COOKIE, response.cookies[AUTH_COOKIE]))
    return params, state


def signed_in(client: TestClient, sub: str) -> TestClient:
    params, _ = login(client)
    response = client.get(
        f"/auth/callback?code=code-{sub}&state={params['state']}", follow_redirects=False
    )
    assert response.status_code == 302, response.text
    return client


def test_login_uses_pkce_s256_and_a_short_lived_state_cookie(client: TestClient) -> None:
    response = client.get("/auth/login?lang=en", follow_redirects=False)
    cookie = response.headers["set-cookie"]
    assert all(flag in cookie for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/auth"))
    params, state = login(client, "?lang=en")
    digest = hashlib.sha256(state["verifier"].encode()).digest()
    assert params["code_challenge"] == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert params["state"] == state["state"]
    assert params["lang"] == "en"
    assert len(state["verifier"]) >= 43


@pytest.mark.parametrize("target", ["//evil.example", "https://evil.example/x", "/\\evil"])
def test_login_refuses_open_redirects(client: TestClient, target: str) -> None:
    _, state = login(client, f"?return_to={target}")
    assert state["return_to"] == "/app"


@pytest.mark.parametrize(
    "target",
    [
        "/\t/evil.example",  # a browser strips tab, LF and CR: //evil.example (#325)
        "/\n/evil.example",
        "/\r/evil.example",
        "\t//evil.example",
        "/ /evil.example",
        "/\x00/evil.example",
        "/\x7f/evil.example",
        "/app\t",
    ],
)
def test_login_refuses_control_characters_and_whitespace_in_the_return_path(
    client: TestClient, target: str
) -> None:
    """Safe by our own check, not only by the framework percent-encoding the Location header."""
    response = client.get("/auth/login", params={"return_to": target}, follow_redirects=False)
    state = json.loads(CRYPTO.open(AUTH_COOKIE, response.cookies[AUTH_COOKIE]))
    assert state["return_to"] == "/app"


def test_login_defaults_to_spanish(client: TestClient) -> None:
    params, _ = login(client)
    assert params["lang"] == "es"


def test_callback_rejects_missing_or_wrong_state(client: TestClient) -> None:
    assert client.get("/auth/callback?code=code-x&state=s").json()["detail"]["code"] == (
        "auth.bad_state"
    )
    login(client)
    wrong = client.get("/auth/callback?code=code-x&state=forged")
    assert (wrong.status_code, wrong.json()["detail"]["code"]) == (400, "auth.bad_state")


def test_callback_rejects_a_mismatched_nonce(client: TestClient) -> None:
    params, _ = login(client)
    response = client.get(f"/auth/callback?code=code-badnonce&state={params['state']}")
    assert (response.status_code, response.json()["detail"]["code"]) == (400, "auth.bad_nonce")


def test_callback_stores_tokens_only_in_encrypted_cookies(
    client: TestClient, oauth: FakeOAuth
) -> None:
    sub = new_sub()
    params, state = login(client, "?return_to=/app/orgs")
    response = client.get(
        f"/auth/callback?code=code-{sub}&state={params['state']}", follow_redirects=False
    )
    assert response.headers["location"] == "/app/orgs"
    assert oauth.exchanged == [(f"code-{sub}", state["verifier"])]
    raw = "\n".join(response.headers.get_list("set-cookie"))
    assert f"tok-{sub}" not in raw and f"rt-{sub}" not in raw
    assert CRYPTO.open(ACCESS_COOKIE, response.cookies[ACCESS_COOKIE]) == f"tok-{sub}"
    assert CRYPTO.open(REFRESH_COOKIE, response.cookies[REFRESH_COOKIE]) == f"rt-{sub}"
    assert f'{AUTH_COOKIE}=""' in raw  # pending-login cookie cleared


def test_cookie_and_bearer_reach_the_same_user(client: TestClient) -> None:
    sub = new_sub()
    by_bearer = client.get("/api/v1/me", headers={"Authorization": f"Bearer tok-{sub}"}).json()
    by_cookie = signed_in(client, sub).get("/api/v1/me").json()
    assert by_cookie["id"] == by_bearer["id"]


def test_tampered_or_swapped_cookie_is_rejected(client: TestClient) -> None:
    sub = new_sub()
    signed_in(client, sub)
    refresh_value = client.cookies[REFRESH_COOKIE]
    client.cookies.set(ACCESS_COOKIE, refresh_value)  # sealed for another cookie name
    client.cookies.delete(REFRESH_COOKIE)
    assert client.get("/api/v1/me").status_code == 401


def test_expired_access_token_is_refreshed_once(client: TestClient, oauth: FakeOAuth) -> None:
    sub = new_sub()
    signed_in(client, sub)
    client.cookies.set(ACCESS_COOKIE, CRYPTO.seal(ACCESS_COOKIE, f"expired-{sub}"))
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    assert oauth.refreshed == [f"rt-{sub}"]
    assert CRYPTO.open(ACCESS_COOKIE, response.cookies[ACCESS_COOKIE]) == f"tok-{sub}"


def test_failed_refresh_clears_the_session(client: TestClient) -> None:
    sub = new_sub()
    signed_in(client, sub)
    client.cookies.set(ACCESS_COOKIE, CRYPTO.seal(ACCESS_COOKIE, f"expired-{sub}"))
    client.cookies.set(REFRESH_COOKIE, CRYPTO.seal(REFRESH_COOKIE, "revoked"))
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert f'{ACCESS_COOKIE}=""' in "\n".join(response.headers.get_list("set-cookie"))


def test_cookie_writes_need_the_web_origin(client: TestClient) -> None:
    signed_in(client, new_sub())
    body = {"name": "Acme"}
    cross = client.post("/api/v1/orgs", json=body, headers={"Origin": "https://evil.example"})
    missing = client.post("/api/v1/orgs", json=body)
    same = client.post("/api/v1/orgs", json=body, headers={"Origin": WEB_ORIGIN})
    assert [r.status_code for r in (cross, missing, same)] == [403, 403, 201]
    assert cross.json()["detail"]["code"] == "auth.bad_origin"


def test_bearer_writes_need_no_origin(client: TestClient) -> None:
    response = client.post(
        "/api/v1/orgs", json={"name": "Cli"}, headers={"Authorization": f"Bearer tok-{new_sub()}"}
    )
    assert response.status_code == 201


def test_logout_clears_cookies_and_ends_the_cognito_session(client: TestClient) -> None:
    signed_in(client, new_sub())
    response = client.get("/auth/logout", follow_redirects=False)
    raw = "\n".join(response.headers.get_list("set-cookie"))
    assert f'{ACCESS_COOKIE}=""' in raw and f'{REFRESH_COOKIE}=""' in raw
    assert response.headers["location"].startswith("https://auth.example.com/logout?client_id=")


def test_logout_revokes_the_refresh_token_so_a_copied_session_ends(
    client: TestClient, oauth: FakeOAuth
) -> None:
    """Cognito's /logout revokes no token; /oauth2/revoke does (#324)."""
    sub = new_sub()
    signed_in(client, sub)
    copied = client.cookies.get(REFRESH_COOKIE)  # e.g. lifted from a shared machine
    response = client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert oauth.revoked == [f"rt-{sub}"]
    client.cookies.clear()
    client.cookies.set(ACCESS_COOKIE, CRYPTO.seal(ACCESS_COOKIE, f"expired-{sub}"))
    client.cookies.set(REFRESH_COOKIE, copied or "")
    assert client.get("/api/v1/me").status_code == 401  # the copy no longer refreshes


def test_logout_still_signs_out_when_revocation_fails(
    client: TestClient, oauth: FakeOAuth, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    sub = new_sub()
    signed_in(client, sub)
    oauth.revoke_fails = True
    response = client.get("/auth/logout", follow_redirects=False)
    raw = "\n".join(response.headers.get_list("set-cookie"))
    assert response.status_code == 302 and f'{REFRESH_COOKIE}=""' in raw
    assert f"rt-{sub}" not in caplog.text


def test_logout_without_a_session_revokes_nothing(client: TestClient, oauth: FakeOAuth) -> None:
    client.cookies.set(REFRESH_COOKIE, "not-a-sealed-value")
    response = client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 302 and oauth.revoked == []


def test_tokens_never_reach_logs(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    sub = new_sub()
    signed_in(client, sub)
    client.cookies.set(ACCESS_COOKIE, CRYPTO.seal(ACCESS_COOKIE, f"expired-{sub}"))
    client.get("/api/v1/me")
    assert f"tok-{sub}" not in caplog.text and f"rt-{sub}" not in caplog.text


def test_session_crypto_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        SessionCrypto(b"short")
    with pytest.raises(Exception, match="invalid"):
        CRYPTO.open(ACCESS_COOKIE, "not-base64!")


def test_sealed_value_opens_only_under_its_own_cookie_name() -> None:
    sealed = CRYPTO.seal(REFRESH_COOKIE, "rt-x")
    assert CRYPTO.open(REFRESH_COOKIE, sealed) == "rt-x"
    with pytest.raises(Exception, match="invalid"):
        CRYPTO.open(ACCESS_COOKIE, sealed)
