"""API tokens for a customer's own tools (evidence-ingestion-api spec).

Admins create and revoke them; the token is shown once and only its SHA-256 is kept. A token is
write-only (`evidence:write`). Resolving one reads it through the named policy api_token_read,
then enters the organization's context (ADR-012 amendment 5).
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update

from atesta_api.modules.identity.context import (
    ContextReason,
    enter_api_token_context,
    enter_org_context,
)
from atesta_api.modules.identity.deps import Member, error, require_role
from atesta_api.modules.identity.invitations import token_hash
from atesta_api.modules.identity.models import ApiToken, Role, User
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession

router = APIRouter()  # mounted under /v1 by routes.py

TOKEN_PREFIX = "atesta_"  # noqa: S105 - a public marker, not a secret
PREFIX_LENGTH = 12


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expires_in_days: int = Field(ge=1, le=365)

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
    scope: str
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
        scope=row.scope,
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
        metadata={"prefix": row.prefix, "expires_in_days": body.expires_in_days},
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


@dataclass(frozen=True, slots=True)
class ApiCaller:
    """Who an accepted API token speaks for: its organization, and the admin who created it."""

    organization_id: uuid.UUID
    token_id: uuid.UUID
    prefix: str
    created_by: uuid.UUID


def require_api_token(request: Request, session: DbSession) -> ApiCaller:
    """401 identity.api_token_invalid for a missing, unknown, revoked or expired token alike."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.startswith(TOKEN_PREFIX) or len(token) > 200:
        raise error(401, "identity.api_token_invalid")
    digest = token_hash(token)
    enter_api_token_context(session, digest)
    row = session.scalar(select(ApiToken).where(ApiToken.token_sha256 == digest))
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise error(401, "identity.api_token_invalid")
    enter_org_context(session, row.organization_id, ContextReason.API_TOKEN)
    # Taking the row lock also serializes this token's writes, so idempotency checks hold.
    session.execute(
        update(ApiToken)
        .where(ApiToken.organization_id == row.organization_id, ApiToken.id == row.id)
        .values(last_used_at=now)
    )
    return ApiCaller(row.organization_id, row.id, row.prefix, row.created_by)


ApiTokenCaller = Annotated[ApiCaller, Depends(require_api_token)]
