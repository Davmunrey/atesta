"""The staff session (operator-portal spec, "Session cookie" and "Session limits"; ADR-017):
strict host-only cookies with their own key and names, the origin check on writes, and the
30-minute idle and 8-hour total limits. Real staff tokens; the staff pool's endpoints are faked.
"""

import json
import time
from collections.abc import Iterator
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

import pytest
from atesta_api.modules.identity.api import InvalidTokenError, SessionCrypto, TokenSet
from atesta_operator.auth import CurrentStaff
from atesta_operator.session import (
    ACCESS_COOKIE,
    LOGIN_COOKIE,
    REFRESH_COOKIE,
    SESSION_COOKIES,
    TIMES_COOKIE,
)
from fastapi.testclient import TestClient

from .conftest import Issuer, MakeStaff

PORTAL = "https://admin.example.test"
JAR = {"domain": "testserver.local", "path": "/"}  # where the test client keeps the app's cookies
KEY = bytes(range(64, 96))


class FakeStaffOAuth:
    """The staff pool's managed login, recorded: codes are `code-<sub>`, refresh `rt-<sub>`."""

    def __init__(self, pool: Issuer) -> None:
        self.pool, self.nonce, self.revoked, self.refreshed = pool, "", [], []

    def authorize_url(self, *, state: str, nonce: str, challenge: str, lang: str) -> str:
        self.nonce = nonce
        return f"https://staff-auth.example.test/oauth2/authorize?state={state}&lang={lang}"

    def exchange_code(self, code: str, verifier: str) -> TokenSet:
        sub = code.removeprefix("code-")
        return TokenSet(self.pool.token(sub), f"rt-{sub}", "id-token")

    def id_token_nonce(self, id_token: str) -> str:
        return self.nonce

    def refresh(self, refresh_token: str) -> TokenSet:
        self.refreshed.append(refresh_token)
        if refresh_token in self.revoked:
            raise InvalidTokenError
        return TokenSet(self.pool.token(refresh_token.removeprefix("rt-")), None, None)

    def revoke(self, refresh_token: str) -> None:
        self.revoked.append(refresh_token)

    def logout_url(self) -> str:
        return "https://staff-auth.example.test/logout"


@pytest.fixture
def oauth(client: TestClient, staff_pool: Issuer) -> Iterator[FakeStaffOAuth]:
    fake = FakeStaffOAuth(staff_pool)
    state = client.app.state  # type: ignore[attr-defined]
    state.oauth, state.web_origin, state.session_crypto = fake, PORTAL, SessionCrypto(KEY)
    yield fake


def sign_in(client: TestClient, sub: str) -> None:
    login = client.get(
        "/auth/login", params={"return_to": "/organizations"}, follow_redirects=False
    )
    state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
    done = client.get(
        "/auth/callback", params={"code": f"code-{sub}", "state": state}, follow_redirects=False
    )
    assert done.status_code == 302 and done.headers["location"] == "/organizations"


def set_cookies(response_headers: list[str]) -> dict[str, str]:
    """name -> the raw Set-Cookie header, lower-cased attributes."""
    found = {}
    for header in response_headers:
        name = header.split("=", 1)[0]
        found[name] = header.lower()
    return found


def test_sign_in_sets_strict_host_only_cookies_of_its_own(
    client: TestClient, oauth: FakeStaffOAuth, make_staff: MakeStaff
) -> None:
    login = client.get("/auth/login", follow_redirects=False)
    pending = set_cookies(login.headers.get_list("set-cookie"))[LOGIN_COOKIE]
    assert "samesite=lax" in pending and "path=/auth" in pending and "httponly" in pending
    state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
    sub = make_staff("support")
    done = client.get(
        "/auth/callback", params={"code": f"code-{sub}", "state": state}, follow_redirects=False
    )
    assert done.headers["location"] == "/"
    cookies = set_cookies(done.headers.get_list("set-cookie"))
    assert set(SESSION_COOKIES) <= set(cookies)
    for name in SESSION_COOKIES:
        header = cookies[name]
        assert "samesite=strict" in header and "httponly" in header and "secure" in header
        assert "domain=" not in header and "path=/" in header
        assert int(SimpleCookie(header)[name]["max-age"]) <= 8 * 3600
    assert not set(cookies) & {"atesta_at", "atesta_rt", "atesta_auth"}  # not the console's
    assert client.get("/api/v1/me").json()["role"] == "support"


def test_a_cookie_sealed_with_the_console_key_does_not_open(
    client: TestClient, oauth: FakeStaffOAuth, make_staff: MakeStaff, staff_pool: Issuer
) -> None:
    console = SessionCrypto(bytes(range(32)))
    times = json.dumps({"started": time.time(), "seen": time.time()})
    client.cookies.set(
        ACCESS_COOKIE, console.seal(ACCESS_COOKIE, staff_pool.token(make_staff("admin")))
    )
    client.cookies.set(TIMES_COOKIE, console.seal(TIMES_COOKIE, times))
    assert client.get("/api/v1/me").status_code == 401


def test_a_bad_state_is_refused(client: TestClient, oauth: FakeStaffOAuth) -> None:
    client.get("/auth/login", follow_redirects=False)
    done = client.get("/auth/callback", params={"code": "code-x", "state": "forged"})
    assert done.status_code == 400 and done.json() == {"detail": {"code": "auth.bad_state"}}


def test_a_write_without_the_portal_origin_is_403(
    client: TestClient, oauth: FakeStaffOAuth, make_staff: MakeStaff
) -> None:
    def write(staff: CurrentStaff) -> None:
        return None

    client.app.add_api_route("/api/v1/probe-write", write, methods=["POST"])  # type: ignore[attr-defined]
    sign_in(client, make_staff("admin"))
    assert client.post("/api/v1/probe-write").json() == {"detail": {"code": "auth.bad_origin"}}
    foreign = client.post("/api/v1/probe-write", headers={"origin": "https://app.example.test"})
    assert foreign.status_code == 403 and foreign.json()["detail"]["code"] == "auth.bad_origin"
    # Past the origin check, the unlisted route is refused by the matrix instead.
    own = client.post("/api/v1/probe-write", headers={"origin": PORTAL})
    assert own.json() == {"detail": {"code": "operator.forbidden"}}


def _times(client: TestClient, started: float, seen: float) -> None:
    sealed = SessionCrypto(KEY).seal(TIMES_COOKIE, json.dumps({"started": started, "seen": seen}))
    client.cookies.set(TIMES_COOKIE, sealed, **JAR)


@pytest.mark.parametrize(
    ("started_ago", "seen_ago"),
    [(10 * 60, 31 * 60), (8 * 3600 + 5, 60)],
    ids=["idle 31 minutes", "8 hours total"],
)
def test_a_session_ends_when_idle_or_too_old(
    client: TestClient,
    oauth: FakeStaffOAuth,
    make_staff: MakeStaff,
    started_ago: int,
    seen_ago: int,
) -> None:
    sign_in(client, make_staff("admin"))
    now = time.time()
    _times(client, now - started_ago, now - seen_ago)
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "auth.invalid_token"}}
    cleared = set_cookies(response.headers.get_list("set-cookie"))
    assert set(SESSION_COOKIES) <= set(cleared)
    assert all("max-age=0" in cleared[name] for name in SESSION_COOKIES)


def test_each_request_moves_last_used(
    client: TestClient, oauth: FakeStaffOAuth, make_staff: MakeStaff
) -> None:
    sign_in(client, make_staff("billing"))
    now = time.time()
    _times(client, now - 3600, now - 29 * 60)
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    sealed = client.cookies.get(TIMES_COOKIE, **JAR)
    assert sealed is not None
    times = json.loads(SessionCrypto(KEY).open(TIMES_COOKIE, sealed))
    assert times["seen"] >= now and abs(times["started"] - (now - 3600)) < 1


def test_an_expired_access_token_is_refreshed_once(
    client: TestClient, oauth: FakeStaffOAuth, make_staff: MakeStaff, staff_pool: Issuer
) -> None:
    sub = make_staff("admin")
    sign_in(client, sub)
    expired = staff_pool.token(sub, exp=int(time.time()) - 300)
    client.cookies.set(ACCESS_COOKIE, SessionCrypto(KEY).seal(ACCESS_COOKIE, expired), **JAR)
    assert client.get("/api/v1/me").status_code == 200
    assert oauth.refreshed == [f"rt-{sub}"]


def test_sign_out_revokes_the_refresh_token_and_clears_the_session(
    client: TestClient, oauth: FakeStaffOAuth, make_staff: MakeStaff
) -> None:
    sub = make_staff("admin")
    sign_in(client, sub)
    out = client.get("/auth/logout", follow_redirects=False)
    assert out.headers["location"] == "https://staff-auth.example.test/logout"
    assert oauth.revoked == [f"rt-{sub}"]
    assert REFRESH_COOKIE in set_cookies(out.headers.get_list("set-cookie"))
    assert client.get("/api/v1/me").status_code == 401
