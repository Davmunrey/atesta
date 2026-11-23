"""Monthly report for management (management-report spec): what was done in the month, from the
audit log; where each framework in progress stands now; and what falls due. Counts and dates
only, never a score (ADR-005)."""

import re
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from atesta_api.modules.compliance.readiness import FrameworkReadiness, framework_readiness
from atesta_api.modules.compliance.register import NOT_A_CERTIFICATION
from atesta_api.modules.compliance.routines import DueItem, routines_due
from atesta_api.modules.compliance.scoring import active_frameworks
from atesta_api.modules.identity.api import Member, require_member
from atesta_api.platform.audit import AuditEvent, record
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["compliance"])

MADRID = ZoneInfo("Europe/Madrid")
_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

# Audit actions counted for each line of the report.
ACTIONS: dict[str, tuple[str, ...]] = {
    "measures_assessed": ("requirement.assessed",),
    "assessments_reviewed": ("framework.assessment_reviewed",),
    "evidence_by_people": ("evidence.statement_recorded",),
    "evidence_by_tools": ("evidence.ingested",),
    "policies_approved": ("policy.approved",),
    "access_reviews_closed": ("access_review.closed",),
    "trainings_closed": ("training.closed",),
    "incidents_recorded": ("incident.created",),
    "incidents_closed": ("incident.closed",),
    "deadlines_met": ("incident.clock_met",),
    "people_joined": ("invitation.accepted",),
}


class Done(BaseModel):
    measures_assessed: int
    assessments_reviewed: int
    evidence_by_people: int
    evidence_by_tools: int
    policies_approved: int
    access_reviews_closed: int
    trainings_closed: int
    incidents_recorded: int
    incidents_closed: int
    deadlines_met: int
    people_joined: int


class Report(BaseModel):
    month: str
    starts: datetime
    ends: datetime
    generated_at: datetime
    statement: str = NOT_A_CERTIFICATION
    done: Done
    status_is_current: bool = True  # the status is today's, not the status at the end of the month
    frameworks: list[FrameworkReadiness]
    due: list[DueItem]


def _bounds(month: str | None) -> tuple[str, datetime, datetime]:
    today = datetime.now(MADRID).date()
    value = month or today.strftime("%Y-%m")
    match = _MONTH.fullmatch(value)
    if match is None:
        raise HTTPException(422, detail={"code": "compliance.report_month_invalid"})
    first = date(int(match.group(1)), int(match.group(2)), 1)
    if first > today:
        raise HTTPException(422, detail={"code": "compliance.report_month_invalid"})
    following = date(first.year + first.month // 12, first.month % 12 + 1, 1)
    start = datetime(first.year, first.month, 1, tzinfo=MADRID)
    end = datetime(following.year, following.month, 1, tzinfo=MADRID)
    return value, start, end


@router.get("/report")
def monthly_report(
    member: Annotated[Member, Depends(require_member)], session: DbSession, month: str | None = None
) -> Report:
    value, start, end = _bounds(month)
    org = member.organization_id
    rows = session.execute(
        select(AuditEvent.action, func.count())
        .where(
            AuditEvent.organization_id == org,
            AuditEvent.occurred_at >= start,
            AuditEvent.occurred_at < end,
            AuditEvent.action.in_([a for actions in ACTIONS.values() for a in actions]),
        )
        .group_by(AuditEvent.action)
    ).tuples()
    counts: dict[str, int] = {action: n for action, n in rows}
    done = Done(**{key: sum(counts.get(a, 0) for a in actions) for key, actions in ACTIONS.items()})
    today = datetime.now(MADRID).date()
    frameworks = [
        r
        for f in active_frameworks(session)
        if (r := framework_readiness(session, org, f.key, f.name, today)) is not None
        and (r.assessed > 0 or r.scope_defined)
    ]
    record(
        session,
        organization_id=org,
        action="organization.report_viewed",
        target_type="organization",
        target_id=str(org),
        actor_user_id=member.user_id,
        metadata={"month": value},
    )
    return Report(
        month=value,
        starts=start,
        ends=end,
        generated_at=datetime.now(MADRID),
        done=done,
        frameworks=frameworks,
        due=routines_due(member, session),
    )
