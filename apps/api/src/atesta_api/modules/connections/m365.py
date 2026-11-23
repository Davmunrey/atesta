"""M365 onboarding steps 2 to 4 (scanner-connectors spec, Microsoft 365 onboarding, #314).

Per-request data travels only in the sealed `atesta_m365` cookie (10 minutes, Path=/auth, no DB
row). The sign-in binds the connection to the Entra tenant of a real admin; the consent callback
is accepted only for that tenant, since Microsoft warns that its `tenant` can be forged. The
callbacks receive Microsoft's query string; the server never logs it (uvicorn --no-access-log,
#257; access-log redaction, #275), and nothing here logs a code or a token (rule 2).

The callbacks are browser navigations, so a refusal redirects to the web connections page with
one code from REFUSALS (web-connections spec, #366); nothing Microsoft sent is reflected.
"""

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from atesta_api.modules.connections.entra import (
    M365Identity,
    MicrosoftUnavailableError,
    SignInError,
)
from atesta_api.modules.connections.models import Connection
from atesta_api.modules.connections.service import ONBOARDING
from atesta_api.modules.identity.api import (
    CurrentCaller,
    Member,
    Role,
    require_member,
    require_role,
)
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession

COOKIE = "atesta_m365"
COOKIE_SECONDS = 600
REFUSALS = frozenset(
    {
        "connections.signin_invalid",
        "connections.consent_denied",
        "connections.tenant_mismatch",
        "connections.microsoft_unavailable",
        "connections.state_invalid",
        "connections.not_found",
        "identity.forbidden",
        "identity.not_found",
        "identity.access_expired",
    }
)

api_router = APIRouter(prefix="/api/v1/orgs/{org_id}/connections", tags=["connections"])
auth_router = APIRouter(prefix="/auth/m365", tags=["auth"])


class M365SignInOut(BaseModel):
    authorize_url: str


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status, detail={"code": code})


def _identity(request: Request) -> M365Identity:
    identity: M365Identity | None = getattr(request.app.state, "m365", None)
    if identity is None:  # the owner has not registered the apps here yet
        raise _error(503, "connections.microsoft_unavailable")
    return identity


def _seal(request: Request, response: Any, pending: dict[str, str]) -> None:
    crypto = request.app.state.session_crypto  # identity's AES-GCM sealing, bound to the name
    value = crypto.seal(COOKIE, json.dumps(pending, sort_keys=True))
    response.set_cookie(
        COOKIE,
        value,
        max_age=COOKIE_SECONDS,
        path="/auth",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def _page(request: Request, query: dict[str, str]) -> RedirectResponse:
    """The web connections page, the single-use cookie deleted."""
    web: str = request.app.state.web_base_url
    response = RedirectResponse(f"{web}/app/connections?{urlencode(query)}", status_code=302)
    response.delete_cookie(COOKIE, path="/auth", secure=True, httponly=True, samesite="lax")
    return response


def _refused(
    request: Request, exc: HTTPException, connection: Connection | None
) -> RedirectResponse:
    """A refusal as a redirect; the org and connection only once the caller was checked."""
    code = exc.detail.get("code") if isinstance(exc.detail, dict) else None
    if code not in REFUSALS:
        raise exc  # not a callback refusal: keep the API's answer
    query = {"error": str(code)}
    if connection is not None:
        query = {"org": str(connection.organization_id), "connection": str(connection.id), **query}
    return _page(request, query)


def _opened(request: Request, state: str) -> dict[str, str]:
    """The sealed pending sign-in, if the cookie opens and `state` matches; else signin_invalid."""
    crypto = request.app.state.session_crypto
    try:
        pending: dict[str, str] = json.loads(crypto.open(COOKIE, request.cookies.get(COOKIE, "")))
    except Exception:  # noqa: BLE001 - any unopenable cookie is the same refusal
        raise _error(400, "connections.signin_invalid") from None
    if not hmac.compare_digest(str(pending.get("state", "")), state):
        raise _error(400, "connections.signin_invalid")
    return pending


def _connection(
    request: Request, caller: CurrentCaller, session: DbSession, pending: dict[str, str]
) -> Connection:
    """The sealed connection, for a caller who is still admin+ of the sealed org."""
    if pending.get("user_id") != str(caller.user_id):
        raise _error(400, "connections.signin_invalid")
    member = require_member(uuid.UUID(pending["org_id"]), request, caller, session)
    if member.role not in (Role.OWNER, Role.ADMIN):
        raise _error(403, "identity.forbidden")
    connection = session.scalars(
        select(Connection).where(
            Connection.organization_id == member.organization_id,
            Connection.id == uuid.UUID(pending["connection_id"]),
        )
    ).one_or_none()
    if connection is None:
        raise _error(404, "connections.not_found")
    if connection.provider != "m365" or connection.status not in ONBOARDING:
        raise _error(409, "connections.state_invalid")
    return connection


@api_router.post("/{connection_id}/m365/signin")
def start_signin(
    connection_id: uuid.UUID,
    request: Request,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> JSONResponse:
    identity = _identity(request)
    connection = session.scalars(
        select(Connection).where(
            Connection.organization_id == member.organization_id, Connection.id == connection_id
        )
    ).one_or_none()
    if connection is None:
        raise _error(404, "connections.not_found")
    if connection.provider != "m365" or connection.status not in ONBOARDING:
        raise _error(409, "connections.state_invalid")
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    url = identity.authorize_url(
        state=state, nonce=nonce, challenge=challenge.rstrip(b"=").decode()
    )
    response = JSONResponse(M365SignInOut(authorize_url=url).model_dump())
    pending = {
        "org_id": str(member.organization_id),
        "connection_id": str(connection.id),
        "user_id": str(member.user_id),
        "state": state,
        "nonce": nonce,
        "verifier": verifier,
    }
    _seal(request, response, pending)
    return response


@auth_router.get("/signin-callback")
def signin_callback(
    request: Request, caller: CurrentCaller, session: DbSession, code: str = "", state: str = ""
) -> RedirectResponse:
    connection: Connection | None = None
    try:
        pending = _opened(request, state)
        connection = _connection(request, caller, session, pending)
        identity = _identity(request)
        try:
            signed_in = identity.sign_in(
                code=code, verifier=pending["verifier"], nonce=pending["nonce"]
            )
        except SignInError:
            raise _error(400, "connections.signin_invalid") from None
        except MicrosoftUnavailableError:
            raise _error(503, "connections.microsoft_unavailable") from None
    except HTTPException as exc:
        return _refused(request, exc, connection)
    consent_state = secrets.token_urlsafe(32)
    resealed = {
        **{k: pending[k] for k in ("org_id", "connection_id", "user_id")},
        "state": consent_state,
        "tid": signed_in.tenant_id,
        "oid": signed_in.object_id,
    }
    response = RedirectResponse(
        identity.consent_url(tenant_id=signed_in.tenant_id, state=consent_state), status_code=302
    )
    _seal(request, response, resealed)
    return response


@auth_router.get("/consent-callback")
def consent_callback(  # noqa: PLR0913 - Microsoft's callback parameters
    request: Request,
    caller: CurrentCaller,
    session: DbSession,
    state: str = "",
    tenant: str = "",
    admin_consent: str = "",
    error: str = "",
) -> RedirectResponse:
    connection: Connection | None = None
    try:
        pending = _opened(request, state)
        if "tid" not in pending:  # a sign-in cookie that never reached Microsoft's sign-in
            raise _error(400, "connections.signin_invalid")
        connection = _connection(request, caller, session, pending)
        if error or admin_consent != "True":
            raise _error(400, "connections.consent_denied")
        if not hmac.compare_digest(tenant, pending["tid"]):
            raise _error(409, "connections.tenant_mismatch")
        if connection.external_tenant_id not in (None, pending["tid"]):  # the tenant pin holds
            raise _error(409, "connections.tenant_mismatch")
    except HTTPException as exc:
        return _refused(request, exc, connection)
    connection.ms_tenant_id = pending["tid"]
    connection.consented_by_oid = pending["oid"]
    session.flush()
    record(
        session,
        organization_id=connection.organization_id,
        action="connection.consent_granted",
        target_type="connection",
        target_id=str(connection.id),
        actor_user_id=caller.user_id,
        metadata={"provider": "m365"},
    )
    return _page(
        request, {"org": str(connection.organization_id), "connection": str(connection.id)}
    )
