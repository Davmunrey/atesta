"""Request authentication and membership checks (identity-auth spec, Request flow)."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from atesta_api.modules.identity.bff import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    OAuthClient,
    SessionCrypto,
    SessionEndedError,
    store_tokens,
)
from atesta_api.modules.identity.cognito import (
    ExpiredTokenError,
    IdentityProvider,
    InvalidTokenError,
    ProviderUnavailableError,
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
RANK = {Role.AUDITOR: -1, Role.MEMBER: 0, Role.ADMIN: 1, Role.OWNER: 2}


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


_WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _cookie_token(request: Request, response: Response, verifier: TokenVerifier) -> str:
    """Access token from the session cookie; one refresh when it has expired."""
    crypto: SessionCrypto = request.app.state.session_crypto
    try:
        token = crypto.open(ACCESS_COOKIE, request.cookies.get(ACCESS_COOKIE, ""))
        verifier.verify(token)
        return token
    except ExpiredTokenError:
        pass
    except InvalidTokenError:
        raise SessionEndedError from None
    try:
        refresh_token = crypto.open(REFRESH_COOKIE, request.cookies.get(REFRESH_COOKIE, ""))
        oauth: OAuthClient = request.app.state.oauth
        tokens = oauth.refresh(refresh_token)
        verifier.verify(tokens.access_token)
    except InvalidTokenError:
        raise SessionEndedError from None
    store_tokens(response, crypto, tokens)
    return tokens.access_token


def authenticate(
    request: Request,
    response: Response,
    session: DbSession,
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
    provider: Annotated[IdentityProvider, Depends(get_identity_provider)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Caller:
    """Bearer token (tests, future CLI) or the BFF session cookie (browser)."""
    if credentials is None and ACCESS_COOKIE not in request.cookies:
        raise error(401, "auth.invalid_token")
    if (
        credentials is None
        and request.method in _WRITES
        and request.headers.get("origin") != request.app.state.web_origin
    ):
        raise error(403, "auth.bad_origin")
    try:  # a JWKS outage is a retryable 503 on both paths, never a 500
        if credentials is not None:
            token = credentials.credentials
        else:
            token = _cookie_token(request, response, verifier)
        sub = verifier.verify(token).sub
    except InvalidTokenError:
        raise error(401, "auth.invalid_token") from None
    except ProviderUnavailableError:
        raise error(503, "auth.provider_unavailable") from None
    enter_user_context(session, sub)
    user_id = session.execute(select(User.id).where(User.cognito_sub == sub)).scalar()
    refreshed = user_id is None
    if user_id is None:
        user_id = refresh_profile(session, provider, sub, token)
    enter_user_context(session, sub, user_id)
    return Caller(user_id, sub, token, profile_refreshed=refreshed)


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


def require_member(
    org_id: uuid.UUID, request: Request, caller: CurrentCaller, session: DbSession
) -> Member:
    """Membership check, then the org context. Non-members get 404: no org enumeration.

    The auditor rules live here so that no endpoint can forget them (rbac spec): access ends
    at the end date, and an auditor never writes, whatever the route.
    """
    row = session.execute(
        select(Membership.role, Membership.access_expires_at).where(
            Membership.organization_id == org_id, Membership.user_id == caller.user_id
        )
    ).first()
    if row is None:
        raise error(404, "identity.not_found")
    role, expires_at = Role(row.role), row.access_expires_at
    if expires_at is not None and expires_at <= datetime.now(UTC):
        raise error(403, "identity.access_expired")
    if role == Role.AUDITOR and request.method in _WRITES:
        raise error(403, "identity.forbidden")
    enter_org_context(session, org_id, ContextReason.MEMBERSHIP)
    return Member(user_id=caller.user_id, organization_id=org_id, role=role)


def require_role(minimum: Role) -> Callable[[Member], Member]:
    def check(member: Annotated[Member, Depends(require_member)]) -> Member:
        if RANK[member.role] < RANK[minimum]:
            raise error(403, "identity.forbidden")
        return member

    return check
