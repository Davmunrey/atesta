"""Access-token verification and userInfo parsing (identity-auth spec, test plan "JWT")."""

import time
from typing import Any

import httpx
import jwt
import pytest
from atesta_api.modules.identity.cognito import (
    CognitoSettings,
    CognitoUserInfo,
    InvalidTokenError,
    TokenVerifier,
)
from cryptography.hazmat.primitives.asymmetric import rsa

SETTINGS = CognitoSettings("eu-south-2", "eu-south-2_TEST", "client-1", "auth.example.com")
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    data: dict[str, Any] = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {**data, "kid": kid, "alg": "RS256", "use": "sig"}


def token(key: Any = KEY, kid: str = "k1", alg: str = "RS256", **overrides: Any) -> str:
    now = int(time.time())
    claims = {
        "sub": "sub-1",
        "iss": SETTINGS.issuer,
        "token_use": "access",
        "client_id": "client-1",
        "scope": "openid email",
        "iat": now,
        "exp": now + 1800,
        **overrides,
    }
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


class Jwks:
    def __init__(self, *keys: dict[str, Any]) -> None:
        self.keys = list(keys)
        self.calls = 0

    def __call__(self) -> dict[str, Any]:
        self.calls += 1
        return {"keys": self.keys}


def verifier(jwks: Jwks | None = None, clock: Any = time.monotonic) -> TokenVerifier:
    return TokenVerifier(SETTINGS, jwks or Jwks(jwk(KEY, "k1")), clock)


def test_valid_access_token() -> None:
    assert verifier().verify(token()).sub == "sub-1"


def test_expiry_leeway_is_60_seconds() -> None:
    now = int(time.time())
    assert verifier().verify(token(exp=now - 30)).sub == "sub-1"
    with pytest.raises(InvalidTokenError):
        verifier().verify(token(exp=now - 90))


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://cognito-idp.eu-west-1.amazonaws.com/eu-south-2_TEST"},
        {"client_id": "client-2"},
        {"token_use": "id"},
        {"scope": "email"},
        {"scope": "openid email aws.cognito.signin.user.admin"},
        {"exp": None},
        {"sub": None},
    ],
)
def test_rejected_claims(overrides: dict[str, Any]) -> None:
    with pytest.raises(InvalidTokenError):
        verifier().verify(token(**overrides))


def test_rejected_algorithms_and_signatures() -> None:
    v = verifier()
    for bad in (
        # full, otherwise valid claims: rejected for the algorithm, not for a missing claim
        token(key=None, alg="none"),
        token(key="secret-key-of-32-bytes-minimum!!", alg="HS256"),
        token(key=OTHER_KEY),
        token()[:-4] + "AAAA",
        "not-a-jwt",
    ):
        with pytest.raises(InvalidTokenError):
            v.verify(bad)


def test_unknown_kid_refetches_at_most_every_five_minutes() -> None:
    now = [1000.0]
    jwks = Jwks(jwk(KEY, "k1"))
    v = verifier(jwks, clock=lambda: now[0])
    v.verify(token())
    for _ in range(3):
        with pytest.raises(InvalidTokenError):
            v.verify(token(kid="k2"))
    assert jwks.calls == 1
    jwks.keys.append(jwk(KEY, "k2"))
    now[0] += 301
    assert v.verify(token(kid="k2")).sub == "sub-1"
    assert jwks.calls == 2


def _provider(status: int, body: dict[str, Any]) -> CognitoUserInfo:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://auth.example.com/oauth2/userInfo"
        assert request.headers["Authorization"] == "Bearer at-1"
        return httpx.Response(status, json=body)

    return CognitoUserInfo(SETTINGS, httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize(("raw", "verified"), [("true", True), ("false", False), ("yes", False)])
def test_userinfo_email_verified_is_strict(raw: str, verified: bool) -> None:
    body = {"sub": "sub-1", "email": "a@example.com", "email_verified": raw}
    assert _provider(200, body).userinfo("at-1").email_verified is verified


def test_userinfo_rejected_token() -> None:
    with pytest.raises(InvalidTokenError):
        _provider(401, {"error": "invalid_token"}).userinfo("at-1")
