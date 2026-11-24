"""Microsoft Entra sign-in for M365 onboarding (scanner-connectors spec, Microsoft 365 onboarding).

Two app registrations in Atesta's tenant: "Atesta Sign-in" (openid profile, no application
permissions) binds a connection to the tenant of a real admin, and "Atesta Scanner" receives the
admin consent. The Sign-in app redeems codes as a confidential web client with a certificate
credential, never a client secret (issue 363): Microsoft says secrets "should not be used in
production environments" (Add credentials to your application, read 2026-11-23). The assertion
follows "Assertion format" in Microsoft's certificate credentials page (read 2026-11-24).
Nothing here logs a code, a token, an assertion or the key (rule 2).
"""

import base64
import binascii
import hmac
import os
import re
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12

AUTHORITY = "https://login.microsoftonline.com"
SIGNIN_PATH = "/auth/m365/signin-callback"
CONSENT_PATH = "/auth/m365/consent-callback"
TOKEN_ENDPOINT = f"{AUTHORITY}/organizations/oauth2/v2.0/token"
JWKS_REFETCH_SECONDS = 300
LEEWAY_SECONDS = 60
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
ASSERTION_SECONDS = 300  # Microsoft: "5-10 minutes after nbf at most"
MIN_RSA_BITS = 2048
_CERTIFICATE = "ATESTA_M365_SIGNIN_CERTIFICATE"
_RETIRED_SECRET = "ATESTA_M365_SIGNIN_CLIENT_SECRET"  # noqa: S105 - a variable name, not a secret
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
class SigninCertificate:
    """The Sign-in app's key and what the assertion says about its certificate."""

    private_key: rsa.RSAPrivateKey = field(repr=False)
    thumbprint: str  # the x5t#S256 header: SHA-256 of the certificate's DER, base64url
    not_after: datetime

    @classmethod
    def from_pfx_base64(cls, value: str) -> "SigninCertificate":
        """Read a passwordless PFX (base64), the format of the Scanner app's certificate.

        Every refusal names the variable and never the content or the library's message, which
        could carry key material (rule 2).
        """
        try:
            key, certificate, _ = pkcs12.load_key_and_certificates(
                base64.b64decode(value, validate=True), None
            )
        except (binascii.Error, ValueError, TypeError):
            raise ValueError(f"{_CERTIFICATE} is not a passwordless base64 PFX") from None
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < MIN_RSA_BITS:
            raise ValueError(f"{_CERTIFICATE} needs an RSA key of at least {MIN_RSA_BITS} bits")
        if certificate is None:
            raise ValueError(f"{_CERTIFICATE} holds no certificate")
        # Encoded as Microsoft's own library does (MSAL for Python 1.39.0, assertion.py).
        thumbprint = base64.urlsafe_b64encode(certificate.fingerprint(hashes.SHA256())).decode()
        return cls(key, thumbprint, certificate.not_valid_after_utc)


@dataclass(frozen=True, slots=True)
class EntraSettings:
    signin_client_id: str
    signin_certificate: SigninCertificate = field(repr=False)
    scanner_client_id: str
    web_base_url: str  # the callbacks are served on the web origin, like /auth/callback

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "EntraSettings | None":
        """None until the owner registers both apps (owner steps); onboarding answers 503.

        ValueError, so the API does not start, when the certificate is unusable or the retired
        client secret is still configured: it must be deleted, here and in Entra (issue 363).
        """
        if env.get(_RETIRED_SECRET):
            raise ValueError(
                f"{_RETIRED_SECRET} is no longer used: delete it and the secret in Entra;"
                f" the Sign-in app authenticates with {_CERTIFICATE}"
            )
        names = ("ATESTA_M365_SIGNIN_CLIENT_ID", _CERTIFICATE, "ATESTA_M365_SCANNER_CLIENT_ID")
        if not all(env.get(n) for n in names):
            return None
        return cls(
            env[names[0]],
            SigninCertificate.from_pfx_base64(env[names[1]]),
            env[names[2]],
            env["ATESTA_WEB_BASE_URL"].rstrip("/"),
        )


class EntraSignIn:
    """Authorize and consent URLs, code redemption and ID token validation against Entra."""

    def __init__(
        self,
        settings: EntraSettings,
        client: httpx.Client,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._client = client
        self._clock = clock
        self._now = now
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

    def _assertion(self) -> str:
        """A fresh client assertion: PS256, the certificate's thumbprint, five minutes."""
        certificate = self._settings.signin_certificate
        now = int(self._now())
        if now >= certificate.not_after.timestamp():
            raise MicrosoftUnavailableError  # an expired certificate: Microsoft is not called
        claims = {
            "aud": TOKEN_ENDPOINT,
            "iss": self._settings.signin_client_id,
            "sub": self._settings.signin_client_id,
            "jti": str(uuid.uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + ASSERTION_SECONDS,
        }
        return jwt.encode(
            claims,
            certificate.private_key,
            algorithm="PS256",
            headers={"typ": "JWT", "x5t#S256": certificate.thumbprint},
        )

    def sign_in(self, *, code: str, verifier: str, nonce: str) -> SignedIn:
        form = {
            "client_id": self._settings.signin_client_id,
            "client_assertion_type": ASSERTION_TYPE,
            "client_assertion": self._assertion(),
            "grant_type": "authorization_code",
            "scope": "openid profile",
            "code": code,
            "redirect_uri": self._settings.web_base_url + SIGNIN_PATH,
            "code_verifier": verifier,
        }
        try:
            response = self._client.post(TOKEN_ENDPOINT, data=form, timeout=10)
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
