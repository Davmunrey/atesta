"""Identity endpoints: profile and org creation (identity-auth spec)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from atesta_api.modules.identity.access import end_date
from atesta_api.modules.identity.activity import router as activity_router
from atesta_api.modules.identity.cognito import IdentityProvider
from atesta_api.modules.identity.context import ContextReason, enter_org_context
from atesta_api.modules.identity.deps import (
    CurrentCaller,
    get_identity_provider,
    refresh_profile,
)
from atesta_api.modules.identity.invitations import accept_router
from atesta_api.modules.identity.invitations import router as invitations_router
from atesta_api.modules.identity.members import router as members_router
from atesta_api.modules.identity.models import Membership, Role, User
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession
from atesta_api.platform.tenancy import Organization

router = APIRouter(prefix="/api/v1", tags=["identity"])
router.include_router(members_router)
router.include_router(activity_router)
router.include_router(invitations_router)
router.include_router(accept_router)


class MembershipOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    role: Role
    access_expires_on: date | None = None


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    email_verified: bool
    locale: str
    memberships: list[MembershipOut]


class OrgIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str


@router.get("/me")
def me(
    caller: CurrentCaller,
    session: DbSession,
    provider: Annotated[IdentityProvider, Depends(get_identity_provider)],
) -> MeOut:
    if not caller.profile_refreshed:  # Cognito owns email; refresh the cache on every /me
        refresh_profile(session, provider, caller.sub, caller.access_token)
    user = session.execute(select(User).where(User.id == caller.user_id)).scalar_one()
    rows = session.execute(
        select(
            Membership.organization_id,
            Organization.name,
            Membership.role,
            Membership.access_expires_at,
        )
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == caller.user_id)
        .order_by(Organization.name)
    ).all()
    return MeOut(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        locale=user.locale,
        memberships=[
            MembershipOut(
                organization_id=o, organization_name=n, role=Role(r), access_expires_on=end_date(x)
            )
            for o, n, r, x in rows
        ],
    )


@router.post("/orgs", status_code=201)
def create_org(body: OrgIn, caller: CurrentCaller, session: DbSession) -> OrgOut:
    org_id = uuid.uuid4()  # server-generated, never from the request
    enter_org_context(session, org_id, ContextReason.ORG_CREATION)
    session.add(Organization(id=org_id, name=body.name))
    session.flush()
    session.add(Membership(organization_id=org_id, user_id=caller.user_id, role=Role.OWNER))
    record(
        session,
        organization_id=org_id,
        action="org.created",
        target_type="organization",
        target_id=str(org_id),
        actor_user_id=caller.user_id,
    )
    return OrgOut(id=org_id, name=body.name)
