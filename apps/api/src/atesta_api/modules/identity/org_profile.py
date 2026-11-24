"""The organization's email language and the people notices go to (notifications spec PR 2).

Other modules read these through identity.api; only the owner changes the language.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.identity.deps import Member, error, require_role
from atesta_api.modules.identity.models import Membership, Role, User
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession
from atesta_api.platform.tenancy import Organization

router = APIRouter(prefix="/orgs/{org_id}", tags=["identity"])

type Locale = Literal["es", "en"]


class LocaleIn(BaseModel):
    locale: Locale


class LocaleOut(BaseModel):
    locale: Locale


@dataclass(frozen=True, slots=True)
class OrganizationProfile:
    name: str
    locale: Locale


@dataclass(frozen=True, slots=True)
class Recipient:
    user_id: uuid.UUID
    email: str
    role: Role


def organization_profile(session: Session, organization_id: uuid.UUID) -> OrganizationProfile:
    """Name and email language, read in the organization's own context."""
    row = session.execute(
        select(Organization.name, Organization.locale).where(Organization.id == organization_id)
    ).one()
    return OrganizationProfile(name=row.name, locale="en" if row.locale == "en" else "es")


def recipients(
    session: Session, organization_id: uuid.UUID, roles: frozenset[Role]
) -> list[Recipient]:
    """Members with these roles and their email, in a stable order."""
    rows = session.execute(
        select(User.id, User.email, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == organization_id, Membership.role.in_(list(roles)))
        .order_by(User.email)
    ).all()
    return [Recipient(user_id=r.id, email=str(r.email), role=Role(r.role)) for r in rows]


@router.put("/locale")
def set_locale(
    body: LocaleIn,
    member: Annotated[Member, Depends(require_role(Role.OWNER))],
    session: DbSession,
) -> LocaleOut:
    organization = session.get(Organization, member.organization_id)
    if organization is None:
        raise error(404, "identity.not_found")
    if organization.locale != body.locale:
        organization.locale = body.locale
        session.flush()
        record(
            session,
            organization_id=organization.id,
            action="organization.locale_changed",
            target_type="organization",
            target_id=str(organization.id),
            actor_user_id=member.user_id,
            metadata={"locale": body.locale},
        )
    return LocaleOut(locale=body.locale)
