"""Access-token verification and userInfo parsing (identity-auth spec, test plan "JWT")."""

import threading
import time
from typing import Any

import httpx
import jwt
import pytest
from atesta_api.modules.identity.cognito import (
    CognitoSettings,
    CognitoUserInfo,
    InvalidTokenError,
    ProviderUnavailableError,
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


class FailingJwks:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> dict[str, Any]:
        self.calls += 1
        raise httpx.ConnectError("unreachable")


def test_failed_fetch_is_retried_at_most_every_30_seconds_and_is_a_503() -> None:
    """Junk-kid tokens cannot turn a JWKS outage into a request flood."""
    now = [1000.0]
    jwks = FailingJwks()
    v = TokenVerifier(SETTINGS, jwks, lambda: now[0])
    for kid in ("k1", "x1", "x2", "x3"):
        with pytest.raises(ProviderUnavailableError):
            v.verify(token(kid=kid))
    assert jwks.calls == 1
    now[0] += 31
    with pytest.raises(ProviderUnavailableError):
        v.verify(token())
    assert jwks.calls == 2


@pytest.mark.parametrize("body", [{}, {"keys": [{"kid": "k1"}]}, {"keys": "x"}])
def test_malformed_jwks_is_provider_unavailable(body: dict[str, Any]) -> None:
    with pytest.raises(ProviderUnavailableError):
        TokenVerifier(SETTINGS, lambda: body).verify(token())


def test_outage_after_success_keeps_cached_keys_and_refuses_unknown_kids_with_503() -> None:
    now = [1000.0]
    jwks = Jwks(jwk(KEY, "k1"))
    v = verifier(jwks, clock=lambda: now[0])
    v.verify(token())
    down = FailingJwks()
    v._fetch = down  # the provider goes down
    now[0] += 301
    with pytest.raises(ProviderUnavailableError):
        v.verify(token(kid="k2"))
    with pytest.raises(ProviderUnavailableError):  # still unknown, not a 401, no new fetch
        v.verify(token(kid="k3"))
    assert down.calls == 1
    assert v.verify(token()).sub == "sub-1"  # cached kid still verifies


def test_fetch_runs_outside_the_lock() -> None:
    """A slow fetch for an unknown kid does not block a token whose kid is cached."""
    started, release = threading.Event(), threading.Event()
    keys = {"keys": [jwk(KEY, "k1")]}
    calls = [0]

    def slow() -> dict[str, Any]:
        calls[0] += 1
        if calls[0] > 1:
            started.set()
            assert release.wait(5)
        return keys

    v = TokenVerifier(SETTINGS, slow, lambda: 1000.0 + 301 * calls[0])
    v.verify(token())  # first fetch, fast
    outcome: list[object] = []
    fetching = threading.Thread(target=lambda: outcome.append(_try(v, token(kid="k9"))))
    fetching.start()
    assert started.wait(5)
    try:
        cached = threading.Thread(target=lambda: outcome.append(v.verify(token()).sub))
        cached.start()
        cached.join(timeout=1)
        assert not cached.is_alive(), "cached-kid verify waited for the JWKS fetch"
        with pytest.raises(ProviderUnavailableError):  # a second fetch never runs in parallel
            v.verify(token(kid="k8"))
    finally:
        release.set()
        fetching.join(timeout=5)
    assert calls[0] == 2
    assert sorted(map(str, outcome)) == ["InvalidTokenError", "sub-1"]


def _try(v: TokenVerifier, raw: str) -> object:
    try:
        return v.verify(raw)
    except (InvalidTokenError, ProviderUnavailableError) as exc:
        return type(exc).__name__


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


def test_expired_token_is_distinguishable_for_refresh() -> None:
    from atesta_api.modules.identity.cognito import ExpiredTokenError

    with pytest.raises(ExpiredTokenError):
        verifier().verify(token(exp=int(time.time()) - 120))


def _oauth(handler: Any) -> Any:
    from atesta_api.modules.identity.cognito import CognitoOAuth

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return CognitoOAuth(SETTINGS, client, verifier(), "https://app.example.com")


def test_authorize_url_is_pkce_s256_with_openid_email_only() -> None:
    url = _oauth(lambda r: httpx.Response(500)).authorize_url(
        state="s", nonce="n", challenge="c", lang="es"
    )
    query = dict(httpx.URL(url).params)
    assert url.startswith("https://auth.example.com/oauth2/authorize?")
    assert query == {
        "response_type": "code",
        "client_id": "client-1",
        "redirect_uri": "https://app.example.com/auth/callback",
        "scope": "openid email",
        "state": "s",
        "nonce": "n",
        "code_challenge": "c",
        "code_challenge_method": "S256",
        "lang": "es",
    }


def test_code_exchange_and_refresh_post_forms_without_a_secret() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://auth.example.com/oauth2/token"
        assert "authorization" not in request.headers  # public client: no client secret
        seen.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(
            200, json={"access_token": "a", "refresh_token": "r", "id_token": "i"}
        )

    oauth = _oauth(handler)
    assert oauth.exchange_code("code-1", "v" * 43).refresh_token == "r"
    assert oauth.refresh("r").access_token == "a"
    assert seen[0]["code_verifier"] == "v" * 43 and seen[0]["grant_type"] == "authorization_code"
    assert seen[1] == {"grant_type": "refresh_token", "client_id": "client-1", "refresh_token": "r"}


def test_rejected_grant_raises_invalid_token() -> None:
    with pytest.raises(InvalidTokenError):
        _oauth(lambda r: httpx.Response(400, json={"error": "invalid_grant"})).refresh("r")


def test_revoke_posts_the_refresh_token_and_tells_an_outage_from_a_refusal() -> None:
    """POST /oauth2/revoke with token and client_id, no secret (public client, #324)."""
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://auth.example.com/oauth2/revoke"
        assert "authorization" not in request.headers
        seen.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200)

    _oauth(handler).revoke("r-1")
    assert seen == [{"token": "r-1", "client_id": "client-1"}]
    with pytest.raises(InvalidTokenError):
        _oauth(lambda r: httpx.Response(400, json={"error": "invalid_request"})).revoke("r")
    with pytest.raises(ProviderUnavailableError):
        _oauth(lambda r: httpx.Response(503)).revoke("r")

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    with pytest.raises(ProviderUnavailableError):
        _oauth(down).revoke("r")


def test_id_token_nonce_needs_a_valid_id_token() -> None:
    id_token = token(token_use="id", aud="client-1", nonce="n-1", client_id=None, scope=None)
    oauth = _oauth(lambda r: httpx.Response(500))
    assert oauth.id_token_nonce(id_token) == "n-1"
    for bad in (token(), token(token_use="id", aud="other", nonce="n-1")):
        with pytest.raises(InvalidTokenError):
            oauth.id_token_nonce(bad)
