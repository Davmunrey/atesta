"""Due dates for email notices (notifications spec PR 3; issue 388).

The same rules as Rutinas (policies and access reviews), Mi trabajo (assigned measures) and
manual control reviews (valid_until), read once for the daily digest and the weekly summary.
Customer titles are returned as typed; catalog titles come in both languages.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from atesta_core.dates import add_months
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.models import (
    AccessReview,
    Control,
    ControlReview,
    Framework,
    Policy,
    PolicyApproval,
    Requirement,
    RequirementAssignment,
)
from atesta_api.modules.compliance.overview import latest_snapshots
from atesta_api.modules.compliance.scoring import active_frameworks
from atesta_api.modules.notifications.api import DueItem

SOON_DAYS = 7


@dataclass(frozen=True, slots=True)
class ComplianceWeek:
    frameworks: list[tuple[str, float | None]]
    due_soon: int  # due from today to 7 days ahead
    overdue: int


def _control_reviews(session: Session, org: uuid.UUID) -> list[DueItem]:
    latest = session.scalars(
        select(ControlReview)
        .where(ControlReview.organization_id == org)
        .ext(distinct_on(ControlReview.control_key))
        .order_by(
            ControlReview.control_key, ControlReview.reviewed_at.desc(), ControlReview.id.desc()
        )
    ).all()
    keys = [r.control_key for r in latest]
    titles = (
        {
            c.key: (c.title_es, c.title_en)
            for c in session.scalars(select(Control).where(Control.key.in_(keys)))
        }
        if keys
        else {}
    )
    return [
        DueItem(
            kind="control_review",
            title_es=titles.get(r.control_key, (r.control_key, None))[0],
            title_en=titles.get(r.control_key, (r.control_key, None))[1],
            due_on=r.valid_until,
            owner_user_id=None,
            path=f"/app/frameworks?org={org}",
        )
        for r in latest
    ]


def _policies(session: Session, org: uuid.UUID) -> list[DueItem]:
    approvals = {
        a.policy_id: a
        for a in session.scalars(
            select(PolicyApproval)
            .where(PolicyApproval.organization_id == org)
            .ext(distinct_on(PolicyApproval.policy_id))
            .order_by(
                PolicyApproval.policy_id,
                PolicyApproval.approved_on.desc(),
                PolicyApproval.recorded_at.desc(),
            )
        )
    }
    items: list[DueItem] = []
    for policy in session.scalars(select(Policy).where(Policy.organization_id == org)):
        approval = approvals.get(policy.id)
        if approval is not None:
            items.append(
                DueItem(
                    kind="policy_review",
                    title_es=policy.title,
                    title_en=None,
                    due_on=add_months(approval.approved_on, policy.review_months),
                    owner_user_id=None,
                    path=f"/app/policies?org={org}",
                )
            )
    return items


def _access_reviews(session: Session, org: uuid.UUID) -> list[DueItem]:
    rows = session.scalars(
        select(AccessReview).where(
            AccessReview.organization_id == org,
            AccessReview.closed_at.is_(None),
            AccessReview.due_on.is_not(None),
        )
    )
    return [
        DueItem(
            kind="access_review",
            title_es=r.title,
            title_en=None,
            due_on=r.due_on,
            owner_user_id=None,
            path=f"/app/access-review?org={org}&id={r.id}",
        )
        for r in rows
        if r.due_on is not None
    ]


def _assignments(session: Session, org: uuid.UUID) -> list[DueItem]:
    latest = session.scalars(
        select(RequirementAssignment)
        .where(RequirementAssignment.organization_id == org)
        .ext(
            distinct_on(RequirementAssignment.framework_key, RequirementAssignment.requirement_code)
        )
        .order_by(
            RequirementAssignment.framework_key,
            RequirementAssignment.requirement_code,
            RequirementAssignment.assigned_at.desc(),
        )
    ).all()
    owned = [a for a in latest if a.owner_user_id is not None and a.due_on is not None]
    names = {f.key: f.name for f in session.scalars(select(Framework))} if owned else {}
    titles = (
        {
            (r.framework_key, r.code): (r.title_es, r.title_en)
            for r in session.scalars(
                select(Requirement).where(
                    Requirement.framework_key.in_({a.framework_key for a in owned})
                )
            )
        }
        if owned
        else {}
    )
    items: list[DueItem] = []
    for a in owned:
        name = names.get(a.framework_key, a.framework_key)
        found = titles.get((a.framework_key, a.requirement_code))
        es = f"{name} {a.requirement_code}" + (f": {found[0]}" if found else "")
        en = f"{name} {a.requirement_code}: {found[1]}" if found and found[1] else None
        items.append(
            DueItem(
                kind="assignment",
                title_es=es,
                title_en=en,
                due_on=a.due_on,  # type: ignore[arg-type]  # filtered above
                owner_user_id=a.owner_user_id,
                path=f"/app/my-work?org={org}",
            )
        )
    return items


def _all(session: Session, org: uuid.UUID) -> list[DueItem]:
    return [
        *_control_reviews(session, org),
        *_policies(session, org),
        *_access_reviews(session, org),
        *_assignments(session, org),
    ]


def due_items(session: Session, org: uuid.UUID, dates: frozenset[date]) -> list[DueItem]:
    """Items due on exactly one of these dates (30, 7 and 1 day ahead for the digest)."""
    return [i for i in _all(session, org) if i.due_on in dates]


def weekly_compliance(session: Session, org: uuid.UUID, *, today: date) -> ComplianceWeek:
    frameworks = active_frameworks(session)
    snapshots = latest_snapshots(session, org, [f.key for f in frameworks])
    items = _all(session, org)
    soon = today + timedelta(days=SOON_DAYS)
    return ComplianceWeek(
        frameworks=[
            (f.name, snapshots[f.key].score if f.key in snapshots else None) for f in frameworks
        ],
        due_soon=sum(1 for i in items if today <= i.due_on <= soon),
        overdue=sum(1 for i in items if i.due_on < today),
    )
