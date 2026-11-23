"""Organization activity (insights spec): who did what, from the audit log.

Admins and owners only. Returns action, target, actor email and time, never event metadata.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atesta_api.modules.identity.deps import Member, require_role
from atesta_api.modules.identity.models import Membership, Role, User
from atesta_api.platform.audit import AuditEvent
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/orgs/{org_id}/activity")  # mounted under /v1 by routes.py
LATEST = 50
PERIODS = (30, 90)


class DayCount(BaseModel):
    day: date
    count: int


class ActivityEvent(BaseModel):
    occurred_at: datetime
    actor_email: str | None  # None for system events or a user no longer in the org
    action: str
    target_type: str
    target_id: str


class Activity(BaseModel):
    days: int
    daily: list[DayCount]
    events: list[ActivityEvent]


def is_member(session: Session, organization_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Whether the user belongs to the organization (for other modules, through api.py)."""
    return (
        session.scalar(
            select(Membership.user_id).where(
                Membership.organization_id == organization_id, Membership.user_id == user_id
            )
        )
        is not None
    )


def person(session: Session, user_id: uuid.UUID) -> tuple[str, str]:
    """A signed-in person's email and language, for records written in their name (api.py)."""
    row = session.execute(select(User.email, User.locale).where(User.id == user_id)).one()
    return str(row.email), str(row.locale)


@router.get("")
def read_activity(
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
    days: Annotated[int, Query()] = 30,
) -> Activity:
    # A query string arrives as text, so the allowed periods are checked here, not as a Literal.
    if days not in PERIODS:
        raise HTTPException(422, detail={"code": "identity.period_invalid"})
    since = datetime.now(UTC) - timedelta(days=days)
    where = (AuditEvent.organization_id == member.organization_id, AuditEvent.occurred_at >= since)
    day = func.date_trunc("day", AuditEvent.occurred_at)
    counts = {
        d.date(): n
        for d, n in session.execute(select(day, func.count()).where(*where).group_by(day)).all()
    }
    first = since.date()
    daily = [
        DayCount(day=first + timedelta(days=i), count=counts.get(first + timedelta(days=i), 0))
        for i in range(days + 1)
    ]
    members = (
        select(Membership.user_id, User.email)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == member.organization_id)
        .subquery()
    )
    rows = session.execute(
        select(AuditEvent, members.c.email)
        .outerjoin(members, members.c.user_id == AuditEvent.actor_user_id)
        .where(*where)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(LATEST)
    ).all()
    events = [
        ActivityEvent(
            occurred_at=event.occurred_at,
            actor_email=email,
            action=event.action,
            target_type=event.target_type,
            target_id=event.target_id,
        )
        for event, email in rows
    ]
    return Activity(days=days, daily=daily, events=events)
