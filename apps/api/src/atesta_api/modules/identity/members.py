"""Member endpoints (identity-auth spec): list, change role, remove."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from atesta_api.modules.identity.deps import Member, error, require_member, require_role
from atesta_api.modules.identity.models import Membership, Role, User
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/orgs/{org_id}/members")  # mounted under /v1 by routes.py


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None
    role: Role


class RoleIn(BaseModel):
    role: Role


def _target_role(session: Session, org_id: uuid.UUID, user_id: uuid.UUID) -> Role:
    role = session.execute(
        select(Membership.role).where(
            Membership.organization_id == org_id, Membership.user_id == user_id
        )
    ).scalar()
    if role is None:
        raise error(404, "identity.not_found")
    return Role(role)


def _keep_an_owner(session: Session, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Lock the owner rows, not the org row (every tenant FK points at it), then count."""
    owners = session.execute(
        select(Membership.user_id)
        .where(Membership.organization_id == org_id, Membership.role == Role.OWNER)
        .with_for_update()
    ).scalars()
    if set(owners) <= {user_id}:
        raise error(409, "identity.last_owner")


@router.get("")
def list_members(
    member: Annotated[Member, Depends(require_member)], session: DbSession
) -> list[MemberOut]:
    rows = session.execute(
        select(User.id, User.email, User.display_name, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == member.organization_id)
        .order_by(User.email)
    ).all()
    return [MemberOut(user_id=u, email=e, display_name=d, role=Role(r)) for u, e, d, r in rows]


@router.patch("/{user_id}")
def change_role(
    user_id: uuid.UUID,
    body: RoleIn,
    member: Annotated[Member, Depends(require_role(Role.OWNER))],
    session: DbSession,
) -> MemberOut:
    org_id = member.organization_id
    current = _target_role(session, org_id, user_id)
    if current == Role.OWNER and body.role != Role.OWNER:
        _keep_an_owner(session, org_id, user_id)
    session.execute(
        update(Membership)
        .where(Membership.organization_id == org_id, Membership.user_id == user_id)
        .values(role=body.role)
    )
    record(
        session,
        organization_id=org_id,
        action="membership.role_changed",
        target_type="user",
        target_id=str(user_id),
        actor_user_id=member.user_id,
        metadata={"from_role": current, "to_role": body.role},
    )
    email, name = session.execute(
        select(User.email, User.display_name).where(User.id == user_id)
    ).one()
    return MemberOut(user_id=user_id, email=email, display_name=name, role=body.role)


@router.delete("/{user_id}", status_code=204)
def remove_member(
    user_id: uuid.UUID,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> Response:
    org_id = member.organization_id
    target = _target_role(session, org_id, user_id)
    if target != Role.MEMBER and member.role != Role.OWNER:
        raise error(403, "identity.forbidden")
    if target == Role.OWNER:
        _keep_an_owner(session, org_id, user_id)
    session.execute(
        delete(Membership).where(
            Membership.organization_id == org_id, Membership.user_id == user_id
        )
    )
    record(
        session,
        organization_id=org_id,
        action="membership.removed",
        target_type="user",
        target_id=str(user_id),
        actor_user_id=member.user_id,
        metadata={"role": target},
    )
    return Response(status_code=204)
