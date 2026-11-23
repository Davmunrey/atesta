"""Microsoft Entra sign-in for M365 onboarding (scanner-connectors spec, Microsoft 365 onboarding).

Two app registrations in Atesta's tenant: "Atesta Sign-in" (openid profile, no application
permissions) binds a connection to the tenant of a real admin, and "Atesta Scanner" receives the
admin consent. The Sign-in app redeems codes as a confidential web client: Microsoft documents
client_secret as "required for confidential web apps" (authorization code flow, read
2026-11-23). Nothing here logs a code, a token or the secret (rule 2).
"""

import hmac
import os
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
import jwt

AUTHORITY = "https://login.microsoftonline.com"
SIGNIN_PATH = "/auth/m365/signin-callback"
CONSENT_PATH = "/auth/m365/consent-callback"
JWKS_REFETCH_SECONDS = 300
LEEWAY_SECONDS = 60
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class SignInError(Exception):
    """The code or the ID token is not acceptable."""


class MicrosoftUnavailableError(Exception):
    """Microsoft could not be reached, or onboarding is not configured here."""


@dataclass(frozen=True, slots=True)
class SignedIn:
    tenant_id: str  # tid: the Entra tenant the admin signed in to
    object_id: str  # oid: the admin's object id in that tenant; never `sub` (pairwise per app)


class M365Identity(Protocol):
    def authorize_url(self, *, state: str, nonce: str, challenge: str) -> str: ...
    def sign_in(self, *, code: str, verifier: str, nonce: str) -> SignedIn: ...
    def consent_url(self, *, tenant_id: str, state: str) -> str: ...


@dataclass(frozen=True, slots=True)
class EntraSettings:
    signin_client_id: str
    signin_client_secret: str = field(repr=False)
    scanner_client_id: str
    web_base_url: str  # the callbacks are served on the web origin, like /auth/callback

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "EntraSettings | None":
        """None until the owner registers both apps (owner steps); onboarding answers 503."""
        names = (
            "ATESTA_M365_SIGNIN_CLIENT_ID",
            "ATESTA_M365_SIGNIN_CLIENT_SECRET",
            "ATESTA_M365_SCANNER_CLIENT_ID",
        )
        if not all(env.get(n) for n in names):
            return None
        return cls(
            env[names[0]], env[names[1]], env[names[2]], env["ATESTA_WEB_BASE_URL"].rstrip("/")
        )


class EntraSignIn:
    """Authorize and consent URLs, code redemption and ID token validation against Entra."""

    def __init__(
        self,
        settings: EntraSettings,
        client: httpx.Client,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._client = client
        self._clock = clock
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None
        self._lock = threading.Lock()

    def authorize_url(self, *, state: str, nonce: str, challenge: str) -> str:
        query = {
            "client_id": self._settings.signin_client_id,
            "response_type": "code",
            "redirect_uri": self._settings.web_base_url + SIGNIN_PATH,
            "response_mode": "query",
            "scope": "openid profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return f"{AUTHORITY}/organizations/oauth2/v2.0/authorize?{urlencode(query)}"

    def consent_url(self, *, tenant_id: str, state: str) -> str:
        query = {
            "client_id": self._settings.scanner_client_id,
            "state": state,
            "redirect_uri": self._settings.web_base_url + CONSENT_PATH,
        }
        return f"{AUTHORITY}/{tenant_id}/adminconsent?{urlencode(query)}"

    def sign_in(self, *, code: str, verifier: str, nonce: str) -> SignedIn:
        form = {
            "client_id": self._settings.signin_client_id,
            "client_secret": self._settings.signin_client_secret,
            "grant_type": "authorization_code",
            "scope": "openid profile",
            "code": code,
            "redirect_uri": self._settings.web_base_url + SIGNIN_PATH,
            "code_verifier": verifier,
        }
        try:
            response = self._client.post(
                f"{AUTHORITY}/organizations/oauth2/v2.0/token", data=form, timeout=10
            )
        except httpx.HTTPError as exc:
            raise MicrosoftUnavailableError from exc
        if response.status_code >= 500:
            raise MicrosoftUnavailableError
        if response.status_code != 200:
            raise SignInError("the code was refused")
        try:
            id_token = str(response.json()["id_token"])
        except (ValueError, KeyError, TypeError) as exc:
            raise SignInError("no ID token") from exc
        return self.validate(id_token, nonce)

    def validate(self, id_token: str, nonce: str) -> SignedIn:
        """Signature, audience, expiry and nonce, then the issuer of the token's own tenant.

        The issuer is checked after the signature, against the verified `tid`: no claim is read
        from an unverified token (multi-tenant issuer validation).
        """
        try:
            header = jwt.get_unverified_header(id_token)  # only `kid` and `alg`, checked below
            if header.get("alg") != "RS256":
                raise SignInError("bad algorithm")
            claims: dict[str, Any] = jwt.decode(
                id_token,
                self._key(str(header.get("kid", ""))),
                algorithms=["RS256"],
                audience=self._settings.signin_client_id,
                leeway=LEEWAY_SECONDS,
                options={
                    "require": ["exp", "iat", "iss", "aud", "tid", "oid", "nonce"],
                    "verify_iss": False,  # checked below against the verified tid
                },
            )
        except jwt.PyJWTError as exc:
            raise SignInError("invalid ID token") from exc
        tenant, object_id = str(claims["tid"]), str(claims["oid"])
        if not _GUID.match(tenant) or claims["iss"] != f"{AUTHORITY}/{tenant}/v2.0":
            raise SignInError("bad tenant or issuer")
        if not _GUID.match(object_id) or not hmac.compare_digest(str(claims["nonce"]), nonce):
            raise SignInError("bad oid or nonce")
        return SignedIn(tenant_id=tenant, object_id=object_id)

    def _key(self, kid: str) -> Any:
        with self._lock:
            if kid in self._keys:
                return self._keys[kid]
            now = self._clock()
            if self._fetched_at is not None and now - self._fetched_at < JWKS_REFETCH_SECONDS:
                raise SignInError("unknown signing key")
            self._fetched_at = now
        try:  # Entra's multi-tenant signing keys
            response = self._client.get(f"{AUTHORITY}/common/discovery/v2.0/keys", timeout=5)
            response.raise_for_status()
            keys = {str(k["kid"]): jwt.PyJWK(k).key for k in response.json()["keys"]}
        except (httpx.HTTPError, ValueError, KeyError, TypeError, jwt.PyJWTError) as exc:
            with self._lock:
                self._fetched_at = None
            raise MicrosoftUnavailableError from exc
        with self._lock:
            self._keys = keys
        if kid not in keys:
            raise SignInError("unknown signing key")
        return keys[kid]
