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

from atesta_api.modules.identity.agent_oauth import AgentOAuth, AgentToken
from atesta_api.platform.devenv import DEV_ENVS

ADMIN_SCOPE = "aws.cognito.signin.user.admin"
JWKS_REFETCH_SECONDS = 300  # after a successful fetch (spec)
JWKS_RETRY_SECONDS = 30  # after a failed fetch
LEEWAY_SECONDS = 60


class InvalidTokenError(Exception):
    code = "auth.invalid_token"


class ProviderUnavailableError(Exception):
    """JWKS could not be fetched or parsed: a retryable 503, never a 401."""

    code = "auth.provider_unavailable"


class ExpiredTokenError(InvalidTokenError):
    """Well-formed and correctly signed, but past exp (plus leeway): refreshable."""


@dataclass(frozen=True, slots=True)
class CognitoSettings:
    region: str
    user_pool_id: str
    app_client_id: str
    domain: str
    issuer_override: str | None = None  # local fake only (local-dev-auth spec)
    base_url_override: str | None = None

    @classmethod
    def from_env(cls) -> "CognitoSettings":
        env = os.environ
        issuer = env.get("ATESTA_COGNITO_ISSUER")
        base_url = env.get("ATESTA_COGNITO_BASE_URL")
        if (issuer or base_url) and env.get("ATESTA_ENV") not in DEV_ENVS:
            raise RuntimeError(
                "Cognito issuer and base URL overrides require ATESTA_ENV local, dev or test"
            )
        return cls(
            env["ATESTA_COGNITO_REGION"],
            env["ATESTA_COGNITO_USER_POOL_ID"],
            env["ATESTA_COGNITO_APP_CLIENT_ID"],
            env["ATESTA_COGNITO_DOMAIN"],
            issuer,
            base_url,
        )

    @property
    def issuer(self) -> str:
        default = f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
        return self.issuer_override or default

    @property
    def base_url(self) -> str:
        """Managed login domain: authorize, token, userInfo and logout endpoints."""
        return (self.base_url_override or f"https://{self.domain}").rstrip("/")


@dataclass(frozen=True, slots=True)
class AccessToken:
    sub: str
    scopes: frozenset[str]
    auth_time: int | None = None  # when the person signed in; a refresh keeps it (operator portal)


class TokenVerifier:
    """RS256 against cached JWKS; unknown kid refetches at most once every 5 minutes.

    One fetch at a time, outside the lock, so cached kids never wait on the network. A failed
    fetch is retried after 30 s; until a fetch succeeds, unknown kids get ProviderUnavailableError.
    """

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
        self._attempted_at: float | None = None
        self._last_ok = False
        self._fetching = False
        self._lock = threading.Lock()

    def _key(self, kid: str) -> Any:
        with self._lock:
            if kid in self._keys:
                return self._keys[kid]
            now = self._clock()
            window = JWKS_REFETCH_SECONDS if self._last_ok else JWKS_RETRY_SECONDS
            if self._fetching or (
                self._attempted_at is not None and now - self._attempted_at < window
            ):
                if self._fetching or not self._last_ok:
                    raise ProviderUnavailableError  # cannot tell yet whether the kid is valid
                return None
            self._fetching, self._attempted_at = True, now
        try:
            data = self._fetch()
            keys = {str(k["kid"]): jwt.PyJWK(k).key for k in data["keys"]}
        except (httpx.HTTPError, ValueError, KeyError, TypeError, jwt.PyJWTError) as exc:
            with self._lock:
                self._fetching, self._last_ok = False, False
            raise ProviderUnavailableError from exc
        with self._lock:
            self._keys, self._fetching, self._last_ok = keys, False, True
        return keys.get(kid)

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
        auth_time = claims.get("auth_time")
        signed_in = (
            auth_time if isinstance(auth_time, int) and not isinstance(auth_time, bool) else None
        )
        return AccessToken(sub=str(claims["sub"]), scopes=scopes, auth_time=signed_in)

    def verify_agent(self, token: str, oauth: AgentOAuth) -> AgentToken:
        """An access token of the hosted MCP server (mcp-oauth spec): issued by this pool for
        that resource (`aud`), to an approved client, carrying the agent scope. A web session
        token has no such audience, so it is refused here."""
        claims = self._decode(token, audience=oauth.resource)
        client_id = str(claims.get("client_id", ""))
        if (
            claims.get("token_use") != "access"
            or client_id not in oauth.clients
            or client_id == self._settings.app_client_id
            or oauth.scope not in str(claims.get("scope", "")).split()
        ):
            raise InvalidTokenError
        return AgentToken(sub=str(claims["sub"]), client_id=client_id)

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
        self._url = f"{settings.base_url}/oauth2/userInfo"
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
        self._base = settings.base_url
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

    def revoke(self, refresh_token: str) -> None:
        """POST /oauth2/revoke: ends the refresh token and every access token issued with it.

        A token that is already revoked or not valid gets 200 (Cognito docs, token revocation
        endpoint); a 400 means the request itself was refused.
        """
        try:
            response = self._client.post(
                f"{self._base}/oauth2/revoke",
                data={"token": refresh_token, "client_id": self._client_id},
                timeout=5,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError from exc
        if response.status_code >= 500:
            raise ProviderUnavailableError
        if response.status_code != 200:
            raise InvalidTokenError

    def logout_url(self) -> str:
        query = urlencode({"client_id": self._client_id, "logout_uri": self._logout_uri})
        return f"{self._base}/logout?{query}"
