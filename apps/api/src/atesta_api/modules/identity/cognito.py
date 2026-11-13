"""Cognito access-token verification and profile lookup (identity-auth spec).

Never logs tokens. Raises InvalidTokenError with a stable code only.
"""

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import jwt

ADMIN_SCOPE = "aws.cognito.signin.user.admin"
JWKS_REFETCH_SECONDS = 300
LEEWAY_SECONDS = 60


class InvalidTokenError(Exception):
    code = "auth.invalid_token"


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

    def verify(self, token: str) -> AccessToken:
        try:
            header = jwt.get_unverified_header(token)
            key = self._key(str(header.get("kid", "")))
            if key is None or header.get("alg") != "RS256":
                raise InvalidTokenError
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._settings.issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "iss", "sub"], "verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError from exc
        scopes = frozenset(str(claims.get("scope", "")).split())
        if (
            claims.get("token_use") != "access"
            or claims.get("client_id") != self._settings.app_client_id
            or "openid" not in scopes
            or ADMIN_SCOPE in scopes
        ):
            raise InvalidTokenError
        return AccessToken(sub=str(claims["sub"]), scopes=scopes)


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
