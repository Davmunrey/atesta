"""The verifier's Google token (scanner-connectors spec, Google verifier contract, step 1).

A JWT bearer grant signed with the org's service account key, sent only to Google's token URL.
Google's `error` decides the outcome; its description is compared, never kept. Fail closed:
no answer but an access token is ever a token.
"""

import base64
import json
from typing import Any

import httpx
import pytest
from atesta_scanner.entra_token import TokenTransientError, TokenUnavailableError
from atesta_scanner.google_token import (
    GRANT_TYPE,
    TOKEN_URL,
    TokenRefusedError,
    delegated_token,
    load_key,
)
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

SUBJECT = "admin@example.es"
SCOPES = frozenset(
    {
        "https://www.googleapis.com/auth/admin.directory.user.readonly",
        "https://www.googleapis.com/auth/admin.directory.domain.readonly",
    }
)
PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = PRIVATE.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
KEY_JSON = {
    "type": "service_account",
    "project_id": "atesta-dev",
    "private_key_id": "0123456789abcdef0123456789abcdef01234567",
    "private_key": PEM,
    "client_email": "scan-org@atesta-dev.iam.gserviceaccount.com",
    "client_id": "111111111111111111111",
    "token_uri": "https://attacker.example/token",  # never followed
}
NOW = 1_800_000_000


def raw(**changes: object) -> str:
    return json.dumps({**KEY_JSON, **changes})


def unb64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def google(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def token(client: httpx.Client) -> str:
    return delegated_token(client, load_key(raw()), SUBJECT, SCOPES, clock=lambda: NOW)


def test_the_grant_is_a_signed_jwt_for_the_subject_and_exactly_the_scopes() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"access_token": "fake-access-token", "expires_in": 3599})

    assert token(google(handler)) == "fake-access-token"
    [request] = seen
    assert (request.method, str(request.url)) == ("POST", TOKEN_URL)  # never the key's token_uri
    form = dict(httpx.QueryParams(request.content.decode()))
    assert form["grant_type"] == GRANT_TYPE == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    header, claims, signature = form["assertion"].split(".")
    assert json.loads(unb64(header)) == {
        "alg": "RS256",
        "typ": "JWT",
        "kid": KEY_JSON["private_key_id"],
    }
    assert json.loads(unb64(claims)) == {
        "iss": KEY_JSON["client_email"],
        "sub": SUBJECT,
        "scope": " ".join(sorted(SCOPES)),
        "aud": TOKEN_URL,
        "iat": NOW,
        "exp": NOW + 3600,
    }
    PRIVATE.public_key().verify(  # raises if the signature is not the key's
        unb64(signature), f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256()
    )


@pytest.mark.parametrize(
    ("error", "description", "reason"),
    [
        (
            "unauthorized_client",
            "Client is unauthorized to retrieve access tokens",
            "not_authorized",
        ),
        ("access_denied", "Requested client not authorized.", "not_authorized"),
        ("admin_policy_enforced", "Blocked by your admin", "blocked_by_policy"),
        ("invalid_grant", "Invalid email or User ID", "delegated_user"),
        ("invalid_grant", "Not a valid email.", "delegated_user"),
    ],
)
def test_refusals_the_customer_can_fix_are_named(error: str, description: str, reason: str) -> None:
    client = google(
        lambda r: httpx.Response(400, json={"error": error, "error_description": description})
    )
    with pytest.raises(TokenRefusedError) as refused:
        token(client)
    assert refused.value.reason == reason
    assert description not in str(refused.value)  # Google's text is never kept


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, {"error": "invalid_grant", "error_description": "Invalid JWT Signature."}),
        (400, {"error": "invalid_grant", "error_description": "Invalid JWT: Token must be short"}),
        (401, {"error": "invalid_client", "error_description": "The OAuth client was not found."}),
        (401, {"error": "deleted_client", "error_description": "The OAuth client was deleted."}),
        (400, {"error": "invalid_scope", "error_description": "Bad scope"}),
        (400, {"error": "something_new"}),
        (200, {"token_type": "Bearer"}),  # no access token
    ],
)
def test_refusals_of_atestas_own_credential_never_touch_the_connection(
    status: int, body: dict[str, str]
) -> None:
    with pytest.raises(TokenUnavailableError):
        token(google(lambda r: httpx.Response(status, json=body)))


@pytest.mark.parametrize("status", [429, 500, 503])
def test_throttling_and_outages_are_transient(status: int) -> None:
    with pytest.raises(TokenTransientError):
        token(google(lambda r: httpx.Response(status, json={"error": "rate_limit"})))


def test_a_network_failure_or_an_answer_that_is_not_json_is_transient() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    with pytest.raises(TokenTransientError):
        token(google(down))
    with pytest.raises(TokenTransientError):
        token(google(lambda r: httpx.Response(400, text="<html>")))


EC_PEM = (
    ec.generate_private_key(ec.SECP256R1())
    .private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    .decode()
)


@pytest.mark.parametrize(
    "key",
    [
        "not json",
        json.dumps(["service_account"]),
        raw(type="authorized_user"),
        raw(client_id="not-a-number"),
        raw(client_email=""),
        raw(private_key_id=None),
        raw(private_key="-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n"),
        raw(private_key=EC_PEM),  # Google signs service account grants with RS256 only
    ],
)
def test_a_key_that_does_not_load_is_atestas_credential_problem(key: str) -> None:
    with pytest.raises(TokenUnavailableError) as error:
        load_key(key)
    assert PEM.splitlines()[1] not in str(error.value)  # rule 2: no key material in errors
    chained = error.value.__context__ is not None and not error.value.__suppress_context__
    assert error.value.__cause__ is None and not chained  # no parser error holding the key


def test_a_loaded_key_never_prints_its_private_part() -> None:
    key = load_key(raw())
    assert key.client_id == KEY_JSON["client_id"]
    assert "PRIVATE" not in repr(key) and "RSAPrivateKey" not in repr(key)
