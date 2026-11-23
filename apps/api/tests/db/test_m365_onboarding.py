"""M365 onboarding steps 2 to 4 against a fake Microsoft (scanner-connectors spec, #314).

Test plan row "M365 onboarding with a fake identity provider": missing, expired or other-user
cookie; wrong state; a refused ID token; admin_consent not True; error present; tenant different
from the signed-in tid: each refused with its code; the happy path stores the tenant and the
consenting admin, once. The callbacks are browser navigations, so a refusal redirects to the web
connections page with its code (web-connections spec, #366).
"""

import logging
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from atesta_api.main import app
from atesta_api.modules.connections.entra import (
    MicrosoftUnavailableError,
    SignedIn,
    SignInError,
)
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth
from .test_connections_http import create
from .test_members import events, org_with

TENANT = "11111111-2222-4333-8444-555555555555"
OID = "66666666-7777-4888-8999-aaaaaaaaaaaa"
CODE = "synthetic-authorization-code"


class FakeMicrosoft:
    """Codes: CODE signs in to TENANT; 'refused' fails the ID token checks; 'down' is an outage."""

    def __init__(self) -> None:
        self.sign_ins: list[dict[str, str]] = []

    def authorize_url(self, *, state: str, nonce: str, challenge: str) -> str:
        return f"https://login.example/authorize?state={state}&code_challenge={challenge}"

    def sign_in(self, *, code: str, verifier: str, nonce: str) -> SignedIn:
        self.sign_ins.append({"code": code, "verifier": verifier, "nonce": nonce})
        if code == "refused":
            raise SignInError("refused")
        if code == "down":
            raise MicrosoftUnavailableError
        return SignedIn(tenant_id=TENANT, object_id=OID)

    def consent_url(self, *, tenant_id: str, state: str) -> str:
        return f"https://login.example/{tenant_id}/adminconsent?state={state}"


@pytest.fixture
def microsoft(client: TestClient) -> Iterator[FakeMicrosoft]:
    fake = FakeMicrosoft()
    app.state.m365 = fake
    yield fake
    app.state.m365 = None


def state_of(url: str) -> str:
    return parse_qs(urlsplit(url).query)["state"][0]


def start(client: TestClient, org: str, sub: str, connection: object) -> str:
    response = client.post(
        f"/api/v1/orgs/{org}/connections/{connection}/m365/signin", headers=auth(sub)
    )
    assert response.status_code == 200, response.text
    return state_of(response.json()["authorize_url"])


def signin(client: TestClient, sub: str, state: str, code: str = CODE) -> Any:
    return client.get(
        "/auth/m365/signin-callback",
        params={"code": code, "state": state},
        headers=auth(sub),
        follow_redirects=False,
    )


def consent(client: TestClient, sub: str, state: str, **overrides: str) -> Any:
    params = {"state": state, "tenant": TENANT, "admin_consent": "True", **overrides}
    return client.get(
        "/auth/m365/consent-callback", params=params, headers=auth(sub), follow_redirects=False
    )


def code_of(response: Any) -> tuple[int, str]:
    return response.status_code, response.json()["detail"]["code"]


PAGE = "https://app.example.com/app/connections"


def refused(response: Any) -> dict[str, str]:
    """A callback refusal: 302 to the connections page, the cookie deleted; its query."""
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.split("?")[0] == PAGE
    cookie = response.headers.get("set-cookie", "")
    assert cookie.startswith("atesta_m365=") and "Max-Age=0" in cookie  # a retry starts afresh
    return {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}


def stored(superuser: Engine, connection: object) -> tuple[str | None, str | None]:
    with superuser.connect() as conn:
        row = conn.execute(
            text("SELECT ms_tenant_id, consented_by_oid FROM connections WHERE id = :c"),
            {"c": connection},
        ).one()
    return row.ms_tenant_id, row.consented_by_oid


def test_an_admin_signs_in_then_consents_and_the_tenant_is_bound_once(
    client: TestClient,
    superuser: Engine,
    microsoft: FakeMicrosoft,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    org, subs = org_with(client, superuser, adm="admin")
    made = create(client, org, subs["adm"])
    first_state = start(client, org, subs["adm"], made["id"])
    cookie = client.cookies.get("atesta_m365")
    assert cookie and first_state not in cookie  # sealed, not readable
    redirected = signin(client, subs["adm"], first_state)
    assert redirected.status_code == 302
    consent_url = redirected.headers["location"]
    assert consent_url.startswith(f"https://login.example/{TENANT}/adminconsent")
    second_state = state_of(consent_url)
    assert second_state != first_state
    done = consent(client, subs["adm"], second_state)
    assert done.status_code == 302
    assert done.headers["location"] == (
        f"https://app.example.com/app/connections?org={org}&connection={made['id']}"
    )
    assert stored(superuser, made["id"]) == (TENANT, OID)
    assert events(superuser, org, "connection.consent_granted") == 1
    replay = consent(client, subs["adm"], second_state)  # the cookie was single use
    assert refused(replay) == {"error": "connections.signin_invalid"}
    assert microsoft.sign_ins[0]["code"] == CODE
    # The test client logs the requests it sends (httpx, or httpx2 once the MCP SDK installs it,
    # https://testserver/...): in production the browser sends them. Every server-side record
    # must hold no code and no state.
    server = [
        r.getMessage()
        for r in caplog.records
        if not (r.name in ("httpx", "httpx2") and "https://testserver/" in r.getMessage())
    ]
    logged = "\n".join(server)
    assert CODE not in logged and first_state not in logged and second_state not in logged


def test_the_pkce_verifier_and_nonce_travel_only_in_the_sealed_cookie(
    client: TestClient, superuser: Engine, microsoft: FakeMicrosoft
) -> None:
    import base64
    import hashlib

    org, subs = org_with(client, superuser)
    made = create(client, org, subs["owner"])
    response = client.post(
        f"/api/v1/orgs/{org}/connections/{made['id']}/m365/signin", headers=auth(subs["owner"])
    )
    url = response.json()["authorize_url"]
    signin(client, subs["owner"], state_of(url))
    verifier = microsoft.sign_ins[0]["verifier"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert parse_qs(urlsplit(url).query)["code_challenge"] == [challenge.decode()]
    assert verifier not in url and microsoft.sign_ins[0]["nonce"] not in url


def test_a_missing_cookie_a_wrong_state_or_another_users_cookie_is_refused(
    client: TestClient, superuser: Engine, microsoft: FakeMicrosoft
) -> None:
    org, subs = org_with(client, superuser, other="admin")
    made = create(client, org, subs["owner"])
    invalid = {"error": "connections.signin_invalid"}  # no org: the caller was never checked
    start(client, org, subs["owner"], made["id"])
    assert refused(signin(client, subs["owner"], "wrong-state")) == invalid
    state = start(client, org, subs["owner"], made["id"])
    assert refused(signin(client, subs["other"], state)) == invalid
    state = start(client, org, subs["owner"], made["id"])
    client.cookies.clear()
    assert refused(signin(client, subs["owner"], state)) == invalid
    assert microsoft.sign_ins == []  # nothing reached Microsoft


def test_a_refused_id_token_and_an_outage_have_their_own_codes(
    client: TestClient, superuser: Engine, microsoft: FakeMicrosoft
) -> None:
    org, subs = org_with(client, superuser)
    made = create(client, org, subs["owner"])
    here = {"org": org, "connection": made["id"]}
    bad = signin(client, subs["owner"], start(client, org, subs["owner"], made["id"]), "refused")
    assert refused(bad) == {**here, "error": "connections.signin_invalid"}
    down = signin(client, subs["owner"], start(client, org, subs["owner"], made["id"]), "down")
    assert refused(down) == {**here, "error": "connections.microsoft_unavailable"}


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"error": "access_denied"}, "connections.consent_denied"),  # the admin selected Cancel
        ({"admin_consent": "False"}, "connections.consent_denied"),
        ({"tenant": "99999999-2222-4333-8444-555555555555"}, "connections.tenant_mismatch"),
    ],
)
def test_a_denied_or_forged_consent_stores_nothing(
    client: TestClient,
    superuser: Engine,
    microsoft: FakeMicrosoft,
    overrides: dict[str, str],
    expected: str,
) -> None:
    org, subs = org_with(client, superuser)
    made = create(client, org, subs["owner"])
    redirected = signin(client, subs["owner"], start(client, org, subs["owner"], made["id"]))
    response = consent(client, subs["owner"], state_of(redirected.headers["location"]), **overrides)
    assert refused(response) == {"org": org, "connection": made["id"], "error": expected}
    assert stored(superuser, made["id"]) == (None, None)
    assert events(superuser, org, "connection.consent_granted") == 0


def test_nothing_microsoft_sends_is_reflected_in_the_redirect(
    client: TestClient, superuser: Engine, microsoft: FakeMicrosoft
) -> None:
    org, subs = org_with(client, superuser)
    made = create(client, org, subs["owner"])
    redirected = signin(client, subs["owner"], start(client, org, subs["owner"], made["id"]))
    state = state_of(redirected.headers["location"])
    response = consent(
        client, subs["owner"], state, error="access_denied", error_description="AADSTS65004 x<y"
    )
    location = response.headers["location"]
    assert "AADSTS" not in location and "access_denied" not in location and state not in location
    assert refused(response)["error"] == "connections.consent_denied"


def test_the_consent_must_match_the_tenant_pinned_by_an_earlier_verification(
    client: TestClient, superuser: Engine, microsoft: FakeMicrosoft
) -> None:
    org, subs = org_with(client, superuser)
    made = create(client, org, subs["owner"])
    with superuser.begin() as conn:  # verified once against another tenant, then revoked
        conn.execute(
            text(
                "UPDATE connections SET status = 'revoked',"
                " external_tenant_id = '99999999-2222-4333-8444-555555555555' WHERE id = :c"
            ),
            {"c": made["id"]},
        )
    redirected = signin(client, subs["owner"], start(client, org, subs["owner"], made["id"]))
    response = consent(client, subs["owner"], state_of(redirected.headers["location"]))
    assert refused(response) == {
        "org": org,
        "connection": made["id"],
        "error": "connections.tenant_mismatch",
    }


def test_a_member_cannot_start_and_a_demoted_admin_cannot_finish(
    client: TestClient, superuser: Engine, microsoft: FakeMicrosoft
) -> None:
    org, subs = org_with(client, superuser, adm="admin", mem="member")
    made = create(client, org, subs["adm"])
    forbidden = client.post(
        f"/api/v1/orgs/{org}/connections/{made['id']}/m365/signin", headers=auth(subs["mem"])
    )
    assert code_of(forbidden) == (403, "identity.forbidden")
    state = start(client, org, subs["adm"], made["id"])
    with superuser.begin() as conn:
        conn.execute(
            text(
                "UPDATE memberships SET role = 'member' WHERE organization_id = :o"
                " AND user_id = (SELECT id FROM users WHERE cognito_sub = :s)"
            ),
            {"o": org, "s": subs["adm"]},
        )
    assert refused(signin(client, subs["adm"], state)) == {"error": "identity.forbidden"}


def test_only_an_m365_connection_still_onboarding_can_start(
    client: TestClient, superuser: Engine, microsoft: FakeMicrosoft
) -> None:
    org, subs = org_with(client, superuser)
    google = create(client, org, subs["owner"], provider="google_workspace", display_name="G")
    path = f"/api/v1/orgs/{org}/connections/{google['id']}/m365/signin"
    assert code_of(client.post(path, headers=auth(subs["owner"]))) == (
        409,
        "connections.state_invalid",
    )
    made = create(client, org, subs["owner"])
    client.delete(f"/api/v1/orgs/{org}/connections/{made['id']}", headers=auth(subs["owner"]))
    path = f"/api/v1/orgs/{org}/connections/{made['id']}/m365/signin"
    assert code_of(client.post(path, headers=auth(subs["owner"]))) == (
        409,
        "connections.state_invalid",
    )


def test_onboarding_answers_503_until_the_apps_are_registered(
    client: TestClient, superuser: Engine
) -> None:
    app.state.m365 = None
    org, subs = org_with(client, superuser)
    made = create(client, org, subs["owner"])
    path = f"/api/v1/orgs/{org}/connections/{made['id']}/m365/signin"
    assert code_of(client.post(path, headers=auth(subs["owner"]))) == (
        503,
        "connections.microsoft_unavailable",
    )
