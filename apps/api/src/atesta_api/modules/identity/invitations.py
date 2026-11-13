"""Invitations (identity-auth spec): copy-once link, atomic claim, inviter re-check."""

import hashlib
import re
import secrets
import string
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from atesta_api.modules.identity.cognito import IdentityProvider
from atesta_api.modules.identity.context import (
    ContextReason,
    enter_invitation_context,
    enter_org_context,
)
from atesta_api.modules.identity.deps import (
    RANK,
    CurrentCaller,
    Member,
    error,
    get_identity_provider,
    refresh_profile,
    require_role,
)
from atesta_api.modules.identity.models import Invitation, Membership, Role, User
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession

TTL = timedelta(days=7)
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


class QueryFreeRoute(APIRoute):
    """400 identity.token_in_query on any query string, before body parsing, auth or userInfo:
    the token must never travel in a URL (identity-auth spec)."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def refuse_query(request: Request) -> Response:
            if request.url.query:
                raise error(400, "identity.token_in_query")
            return await handler(request)

        return refuse_query


router = APIRouter()  # mounted under /v1 by routes.py
accept_router = APIRouter(route_class=QueryFreeRoute)


def normalize_email(value: str) -> str:
    """Fold ASCII case only. Unicode casefold merges distinct mailboxes (ß -> ss, Kelvin -> k)."""
    return value.strip().translate(_ASCII_LOWER)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class InvitationIn(BaseModel):
    email: str = Field(max_length=320)
    role: Role

    @field_validator("email")
    @classmethod
    def normalize(cls, value: str) -> str:
        if not value.strip().isascii() or not _EMAIL.fullmatch(value.strip()):
            raise ValueError("invalid email")  # Cognito and SES carry ASCII addresses only
        return normalize_email(value)


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    expires_at: datetime


class CreatedInvitation(InvitationOut):
    accept_link: str  # shown once; the API keeps only the SHA-256 of the token


class Accepted(BaseModel):
    organization_id: uuid.UUID
    role: Role


class AcceptIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


@router.post("/orgs/{org_id}/invitations", status_code=201)
def create_invitation(
    body: InvitationIn,
    request: Request,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> CreatedInvitation:
    if RANK[body.role] > RANK[member.role]:
        raise error(403, "identity.role_not_allowed")
    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        organization_id=member.organization_id,
        email=body.email,
        role=body.role,
        token_sha256=token_hash(token),
        invited_by=member.user_id,
        expires_at=datetime.now(UTC) + TTL,
    )
    session.add(invitation)
    session.flush()
    record(
        session,
        organization_id=member.organization_id,
        action="invitation.created",
        target_type="invitation",
        target_id=str(invitation.id),
        actor_user_id=member.user_id,
        metadata={"role": body.role},
    )
    link = f"{request.app.state.web_base_url}/invite#token={token}"  # fragment: never logged
    return CreatedInvitation(
        id=invitation.id,
        email=body.email,
        role=body.role,
        expires_at=invitation.expires_at,
        accept_link=link,
    )


@router.get("/orgs/{org_id}/invitations")
def list_invitations(
    member: Annotated[Member, Depends(require_role(Role.ADMIN))], session: DbSession
) -> list[InvitationOut]:
    rows = session.execute(
        select(Invitation).where(
            Invitation.organization_id == member.organization_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > datetime.now(UTC),
        )
    ).scalars()
    return [
        InvitationOut(id=i.id, email=i.email, role=Role(i.role), expires_at=i.expires_at)
        for i in rows
    ]


@router.delete("/orgs/{org_id}/invitations/{invitation_id}", status_code=204)
def revoke_invitation(
    invitation_id: uuid.UUID,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> Response:
    revoked = session.execute(
        update(Invitation)
        .where(
            Invitation.id == invitation_id,
            Invitation.organization_id == member.organization_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
        .returning(Invitation.id)
    ).scalar()
    if revoked is None:
        raise error(404, "identity.not_found")
    record(
        session,
        organization_id=member.organization_id,
        action="invitation.revoked",
        target_type="invitation",
        target_id=str(invitation_id),
        actor_user_id=member.user_id,
    )
    return Response(status_code=204)


@accept_router.post("/invitations/accept")
def accept_invitation(
    body: AcceptIn,
    caller: CurrentCaller,
    session: DbSession,
    provider: Annotated[IdentityProvider, Depends(get_identity_provider)],
) -> Accepted:
    if not caller.profile_refreshed:  # decide on Cognito's current email, never a stale cache
        refresh_profile(session, provider, caller.sub, caller.access_token)
    user = session.execute(select(User).where(User.id == caller.user_id)).scalar_one()
    digest = token_hash(body.token)
    enter_invitation_context(session, digest)
    invitation = session.execute(
        select(Invitation).where(Invitation.token_sha256 == digest)
    ).scalar()
    if invitation is None:
        raise error(404, "identity.invitation_invalid")
    if (
        invitation.accepted_at
        or invitation.revoked_at
        or invitation.expires_at <= datetime.now(UTC)
    ):
        raise error(410, "identity.invitation_invalid")
    if not user.email_verified:
        raise error(403, "identity.email_unverified")
    if normalize_email(user.email) != normalize_email(invitation.email):
        raise error(403, "identity.email_mismatch")
    org_id, role = invitation.organization_id, Role(invitation.role)
    enter_org_context(session, org_id, ContextReason.INVITATION)
    roles = dict(
        session.execute(
            select(Membership.user_id, Membership.role).where(
                Membership.organization_id == org_id,
                Membership.user_id.in_([caller.user_id, invitation.invited_by]),
            )
        ).all()
    )
    if caller.user_id in roles:
        raise error(409, "identity.already_member")
    inviter = roles.get(invitation.invited_by)
    if inviter is None or RANK[Role(inviter)] < max(RANK[role], RANK[Role.ADMIN]):
        raise error(410, "identity.invitation_invalid")  # inviter removed or demoted
    claimed = session.execute(
        update(Invitation)
        .where(
            Invitation.token_sha256 == digest,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > datetime.now(UTC),
        )
        .values(accepted_at=datetime.now(UTC))
        .returning(Invitation.id)
    ).scalar()
    if claimed is None:
        raise error(410, "identity.invitation_invalid")
    try:
        with session.begin_nested():
            session.add(Membership(organization_id=org_id, user_id=caller.user_id, role=role))
    except IntegrityError:
        raise error(409, "identity.already_member") from None
    record(
        session,
        organization_id=org_id,
        action="invitation.accepted",
        target_type="invitation",
        target_id=str(claimed),
        actor_user_id=caller.user_id,
        metadata={"role": role},
    )
    return Accepted(organization_id=org_id, role=Role(role))
