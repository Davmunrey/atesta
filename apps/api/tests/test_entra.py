"""Entra sign-in for M365 onboarding (#314): ID token checks against a fake Microsoft, no network.

Tokens are signed here with a throwaway RSA key, served from a fake JWKS endpoint. The Sign-in
app proves itself with a certificate, never a client secret (#363): the certificates here are
self-signed and made per test run.
"""

import base64
import hashlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
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
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

TENANT = "11111111-2222-4333-8444-555555555555"
OID = "66666666-7777-4888-8999-aaaaaaaaaaaa"
CLIENT = "signin-client-id"
NONCE = "synthetic-nonce"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TOKEN_ENDPOINT = f"{AUTHORITY}/organizations/oauth2/v2.0/token"
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


def certificate(key: Any, *, days: int = 365) -> x509.Certificate:
    """Self-signed, valid from yesterday for `days` days (negative: already expired)."""
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "atesta-signin-test")])
    start = datetime.now(UTC) - timedelta(days=1)
    end = start + timedelta(days=days) if days > 0 else datetime.now(UTC) - timedelta(hours=1)
    if days <= 0:
        start = end - timedelta(days=30)
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .sign(key, hashes.SHA256())
    )


def pfx(key: Any, cert: x509.Certificate | None, password: bytes | None = None) -> str:
    """Base64 of a PFX, the format the API reads from ATESTA_M365_SIGNIN_CERTIFICATE."""
    encryption = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )
    return base64.b64encode(
        pkcs12.serialize_key_and_certificates(b"signin", key, cert, None, encryption)
    ).decode()


SIGNIN_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SIGNIN_CERT = certificate(SIGNIN_KEY)
SIGNIN_PFX = pfx(SIGNIN_KEY, SIGNIN_CERT)
ENV = {
    "ATESTA_M365_SIGNIN_CLIENT_ID": CLIENT,
    "ATESTA_M365_SIGNIN_CERTIFICATE": SIGNIN_PFX,
    "ATESTA_M365_SCANNER_CLIENT_ID": "scanner-client-id",
    "ATESTA_WEB_BASE_URL": "https://app.example.com/",
}
_SETTINGS = EntraSettings.from_env(ENV)
assert _SETTINGS is not None
SETTINGS: EntraSettings = _SETTINGS


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


def entra(fake: FakeMicrosoft, settings: EntraSettings = SETTINGS) -> EntraSignIn:
    return EntraSignIn(settings, httpx.Client(transport=httpx.MockTransport(fake.handle)))


def test_a_valid_sign_in_binds_the_tenant_and_the_admin_object_id() -> None:
    fake = FakeMicrosoft(token())
    signed_in = entra(fake).sign_in(code="the-code", verifier="the-verifier", nonce=NONCE)
    assert (signed_in.tenant_id, signed_in.object_id) == (TENANT, OID)
    form = fake.token_requests[0]
    assert "client_secret" not in form and form["code_verifier"] == ["the-verifier"]
    assert form["client_id"] == [CLIENT] and form["client_assertion_type"] == [ASSERTION_TYPE]
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


def test_the_code_is_redeemed_with_a_certificate_assertion_as_microsoft_documents() -> None:
    """certificate-credentials, "Assertion format" (read 2026-11-24): PS256, x5t#S256, and
    aud, iss, sub, jti, nbf, iat and a short exp."""
    fake = FakeMicrosoft(token())
    before = int(time.time())
    client = entra(fake)
    client.sign_in(code="c", verifier="v", nonce=NONCE)
    client.sign_in(code="c2", verifier="v2", nonce=NONCE)
    first, second = (form["client_assertion"][0] for form in fake.token_requests)
    header = jwt.get_unverified_header(first)
    der = SIGNIN_CERT.public_bytes(serialization.Encoding.DER)
    assert header == {
        "alg": "PS256",
        "typ": "JWT",
        "x5t#S256": base64.urlsafe_b64encode(hashlib.sha256(der).digest()).decode(),
    }
    claims = jwt.decode(
        first, SIGNIN_CERT.public_key(), algorithms=["PS256"], audience=TOKEN_ENDPOINT
    )
    assert claims["iss"] == claims["sub"] == CLIENT
    assert before <= claims["iat"] == claims["nbf"] <= int(time.time())
    assert claims["exp"] - claims["nbf"] == 300  # Microsoft: 5 to 10 minutes at most
    assert uuid.UUID(claims["jti"]).version == 4
    assert set(claims) == {"aud", "iss", "sub", "jti", "iat", "nbf", "exp"}
    other = jwt.decode(
        second, SIGNIN_CERT.public_key(), algorithms=["PS256"], audience=TOKEN_ENDPOINT
    )
    assert other["jti"] != claims["jti"]  # one assertion per sign-in, never reused


def test_an_expired_certificate_stops_the_sign_in_before_microsoft_is_called() -> None:
    expired = EntraSettings.from_env(
        {**ENV, "ATESTA_M365_SIGNIN_CERTIFICATE": pfx(SIGNIN_KEY, certificate(SIGNIN_KEY, days=0))}
    )
    assert expired is not None
    fake = FakeMicrosoft(token())
    with pytest.raises(MicrosoftUnavailableError):
        entra(fake, expired).sign_in(code="c", verifier="v", nonce=NONCE)
    assert fake.token_requests == []


def test_settings_are_optional_and_never_show_the_key() -> None:
    assert EntraSettings.from_env({"ATESTA_WEB_BASE_URL": "https://x"}) is None
    for missing in ("ATESTA_M365_SIGNIN_CLIENT_ID", "ATESTA_M365_SIGNIN_CERTIFICATE"):
        assert EntraSettings.from_env({k: v for k, v in ENV.items() if k != missing}) is None
    assert SETTINGS.web_base_url == "https://app.example.com"
    shown = repr(SETTINGS)
    assert SIGNIN_PFX not in shown and "PrivateKey" not in shown and "BEGIN" not in shown


WEAK_KEY = rsa.generate_private_key(public_exponent=65537, key_size=1024)  # noqa: S505  # nosemgrep: python.cryptography.security.insufficient-rsa-key-size.insufficient-rsa-key-size - the weak key the API must refuse
EC_KEY = ec.generate_private_key(ec.SECP256R1())


@pytest.mark.parametrize(
    "value",
    [
        "not base64 !!",
        base64.b64encode(b"not a pfx").decode(),
        pfx(SIGNIN_KEY, SIGNIN_CERT, password=b"a-password"),  # must be passwordless
        pfx(SIGNIN_KEY, None),  # a key with no certificate
        pfx(WEAK_KEY, certificate(WEAK_KEY)),  # RSA under 2048 bits
        pfx(EC_KEY, certificate(EC_KEY)),  # PS256 needs an RSA key
    ],
    ids=["not-base64", "not-pfx", "password", "no-certificate", "weak-rsa", "ec-key"],
)
def test_an_unusable_certificate_stops_the_start_without_echoing_it(value: str) -> None:
    with pytest.raises(ValueError, match="ATESTA_M365_SIGNIN_CERTIFICATE") as refused:
        EntraSettings.from_env({**ENV, "ATESTA_M365_SIGNIN_CERTIFICATE": value})
    assert value not in str(refused.value)
    assert refused.value.__cause__ is None  # no library message that could carry key material


def test_a_leftover_client_secret_stops_the_start() -> None:
    """Issue 363: the secret is gone. One still configured must be deleted, not ignored."""
    leftover = "x" * 24  # no entropy: never looks like a real secret to the scanner
    with pytest.raises(ValueError, match="ATESTA_M365_SIGNIN_CLIENT_SECRET") as refused:
        EntraSettings.from_env({**ENV, "ATESTA_M365_SIGNIN_CLIENT_SECRET": leftover})
    assert leftover not in str(refused.value)
