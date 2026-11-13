"""Cognito access-token verification and profile lookup (identity-auth spec).

Never logs tokens. Raises InvalidTokenError with a stable code only.
"""

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
import jwt

ADMIN_SCOPE = "aws.cognito.signin.user.admin"
JWKS_REFETCH_SECONDS = 300
LEEWAY_SECONDS = 60


class InvalidTokenError(Exception):
    code = "auth.invalid_token"


class ExpiredTokenError(InvalidTokenError):
    """Well-formed and correctly signed, but past exp (plus leeway): refreshable."""


@dataclass(frozen=True, slots=True)
class CognitoSettings:
    region: str
    user_pool_id: str
    app_client_id: str
    domain: str

    @classmethod
    def from_env(cls) -> "CognitoSettings":
        env = os.environ
        return cls(
            env["ATESTA_COGNITO_REGION"],
            env["ATESTA_COGNITO_USER_POOL_ID"],
            env["ATESTA_COGNITO_APP_CLIENT_ID"],
            env["ATESTA_COGNITO_DOMAIN"],
        )

    @property
    def issuer(self) -> str:
        return f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"


@dataclass(frozen=True, slots=True)
class AccessToken:
    sub: str
    scopes: frozenset[str]


class TokenVerifier:
    """RS256 against cached JWKS; unknown kid refetches at most once every 5 minutes."""

    def __init__(
        self,
        settings: CognitoSettings,
        fetch_jwks: Callable[[], dict[str, Any]],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._fetch = fetch_jwks
        self._clock = clock
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None
        self._lock = threading.Lock()

    def _key(self, kid: str) -> Any:
        with self._lock:
            stale = self._fetched_at is None or (
                self._clock() - self._fetched_at >= JWKS_REFETCH_SECONDS
            )
            if kid not in self._keys and stale:
                jwks = self._fetch()
                self._keys = {k["kid"]: jwt.PyJWK(k).key for k in jwks.get("keys", [])}
                self._fetched_at = self._clock()
            return self._keys.get(kid)

    def _decode(self, token: str, audience: str | None) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            key = self._key(str(header.get("kid", "")))
            if key is None or header.get("alg") != "RS256":
                raise InvalidTokenError
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._settings.issuer,
                audience=audience,
                leeway=LEEWAY_SECONDS,
                options={
                    "require": ["exp", "iat", "iss", "sub"],
                    "verify_aud": audience is not None,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise ExpiredTokenError from exc
        except jwt.PyJWTError as exc:
            raise InvalidTokenError from exc
        return claims

    def verify(self, token: str) -> AccessToken:
        claims = self._decode(token, audience=None)
        scopes = frozenset(str(claims.get("scope", "")).split())
        if (
            claims.get("token_use") != "access"
            or claims.get("client_id") != self._settings.app_client_id
            or "openid" not in scopes
            or ADMIN_SCOPE in scopes
        ):
            raise InvalidTokenError
        return AccessToken(sub=str(claims["sub"]), scopes=scopes)

    def verify_id_token(self, token: str) -> dict[str, Any]:
        """ID tokens are used only to check the sign-in nonce, never to authorize requests."""
        claims = self._decode(token, audience=self._settings.app_client_id)
        if claims.get("token_use") != "id":
            raise InvalidTokenError
        return claims


def jwks_fetcher(settings: CognitoSettings, client: httpx.Client) -> Callable[[], dict[str, Any]]:
    def fetch() -> dict[str, Any]:
        response = client.get(f"{settings.issuer}/.well-known/jwks.json", timeout=5)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    return fetch


@dataclass(frozen=True, slots=True)
class UserInfo:
    sub: str
    email: str
    email_verified: bool


class IdentityProvider(Protocol):
    def userinfo(self, access_token: str) -> UserInfo: ...


class CognitoUserInfo:
    """Profile from /oauth2/userInfo with the caller's own access token (scopes openid email)."""

    def __init__(self, settings: CognitoSettings, client: httpx.Client) -> None:
        self._url = f"https://{settings.domain}/oauth2/userInfo"
        self._client = client

    def userinfo(self, access_token: str) -> UserInfo:
        response = self._client.get(
            self._url, headers={"Authorization": f"Bearer {access_token}"}, timeout=5
        )
        if response.status_code in (400, 401, 403):
            raise InvalidTokenError
        response.raise_for_status()
        data = response.json()
        verified = data.get("email_verified") in ("true", True)
        return UserInfo(sub=str(data["sub"]), email=str(data["email"]), email_verified=verified)


@dataclass(frozen=True, slots=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    id_token: str | None


class CognitoOAuth:
    """Managed login endpoints for the BFF: public client, Authorization Code + PKCE."""

    def __init__(
        self,
        settings: CognitoSettings,
        client: httpx.Client,
        verifier: TokenVerifier,
        web_origin: str,
    ) -> None:
        self._base = f"https://{settings.domain}"
        self._client_id = settings.app_client_id
        self._client = client
        self._verifier = verifier
        self._redirect_uri = f"{web_origin}/auth/callback"
        self._logout_uri = f"{web_origin}/"

    def authorize_url(self, *, state: str, nonce: str, challenge: str, lang: str) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "scope": "openid email",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "lang": lang,
            }
        )
        return f"{self._base}/oauth2/authorize?{query}"

    def _token(self, form: dict[str, str]) -> TokenSet:
        response = self._client.post(f"{self._base}/oauth2/token", data=form, timeout=5)
        if response.status_code in (400, 401):
            raise InvalidTokenError
        response.raise_for_status()
        body = response.json()
        return TokenSet(
            access_token=str(body["access_token"]),
            refresh_token=body.get("refresh_token"),
            id_token=body.get("id_token"),
        )

    def exchange_code(self, code: str, verifier: str) -> TokenSet:
        return self._token(
            {
                "grant_type": "authorization_code",
                "client_id": self._client_id,
                "code": code,
                "redirect_uri": self._redirect_uri,
                "code_verifier": verifier,
            }
        )

    def refresh(self, refresh_token: str) -> TokenSet:
        return self._token(
            {
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "refresh_token": refresh_token,
            }
        )

    def id_token_nonce(self, id_token: str) -> str:
        return str(self._verifier.verify_id_token(id_token).get("nonce", ""))

    def logout_url(self) -> str:
        query = urlencode({"client_id": self._client_id, "logout_uri": self._logout_uri})
        return f"{self._base}/logout?{query}"
