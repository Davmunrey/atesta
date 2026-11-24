"""The verifier's Google token: a JWT bearer grant with the org's service account key (D7, D9).

Follows Google's "Using OAuth 2.0 for Server to Server Applications" HTTP/REST steps (updated
2026-11-19): an RS256 JWT with `kid`, `iss`, `sub`, `scope`, `aud`, `iat` and `exp` one hour
later, posted to the one token URL. The key's own `token_uri` is never followed, so the key is
only ever presented to Google. Google's `error` decides the outcome; its description is compared
and dropped, never stored or logged (it can echo the subject). See the spec's Google verifier
contract for the table this module implements.
"""

import base64
import json
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

import httpx
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from atesta_scanner.entra_token import TokenTransientError, TokenUnavailableError

TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - a public URL, not a secret
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"
LIFETIME_S = 3600  # Google's maximum for the assertion
_CLIENT_ID = re.compile(r"[0-9]{6,30}")
_NOT_AUTHORIZED = frozenset({"unauthorized_client", "access_denied"})
REFUSALS = frozenset({"not_authorized", "blocked_by_policy", "delegated_user"})


class TokenRefusedError(Exception):
    """Google refused the delegation for a reason the customer can fix (one of REFUSALS)."""

    def __init__(self, reason: str) -> None:
        if reason not in REFUSALS:
            raise ValueError("unknown refusal")
        super().__init__(f"google refused the delegation: {reason}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ServiceAccountKey:
    client_email: str
    client_id: str  # the numeric OAuth client id the customer authorizes for delegation
    private_key_id: str
    private_key: rsa.RSAPrivateKey = field(repr=False)


def _unavailable(message: str) -> TokenUnavailableError:
    return TokenUnavailableError(message)


def load_key(raw: str) -> ServiceAccountKey:
    """A service account JSON key. Errors never carry any part of it (rule 2)."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise _unavailable("the service account key is not JSON") from None
    if not isinstance(data, dict) or data.get("type") != "service_account":
        raise _unavailable("the credential is not a service account key")
    values = [data.get(name) for name in ("client_email", "client_id", "private_key_id")]
    pem = data.get("private_key")
    if not all(isinstance(value, str) and value for value in [*values, pem]):
        raise _unavailable("the service account key lacks a field")
    email, client_id, key_id = (str(value) for value in values)
    if not _CLIENT_ID.fullmatch(client_id):
        raise _unavailable("the service account client id is not numeric")
    try:
        private = serialization.load_pem_private_key(str(pem).encode(), password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm):
        raise _unavailable("the service account private key does not load") from None
    if not isinstance(private, rsa.RSAPrivateKey):
        raise _unavailable("the service account private key is not RSA")
    return ServiceAccountKey(email, client_id, key_id, private)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _part(value: Mapping[str, object]) -> str:
    return _b64(json.dumps(value, separators=(",", ":")).encode())


def assertion(key: ServiceAccountKey, subject: str, scopes: Iterable[str], now: int) -> str:
    header = {"alg": "RS256", "typ": "JWT", "kid": key.private_key_id}
    claims = {
        "iss": key.client_email,
        "sub": subject,
        "scope": " ".join(sorted(scopes)),
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + LIFETIME_S,
    }
    signing_input = f"{_part(header)}.{_part(claims)}"
    signature = key.private_key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64(signature)}"


def _refusal(body: dict[str, object]) -> Exception:
    error, description = body.get("error"), body.get("error_description")
    if error in _NOT_AUTHORIZED:
        return TokenRefusedError("not_authorized")  # no DWD entry yet, or not propagated
    if error == "admin_policy_enforced":
        return TokenRefusedError("blocked_by_policy")
    if error == "invalid_grant" and not (
        isinstance(description, str) and description.startswith("Invalid JWT")
    ):
        return TokenRefusedError("delegated_user")  # Google: the user does not exist
    # Clock, signature, a deleted client or key, a bad scope, anything new: Atesta's credential.
    return _unavailable("google refused atesta's service account credential")


def delegated_token(
    client: httpx.Client,
    key: ServiceAccountKey,
    subject: str,
    scopes: Iterable[str],
    clock: Callable[[], float] = time.time,
) -> str:
    """An access token as `subject` for exactly `scopes` (Google requires them all authorized)."""
    grant = {"grant_type": GRANT_TYPE, "assertion": assertion(key, subject, scopes, int(clock()))}
    try:
        response = client.post(TOKEN_URL, data=grant, headers={"Accept": "application/json"})
    except httpx.HTTPError:
        raise TokenTransientError("the google token endpoint is unreachable") from None
    status = response.status_code
    if status == 429 or status >= 500:
        raise TokenTransientError(f"the google token endpoint answered {status}")
    try:
        body = response.json()
    except ValueError:
        raise TokenTransientError("the google token endpoint answered with no JSON") from None
    if not isinstance(body, dict):
        raise TokenTransientError("the google token endpoint answered with no object")
    token = body.get("access_token")
    if status == 200 and isinstance(token, str) and token:
        return token
    raise _refusal(body) from None
