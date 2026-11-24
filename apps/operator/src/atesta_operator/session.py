"""The staff session: backend for frontend, as the console's (ADR-017, "Staff identity"; spec,
"Session cookie" and "Session limits").

- **Cookies:** their own names and key; host-only (no Domain), HttpOnly, Secure and
  `SameSite=Strict`. The pending sign-in cookie alone is `Lax` and scoped to `/auth`: the staff
  pool's redirect back is a cross-site navigation, and a Strict cookie would not come with it.
  It holds the state, nonce and PKCE verifier, never a token.
- **Limits:** the session cookie seals when it started and when it was last used. A request
  more than 30 minutes after the last one, or 8 hours after sign-in, ends it: 401 and every
  session cookie cleared. Each request moves "last used".
- **Writes:** a cookie-authenticated write must carry the portal's origin (403 `auth.bad_origin`).

Nothing here logs a token, a cookie or a code.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

from atesta_api.modules.identity.api import (
    CognitoOAuth,
    ExpiredTokenError,
    InvalidTokenError,
    ProviderUnavailableError,
    SessionCrypto,
    TokenSet,
    TokenVerifier,
    safe_return,
)
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

LOGIN_COOKIE = "atesta_op_login"
ACCESS_COOKIE = "atesta_op_at"
REFRESH_COOKIE = "atesta_op_rt"
TIMES_COOKIE = "atesta_op_session"
SESSION_COOKIES = (ACCESS_COOKIE, REFRESH_COOKIE, TIMES_COOKIE)
IDLE_SECONDS = 30 * 60
TOTAL_SECONDS = 8 * 3600
LOGIN_SECONDS = 600
WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_log = logging.getLogger(__name__)


class SessionEndedError(Exception):
    """Idle, too old, tampered or refused at refresh: 401, and the cookies are cleared."""


def session_ended_handler(request: Request, exc: Exception) -> Response:
    response = JSONResponse({"detail": {"code": "auth.invalid_token"}}, status_code=401)
    _clear(response)
    return response


def _set(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name, value, max_age=max_age, path="/", secure=True, httponly=True, samesite="strict"
    )


def _clear(response: Response) -> None:
    for name in SESSION_COOKIES:
        response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="strict")


def _seal(request: Request, name: str, value: str) -> str:
    crypto: SessionCrypto = request.app.state.session_crypto
    return crypto.seal(name, value)


def _open(request: Request, name: str) -> str:
    crypto: SessionCrypto = request.app.state.session_crypto
    try:
        return crypto.open(name, request.cookies.get(name, ""))
    except InvalidTokenError:
        raise SessionEndedError from None


def _store(request: Request, response: Response, tokens: TokenSet, started: float) -> None:
    left = max(int(started + TOTAL_SECONDS - time.time()), 0)
    _set(response, ACCESS_COOKIE, _seal(request, ACCESS_COOKIE, tokens.access_token), left)
    if tokens.refresh_token:
        _set(response, REFRESH_COOKIE, _seal(request, REFRESH_COOKIE, tokens.refresh_token), left)
    times = json.dumps({"started": started, "seen": time.time()})
    _set(response, TIMES_COOKIE, _seal(request, TIMES_COOKIE, times), left)


def has_session(request: Request) -> bool:
    return ACCESS_COOKIE in request.cookies


def session_token(request: Request, response: Response) -> str:
    """The access token of a live session, refreshed once if it expired; moves "last used"."""
    if request.method in WRITES and request.headers.get("origin") != request.app.state.web_origin:
        raise HTTPException(status_code=403, detail={"code": "auth.bad_origin"})
    try:
        times = json.loads(_open(request, TIMES_COOKIE))
        started, seen = float(times["started"]), float(times["seen"])
    except (ValueError, KeyError, TypeError):
        raise SessionEndedError from None
    now = time.time()
    if now - seen > IDLE_SECONDS or now - started > TOTAL_SECONDS:
        raise SessionEndedError
    verifier: TokenVerifier = request.app.state.token_verifier
    tokens = TokenSet(_open(request, ACCESS_COOKIE), None, None)
    try:
        verifier.verify(tokens.access_token)
    except ExpiredTokenError:
        oauth: CognitoOAuth = request.app.state.oauth
        try:
            tokens = oauth.refresh(_open(request, REFRESH_COOKIE))
            verifier.verify(tokens.access_token)
        except InvalidTokenError:
            raise SessionEndedError from None
    except InvalidTokenError:
        raise SessionEndedError from None
    _store(request, response, tokens, started)
    return tokens.access_token


router = APIRouter(prefix="/auth", tags=["auth"])


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


@router.get("/login")
def login(request: Request, lang: str = "es", return_to: str | None = None) -> RedirectResponse:
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    oauth: CognitoOAuth = request.app.state.oauth
    url = oauth.authorize_url(
        state=state, nonce=nonce, challenge=challenge, lang="en" if lang == "en" else "es"
    )
    pending = {"state": state, "nonce": nonce, "verifier": verifier}
    pending["return_to"] = safe_return(return_to, fallback="/")
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        LOGIN_COOKIE,
        _seal(request, LOGIN_COOKIE, json.dumps(pending)),
        max_age=LOGIN_SECONDS,
        path="/auth",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/callback")
def callback(request: Request, code: str, state: str) -> RedirectResponse:
    crypto: SessionCrypto = request.app.state.session_crypto
    oauth: CognitoOAuth = request.app.state.oauth
    verifier: TokenVerifier = request.app.state.token_verifier
    try:
        pending = json.loads(crypto.open(LOGIN_COOKIE, request.cookies.get(LOGIN_COOKIE, "")))
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
    _store(request, response, tokens, time.time())
    response.delete_cookie(LOGIN_COOKIE, path="/auth", secure=True, httponly=True, samesite="lax")
    return response


@router.get("/logout")
def logout(request: Request) -> RedirectResponse:
    """Revoke the refresh token (best effort), clear the cookies, end the managed login."""
    oauth: CognitoOAuth = request.app.state.oauth
    sealed = request.cookies.get(REFRESH_COOKIE)
    if sealed:
        crypto: SessionCrypto = request.app.state.session_crypto
        try:
            oauth.revoke(crypto.open(REFRESH_COOKIE, sealed))
        except (InvalidTokenError, ProviderUnavailableError) as exc:
            _log.warning("sign-out: refresh token not revoked (%s)", type(exc).__name__)
    response = RedirectResponse(oauth.logout_url(), status_code=302)
    _clear(response)
    return response
