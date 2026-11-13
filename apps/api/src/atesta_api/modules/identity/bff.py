"""Backend for frontend (web-shell spec): the API signs users in and keeps the tokens.

Tokens live only in AES-GCM sealed, HttpOnly cookies; the browser never reads them. Nothing
here logs a token, a cookie or a code.
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from atesta_api.modules.identity.cognito import InvalidTokenError, TokenSet, TokenVerifier

AUTH_COOKIE = "atesta_auth"  # pending sign-in: state, nonce, PKCE verifier, return path
ACCESS_COOKIE = "atesta_at"
REFRESH_COOKIE = "atesta_rt"
SESSION_SECONDS = 12 * 3600  # refresh token lifetime (identity spec)
LOGIN_SECONDS = 600

__all__ = ["ACCESS_COOKIE", "AUTH_COOKIE", "REFRESH_COOKIE", "SessionCrypto", "TokenSet"]


class OAuthClient(Protocol):
    def authorize_url(self, *, state: str, nonce: str, challenge: str, lang: str) -> str: ...
    def exchange_code(self, code: str, verifier: str) -> TokenSet: ...
    def id_token_nonce(self, id_token: str) -> str: ...
    def refresh(self, refresh_token: str) -> TokenSet: ...
    def logout_url(self) -> str: ...


class SessionCrypto:
    """Seals a value for one cookie name; a value moved to another cookie does not open."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("session key must be 32 bytes")
        self._aead = AESGCM(key)

    def seal(self, name: str, value: str) -> str:
        nonce = os.urandom(12)
        sealed = nonce + self._aead.encrypt(nonce, value.encode(), name.encode())
        return base64.urlsafe_b64encode(sealed).decode().rstrip("=")

    def open(self, name: str, sealed: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(sealed + "=" * (-len(sealed) % 4))
            return self._aead.decrypt(raw[:12], raw[12:], name.encode()).decode()
        except (binascii.Error, InvalidTag, ValueError, UnicodeDecodeError) as exc:
            raise InvalidTokenError("invalid session cookie") from exc


class SessionEndedError(HTTPException):
    """401 that also clears the session cookies (expired refresh, tampered cookie)."""

    def __init__(self) -> None:
        super().__init__(status_code=401, detail={"code": "auth.invalid_token"})


def session_ended_handler(request: Request, exc: Exception) -> Response:
    response = JSONResponse({"detail": {"code": "auth.invalid_token"}}, status_code=401)
    clear_session(response)
    return response


def set_cookie(response: Response, name: str, value: str, max_age: int, path: str = "/") -> None:
    response.set_cookie(
        name, value, max_age=max_age, path=path, secure=True, httponly=True, samesite="lax"
    )


def clear_session(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")


def store_tokens(response: Response, crypto: SessionCrypto, tokens: TokenSet) -> None:
    set_cookie(
        response, ACCESS_COOKIE, crypto.seal(ACCESS_COOKIE, tokens.access_token), SESSION_SECONDS
    )
    if tokens.refresh_token:
        sealed = crypto.seal(REFRESH_COOKIE, tokens.refresh_token)
        set_cookie(response, REFRESH_COOKIE, sealed, SESSION_SECONDS)


def _safe_return(target: str | None) -> str:
    """Only same-site absolute paths: no scheme, no '//' host, no backslash tricks."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return "/app"


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(request: Request, lang: str = "es", return_to: str | None = None) -> RedirectResponse:
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    oauth: OAuthClient = request.app.state.oauth
    url = oauth.authorize_url(
        state=state, nonce=nonce, challenge=challenge, lang="en" if lang == "en" else "es"
    )
    pending = json.dumps(
        {"state": state, "nonce": nonce, "verifier": verifier, "return_to": _safe_return(return_to)}
    )
    response = RedirectResponse(url, status_code=302)
    crypto: SessionCrypto = request.app.state.session_crypto
    set_cookie(response, AUTH_COOKIE, crypto.seal(AUTH_COOKIE, pending), LOGIN_SECONDS, "/auth")
    return response


@router.get("/callback")
def callback(request: Request, code: str, state: str) -> RedirectResponse:
    crypto: SessionCrypto = request.app.state.session_crypto
    oauth: OAuthClient = request.app.state.oauth
    verifier: TokenVerifier = request.app.state.token_verifier
    try:
        pending = json.loads(crypto.open(AUTH_COOKIE, request.cookies.get(AUTH_COOKIE, "")))
    except InvalidTokenError:
        raise _error(400, "auth.bad_state") from None
    if not hmac.compare_digest(str(pending["state"]), state):
        raise _error(400, "auth.bad_state")
    try:
        tokens = oauth.exchange_code(code, pending["verifier"])
        nonce = oauth.id_token_nonce(tokens.id_token or "")
        verifier.verify(tokens.access_token)
    except InvalidTokenError:
        raise _error(401, "auth.invalid_token") from None
    if not hmac.compare_digest(nonce, str(pending["nonce"])):
        raise _error(400, "auth.bad_nonce")
    response = RedirectResponse(pending["return_to"], status_code=302)
    store_tokens(response, crypto, tokens)
    response.delete_cookie(AUTH_COOKIE, path="/auth", secure=True, httponly=True, samesite="lax")
    return response


@router.get("/logout")
def logout(request: Request) -> RedirectResponse:
    oauth: OAuthClient = request.app.state.oauth
    response = RedirectResponse(oauth.logout_url(), status_code=302)
    clear_session(response)
    return response
