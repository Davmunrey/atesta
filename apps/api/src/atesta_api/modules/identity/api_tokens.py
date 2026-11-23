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
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

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
    Role,
    User,
)
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession
from atesta_api.platform.i18n import accepted_locale, message

router = APIRouter()  # mounted under /v1 by routes.py

TOKEN_PREFIX = "atesta_"  # noqa: S105 - a public marker, not a secret
PREFIX_LENGTH = 12
WINDOW = timedelta(seconds=60)
USAGE_SHOWN = 100

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
    revoked = session.scalar(
        update(ApiToken)
        .where(
            ApiToken.organization_id == member.organization_id,
            ApiToken.id == token_id,
            ApiToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC), revoked_by=member.user_id)
        .returning(ApiToken.prefix)
    )
    if revoked is None:
        raise error(404, "identity.not_found")
    record(
        session,
        organization_id=member.organization_id,
        action="api_token.revoked",
        target_type="api_token",
        target_id=str(token_id),
        actor_user_id=member.user_id,
        metadata={"prefix": revoked},
    )
    return Response(status_code=204)


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


def require_api_token(request: Request, session: DbSession) -> ApiCaller:
    """401 identity.api_token_invalid for a missing, unknown, revoked or expired key alike."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.startswith(TOKEN_PREFIX) or len(token) > 200:
        raise _error(401, "identity.api_token_invalid", request)
    digest = token_hash(token)
    enter_api_token_context(session, digest)
    row = session.scalar(select(ApiToken).where(ApiToken.token_sha256 == digest))
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise _error(401, "identity.api_token_invalid", request)
    enter_org_context(session, row.organization_id, ContextReason.API_TOKEN)
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

    return check


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
