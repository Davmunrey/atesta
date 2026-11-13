"""Member endpoints (identity-auth spec): list, change role, remove."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import delete, or_, select, update
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


def _lock_target(
    session: Session, org_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Role, set[uuid.UUID]]:
    """Lock the target row and every owner row in one statement, then decide.

    Every decision reads this locked state, so a concurrent promotion, demotion or removal of
    the target is seen. Rows lock in user_id order, so two requests cannot deadlock. The org
    row stays unlocked: every tenant FK points at it.
    """
    rows = session.execute(
        select(Membership.user_id, Membership.role)
        .where(
            Membership.organization_id == org_id,
            or_(Membership.user_id == user_id, Membership.role == Role.OWNER),
        )
        .order_by(Membership.user_id)
        .with_for_update()
    ).all()
    role = next((r for u, r in rows if u == user_id), None)
    if role is None:
        raise error(404, "identity.not_found")
    return Role(role), {u for u, r in rows if r == Role.OWNER}


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
    current, owners = _lock_target(session, org_id, user_id)
    if current == Role.OWNER and body.role != Role.OWNER and owners <= {user_id}:
        raise error(409, "identity.last_owner")
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
    target, owners = _lock_target(session, org_id, user_id)
    if target != Role.MEMBER and member.role != Role.OWNER:
        raise error(403, "identity.forbidden")
    if target == Role.OWNER and owners <= {user_id}:
        raise error(409, "identity.last_owner")
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
