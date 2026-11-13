"""Request authentication and membership checks (identity-auth spec, Request flow)."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from atesta_api.modules.identity.cognito import (
    IdentityProvider,
    InvalidTokenError,
    TokenVerifier,
    UserInfo,
)
from atesta_api.modules.identity.context import (
    ContextReason,
    enter_org_context,
    enter_user_context,
)
from atesta_api.modules.identity.models import Membership, Role, User
from atesta_api.platform.db import DbSession

_bearer = HTTPBearer(auto_error=False)
_RANK = {Role.MEMBER: 0, Role.ADMIN: 1, Role.OWNER: 2}


def error(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


def get_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier = request.app.state.token_verifier
    return verifier


def get_identity_provider(request: Request) -> IdentityProvider:
    provider: IdentityProvider = request.app.state.identity_provider
    return provider


@dataclass(frozen=True, slots=True)
class Caller:
    user_id: uuid.UUID
    sub: str
    access_token: str
    profile_refreshed: bool


@dataclass(frozen=True, slots=True)
class Member:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: Role


def upsert_user(session: Session, info: UserInfo) -> uuid.UUID:
    """Parallel first calls yield one row: ON CONFLICT on the cognito_sub arbiter only."""
    statement = (
        insert(User)
        .values(
            id=uuid.uuid4(),
            cognito_sub=info.sub,
            email=info.email,
            email_verified=info.email_verified,
        )
        .on_conflict_do_update(
            index_elements=[User.cognito_sub],
            set_={"email": info.email, "email_verified": info.email_verified},
        )
        .returning(User.id)
    )
    user_id: uuid.UUID = session.execute(statement).scalar_one()
    return user_id


def authenticate(
    session: DbSession,
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
    provider: Annotated[IdentityProvider, Depends(get_identity_provider)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Caller:
    if credentials is None:
        raise error(401, "auth.invalid_token")
    try:
        token = verifier.verify(credentials.credentials)
    except InvalidTokenError:
        raise error(401, "auth.invalid_token") from None
    enter_user_context(session, token.sub)
    user_id = session.execute(select(User.id).where(User.cognito_sub == token.sub)).scalar()
    refreshed = user_id is None
    if user_id is None:
        user_id = refresh_profile(session, provider, token.sub, credentials.credentials)
    enter_user_context(session, token.sub, user_id)
    return Caller(user_id, token.sub, credentials.credentials, profile_refreshed=refreshed)


def refresh_profile(
    session: Session, provider: IdentityProvider, sub: str, access_token: str
) -> uuid.UUID:
    try:
        info = provider.userinfo(access_token)
    except InvalidTokenError:
        raise error(401, "auth.invalid_token") from None
    if info.sub != sub:
        raise error(401, "auth.invalid_token")
    return upsert_user(session, info)


CurrentCaller = Annotated[Caller, Depends(authenticate)]


def require_member(org_id: uuid.UUID, caller: CurrentCaller, session: DbSession) -> Member:
    """Membership check, then the org context. Non-members get 404: no org enumeration."""
    role = session.execute(
        select(Membership.role).where(
            Membership.organization_id == org_id, Membership.user_id == caller.user_id
        )
    ).scalar()
    if role is None:
        raise error(404, "identity.not_found")
    enter_org_context(session, org_id, ContextReason.MEMBERSHIP)
    return Member(user_id=caller.user_id, organization_id=org_id, role=Role(role))


def require_role(minimum: Role) -> Callable[[Member], Member]:
    def check(member: Annotated[Member, Depends(require_member)]) -> Member:
        if _RANK[member.role] < _RANK[minimum]:
            raise error(403, "identity.forbidden")
        return member

    return check
