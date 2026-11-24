"""API keys for a customer's own tools and AI agents (evidence-ingestion-api, api-keys-v2).

Admins create and revoke them; the key is shown once and only its SHA-256 is kept. A key carries
explicit scopes and its own rate limit. Resolving one reads it through the named policy
api_token_read, then enters the organization's context (ADR-012 amendments 5 and 6). Every
accepted request is one usage row: route template and scope, never content (rule 2).
"""

import math
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Receive, Send
from starlette.types import Scope as Scope_

from atesta_api.modules.identity.agent_oauth import AgentOAuth, grant_digest
from atesta_api.modules.identity.context import (
    ContextReason,
    enter_api_token_context,
    enter_org_context,
)
from atesta_api.modules.identity.deps import Member, error, require_role
from atesta_api.modules.identity.invitations import QueryFreeRoute, token_hash
from atesta_api.modules.identity.models import (
    READ_SCOPES,
    SCOPES,
    ApiToken,
    ApiTokenUsage,
    Membership,
    Role,
    User,
)
from atesta_api.modules.identity.standing import enforce
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession
from atesta_api.platform.i18n import accepted_locale, message

router = APIRouter()  # mounted under /v1 by routes.py

TOKEN_PREFIX = "atesta_"  # noqa: S105 - a public marker, not a secret
PREFIX_LENGTH = 12
WINDOW = timedelta(seconds=60)
USAGE_SHOWN = 100
# Set on the ASGI scope by the hosted MCP server's in-process hand-off only (`as_agent`): the
# digest of an agent token it has already verified. A request from outside cannot set a scope
# key, and no header is ever read for this (mcp-oauth spec).
AGENT_SCOPE_KEY = "atesta.agent_grant"
GRANT_PREFIX = "oauth_"
USAGE_RETENTION = timedelta(days=90)  # the `retention` policy holds the same limit in Postgres

type Scope = Literal[
    "compliance:read", "incidents:read", "evidence:write", "assessment:propose", "routines:write"
]


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expires_in_days: int = Field(ge=1, le=365)
    scopes: list[Scope] = Field(min_length=1, max_length=len(SCOPES))
    rate_limit_per_minute: int = Field(default=60, ge=1, le=600)

    @field_validator("scopes")
    @classmethod
    def distinct(cls, value: list[Scope]) -> list[Scope]:
        if len(set(value)) != len(value):
            raise ValueError("a scope is repeated")
        return sorted(value, key=SCOPES.index)

    @field_validator("name")
    @classmethod
    def tidy(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("the name is empty")
        return cleaned


class TokenOut(BaseModel):
    id: uuid.UUID
    kind: Literal["key", "oauth"] = "key"
    client_id: str | None = None  # the approved client of an OAuth grant
    name: str
    prefix: str
    scopes: list[str]
    rate_limit_per_minute: int
    read_only: bool
    created_by_email: str
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class CreatedToken(TokenOut):
    token: str  # shown once; the API keeps only its SHA-256


def _out(row: ApiToken, email: str) -> TokenOut:
    return TokenOut(
        id=row.id,
        kind="oauth" if row.kind == "oauth" else "key",
        client_id=row.oauth_client_id,
        name=row.name,
        prefix=row.prefix,
        scopes=row.scopes,
        rate_limit_per_minute=row.rate_limit_per_minute,
        read_only=set(row.scopes) <= set(READ_SCOPES),
        created_by_email=email,
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


@router.post("/orgs/{org_id}/api-tokens", status_code=201)
def create_token(
    body: TokenIn, member: Annotated[Member, Depends(require_role(Role.ADMIN))], session: DbSession
) -> CreatedToken:
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    row = ApiToken(
        organization_id=member.organization_id,
        name=body.name,
        prefix=token[:PREFIX_LENGTH],
        token_sha256=token_hash(token),
        scopes=list(body.scopes),
        rate_limit_per_minute=body.rate_limit_per_minute,
        created_by=member.user_id,
        created_at=now,
        expires_at=now + timedelta(days=body.expires_in_days),
    )
    session.add(row)
    session.flush()
    record(
        session,
        organization_id=member.organization_id,
        action="api_token.created",
        target_type="api_token",
        target_id=str(row.id),
        actor_user_id=member.user_id,
        metadata={
            "prefix": row.prefix,
            "expires_in_days": body.expires_in_days,
            "scopes": " ".join(body.scopes),
            "rate_limit_per_minute": body.rate_limit_per_minute,
        },
    )
    email = session.scalar(select(User.email).where(User.id == member.user_id)) or ""
    return CreatedToken(**_out(row, email).model_dump(), token=token)


@router.get("/orgs/{org_id}/api-tokens")
def list_tokens(
    member: Annotated[Member, Depends(require_role(Role.ADMIN))], session: DbSession
) -> list[TokenOut]:
    rows = session.execute(
        select(ApiToken, User.email)
        .join(User, User.id == ApiToken.created_by)
        .where(ApiToken.organization_id == member.organization_id)
        .order_by(ApiToken.created_at.desc(), ApiToken.id)
    )
    return [_out(row, email) for row, email in rows]


@router.delete("/orgs/{org_id}/api-tokens/{token_id}", status_code=204)
def revoke_token(
    token_id: uuid.UUID,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> Response:
    revoked = session.execute(
        update(ApiToken)
        .where(
            ApiToken.organization_id == member.organization_id,
            ApiToken.id == token_id,
            ApiToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC), revoked_by=member.user_id)
        .returning(ApiToken.prefix, ApiToken.kind, ApiToken.oauth_client_id)
    ).first()
    if revoked is None:
        raise error(404, "identity.not_found")
    is_grant = revoked.kind == "oauth"
    record(
        session,
        organization_id=member.organization_id,
        action="agent_grant.revoked" if is_grant else "api_token.revoked",
        target_type="api_token",
        target_id=str(token_id),
        actor_user_id=member.user_id,
        metadata={"prefix": revoked.prefix}
        | ({"client_id": revoked.oauth_client_id} if is_grant else {}),
    )
    return Response(status_code=204)


class AgentClient(BaseModel):
    client_id: str
    name: str


class GrantIn(BaseModel):
    client_id: str = Field(min_length=1, max_length=128)
    expires_in_days: int = Field(ge=1, le=365)
    scopes: list[Scope] = Field(min_length=1, max_length=len(SCOPES))
    rate_limit_per_minute: int = Field(default=60, ge=1, le=600)

    @field_validator("scopes")
    @classmethod
    def distinct(cls, value: list[Scope]) -> list[Scope]:
        if len(set(value)) != len(value):
            raise ValueError("a scope is repeated")
        return sorted(value, key=SCOPES.index)


def agent_oauth(request: Request) -> AgentOAuth | None:
    """OAuth for the hosted MCP server, or None while it is off (mcp-oauth spec)."""
    found: AgentOAuth | None = getattr(request.app.state, "agent_oauth", None)
    return found


@router.get("/orgs/{org_id}/agent-clients")
def list_agent_clients(
    request: Request, member: Annotated[Member, Depends(require_role(Role.ADMIN))]
) -> list[AgentClient]:
    """The approved clients an admin may grant; empty while OAuth is off."""
    oauth = agent_oauth(request)
    clients = {} if oauth is None else oauth.clients
    return [AgentClient(client_id=key, name=name) for key, name in clients.items()]


@router.post("/orgs/{org_id}/agent-grants", status_code=201)
def create_agent_grant(
    body: GrantIn,
    request: Request,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> TokenOut:
    """The caller lets one approved client act for them in this organization: the consent.

    A grant is an API key without a secret (ADR-016 amendment 1): it is found by the digest of
    the issuer, the client and the person, which the hosted server derives from a verified token.
    """
    oauth = agent_oauth(request)
    if oauth is None:
        raise error(409, "identity.agent_oauth_off")
    if body.client_id not in oauth.clients:
        raise error(422, "identity.agent_client_unknown")
    person = session.execute(
        select(User.cognito_sub, User.email).where(User.id == member.user_id)
    ).one()
    digest = grant_digest(oauth.issuer, body.client_id, person.cognito_sub)
    now = datetime.now(UTC)
    active = session.scalar(
        select(ApiToken.id).where(
            ApiToken.organization_id == member.organization_id,
            ApiToken.token_sha256 == digest,
            ApiToken.kind == "oauth",
            ApiToken.revoked_at.is_(None),
            ApiToken.expires_at > now,
        )
    )
    if active is not None:
        raise error(409, "identity.agent_grant_exists")
    row = ApiToken(
        organization_id=member.organization_id,
        kind="oauth",
        oauth_client_id=body.client_id,
        name=oauth.clients[body.client_id][:100],
        prefix=GRANT_PREFIX + digest[: PREFIX_LENGTH - len(GRANT_PREFIX)],
        token_sha256=digest,
        scopes=list(body.scopes),
        rate_limit_per_minute=body.rate_limit_per_minute,
        created_by=member.user_id,
        created_at=now,
        expires_at=now + timedelta(days=body.expires_in_days),
    )
    session.add(row)
    session.flush()
    record(
        session,
        organization_id=member.organization_id,
        action="agent_grant.created",
        target_type="api_token",
        target_id=str(row.id),
        actor_user_id=member.user_id,
        metadata={
            "prefix": row.prefix,
            "client_id": body.client_id,
            "expires_in_days": body.expires_in_days,
            "scopes": " ".join(body.scopes),
            "rate_limit_per_minute": body.rate_limit_per_minute,
        },
    )
    return _out(row, person.email)


class UsageRow(BaseModel):
    at: datetime
    method: str
    route: str
    scope: str | None


class UsageOut(BaseModel):
    last_24h: int
    recent: list[UsageRow]


@router.get("/orgs/{org_id}/api-tokens/{token_id}/usage")
def token_usage(
    token_id: uuid.UUID,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> UsageOut:
    org = member.organization_id
    known = session.scalar(
        select(ApiToken.id).where(ApiToken.organization_id == org, ApiToken.id == token_id)
    )
    if known is None:
        raise error(404, "identity.not_found")
    mine = (ApiTokenUsage.organization_id == org, ApiTokenUsage.token_id == token_id)
    since = datetime.now(UTC) - timedelta(hours=24)
    count = session.scalar(select(func.count()).where(*mine, ApiTokenUsage.at > since)) or 0
    rows = session.scalars(
        select(ApiTokenUsage)
        .where(*mine)
        .order_by(ApiTokenUsage.at.desc(), ApiTokenUsage.id)
        .limit(USAGE_SHOWN)
    )
    return UsageOut(
        last_24h=count, recent=[UsageRow.model_validate(r, from_attributes=True) for r in rows]
    )


def expire_key_usage(session: Session, organization_id: uuid.UUID, *, now: datetime) -> int:
    """Delete the organization's usage rows older than 90 days; returns how many went.

    For the daily job, in the organization's context. The database decides what may go: the
    `retention` policy hides younger rows from DELETE and tenant_isolation hides other
    organizations, so a wrong `now` or id here deletes nothing extra (ADR-012 amendment 9).
    """
    gone = (
        delete(ApiTokenUsage)
        .where(
            ApiTokenUsage.organization_id == organization_id,
            ApiTokenUsage.at < now - USAGE_RETENTION,
        )
        .returning(ApiTokenUsage.id)
        .cte("gone")
    )
    # Counted in the database: the deleted ids never travel to the worker.
    return session.scalar(select(func.count()).select_from(gone)) or 0


@dataclass(frozen=True, slots=True)
class ApiCaller:
    """Who an accepted API key speaks for: its organization, and the admin who created it."""

    organization_id: uuid.UUID
    token_id: uuid.UUID
    prefix: str
    created_by: uuid.UUID
    scopes: tuple[str, ...]
    rate_limit_per_minute: int


def _error(
    status: int, code: str, request: Request, headers: dict[str, str] | None = None, **values: str
) -> HTTPException:
    """A key's 401, 403 and 429 carry the reason in the caller's language (api-keys-v2 spec)."""
    locale = accepted_locale(request.headers.get("accept-language"))
    text = message(locale, f"api_token.{code.removeprefix('identity.api_token_')}")
    detail = {"code": code, "message": text.format(**values), **values}
    return HTTPException(status, detail=detail, headers=headers)


def as_agent(app: ASGIApp, digest: str) -> ASGIApp:
    """The API, entered as the agent whose token the hosted MCP server has verified.

    In-process only: the digest travels on the ASGI scope, which no network request can set.
    """

    async def entered(scope: Scope_, receive: Receive, send: Send) -> None:
        await app({**scope, AGENT_SCOPE_KEY: digest}, receive, send)

    return entered


def _grant(request: Request, session: DbSession, digest: str) -> ApiToken:
    """The one active grant of a verified person and client, while that person is still an
    owner or admin of its organization. Anything else is the 401 of a bad key."""
    enter_api_token_context(session, digest)
    now = datetime.now(UTC)
    found = session.scalars(
        select(ApiToken).where(
            ApiToken.token_sha256 == digest,
            ApiToken.kind == "oauth",
            ApiToken.revoked_at.is_(None),
            ApiToken.expires_at > now,
        )
    ).all()
    if len(found) != 1:  # none, or the same person and client in two organizations
        raise _error(401, "identity.api_token_invalid", request)
    row = found[0]
    enter_org_context(session, row.organization_id, ContextReason.API_TOKEN)
    standing = session.execute(
        select(Membership.role, Membership.access_expires_at).where(
            Membership.organization_id == row.organization_id,
            Membership.user_id == row.created_by,
        )
    ).first()
    if (
        standing is None
        or Role(standing.role) not in (Role.OWNER, Role.ADMIN)
        or (standing.access_expires_at is not None and standing.access_expires_at <= now)
    ):
        raise _error(401, "identity.api_token_invalid", request)
    return row


def require_api_token(request: Request, session: DbSession) -> ApiCaller:
    """401 identity.api_token_invalid for a missing, unknown, revoked or expired key alike."""
    now = datetime.now(UTC)
    agent = request.scope.get(AGENT_SCOPE_KEY)
    if isinstance(agent, str):
        row = _grant(request, session, agent)
    else:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.startswith(TOKEN_PREFIX) or len(token) > 200:
            raise _error(401, "identity.api_token_invalid", request)
        digest = token_hash(token)
        enter_api_token_context(session, digest)
        found = session.scalar(
            select(ApiToken).where(ApiToken.token_sha256 == digest, ApiToken.kind == "key")
        )
        if found is None or found.revoked_at is not None or found.expires_at <= now:
            raise _error(401, "identity.api_token_invalid", request)
        row = found
        enter_org_context(session, row.organization_id, ContextReason.API_TOKEN)
    language = accepted_locale(request.headers.get("accept-language"))
    enforce(
        session,
        row.organization_id,
        method=request.method,
        path=request.url.path,
        owner=False,
        language=language,
    )
    # Taking the row lock serializes this key's requests: idempotency and rate counts hold.
    session.execute(
        update(ApiToken)
        .where(ApiToken.organization_id == row.organization_id, ApiToken.id == row.id)
        .values(last_used_at=now)
    )
    return ApiCaller(
        row.organization_id,
        row.id,
        row.prefix,
        row.created_by,
        tuple(row.scopes),
        row.rate_limit_per_minute,
    )


def _within_limit(request: Request, session: DbSession, caller: ApiCaller) -> None:
    """429 once the key's accepted requests in the last 60 seconds reach its limit."""
    now = datetime.now(UTC)
    mine = (
        ApiTokenUsage.organization_id == caller.organization_id,
        ApiTokenUsage.token_id == caller.token_id,
        ApiTokenUsage.at > now - WINDOW,
    )
    count, oldest = session.execute(
        select(func.count(), func.min(ApiTokenUsage.at)).where(*mine)
    ).one()
    if count >= caller.rate_limit_per_minute:
        wait = max(1, math.ceil((oldest + WINDOW - now).total_seconds()))
        raise _error(
            429,
            "identity.api_token_rate_limited",
            request,
            headers={"Retry-After": str(wait)},
            seconds=str(wait),
        )


_SCOPED: dict[Callable[..., ApiCaller], str | None] = {}  # each check, and the scope it needs


def require_scope(scope: str | None) -> Callable[..., ApiCaller]:
    """The key, checked for `scope` (None: any key), counted against its limit, then logged."""
    if scope is not None and scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}")

    def check(
        request: Request,
        session: DbSession,
        caller: Annotated[ApiCaller, Depends(require_api_token)],
    ) -> ApiCaller:
        if scope is not None and scope not in caller.scopes:
            raise _error(403, "identity.api_token_scope", request, scope=scope)
        _within_limit(request, session, caller)
        route = getattr(request.scope.get("route"), "path", request.url.path)
        session.add(
            ApiTokenUsage(
                organization_id=caller.organization_id,
                token_id=caller.token_id,
                method=request.method,
                route=route,
                scope=scope,
            )
        )
        session.flush()
        return caller

    _SCOPED[check] = scope
    return check


def _scope_of(dependant: Dependant) -> tuple[bool, str | None]:
    for dependency in dependant.dependencies:
        if dependency.call in _SCOPED:
            return True, _SCOPED[dependency.call]
        found = _scope_of(dependency)
        if found[0]:
            return found
    return False, None


def annotate_scopes(router: APIRouter) -> None:
    """Name each key route's permission in OpenAPI (x-atesta-scope), for the public API
    reference (#334). Call it on a router once its routes are defined, before it is included.
    Routes that take no key, and GET /api/v1/key, carry none."""
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        keyed, scope = _scope_of(route.dependant)
        if keyed and scope is not None:
            route.openapi_extra = {**(route.openapi_extra or {}), "x-atesta-scope": scope}


ApiTokenCaller = Annotated[ApiCaller, Depends(require_api_token)]


def token_labels(
    session: Session, organization_id: uuid.UUID, ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str]]:
    """Name and prefix of the organization's keys, for showing who proposed or wrote what."""
    if not ids:
        return {}
    rows = session.execute(
        select(ApiToken.id, ApiToken.name, ApiToken.prefix).where(
            ApiToken.organization_id == organization_id, ApiToken.id.in_(ids)
        )
    )
    return {row.id: (row.name, row.prefix) for row in rows}


class KeyOut(BaseModel):
    name: str
    prefix: str
    scopes: list[str]
    rate_limit_per_minute: int
    expires_at: datetime


key_router = APIRouter(prefix="/api/v1", tags=["api-keys"], route_class=QueryFreeRoute)


@key_router.get("/key")
def read_key(
    caller: Annotated[ApiCaller, Depends(require_scope(None))], session: DbSession
) -> KeyOut:
    row = session.scalar(
        select(ApiToken).where(
            ApiToken.organization_id == caller.organization_id, ApiToken.id == caller.token_id
        )
    )
    if row is None:  # resolved in this transaction: unreachable
        raise error(404, "identity.not_found")
    return KeyOut.model_validate(row, from_attributes=True)


annotate_scopes(key_router)
