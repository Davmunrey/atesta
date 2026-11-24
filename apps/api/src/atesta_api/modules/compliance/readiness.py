"""Readiness counts for the dashboard cockpit (readiness-cockpit spec).

Counts only, from the organization's own recorded rows: the latest assessment and the latest
assignment of each requirement. Nothing here is a compliance score (ADR-005, claims-honesty).
"""

import uuid
from collections import Counter
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.register import (
    _assessments,
    _assignments,
    _axes,
    _requirements,
    _review,
    _scope,
)
from atesta_api.modules.compliance.scoring import active_frameworks
from atesta_api.modules.identity.api import Member, require_member
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["compliance"])


class FrameworkReadiness(BaseModel):
    key: str
    name: str
    total: int
    assessed: int
    implemented: int
    partial: int
    not_implemented: int
    not_applicable: int
    has_axes: bool
    scope_defined: bool
    review_on: date | None
    overdue: int
    unowned_open: int
    open_by_owner: dict[uuid.UUID, int]
    last_assessed_at: datetime | None


@router.get("/readiness")
def readiness(
    member: Annotated[Member, Depends(require_member)], session: DbSession
) -> list[FrameworkReadiness]:
    return organization_readiness(session, member.organization_id)


def organization_readiness(session: Session, org: uuid.UUID) -> list[FrameworkReadiness]:
    """Every active framework's counts for one organization (the portfolio reuses it)."""
    today = datetime.now().astimezone().date()
    out: list[FrameworkReadiness] = []
    for framework in active_frameworks(session):
        found = framework_readiness(session, org, framework.key, framework.name, today)
        if found is not None:
            out.append(found)
    return out


def framework_readiness(
    session: Session, org: uuid.UUID, key: str, name: str, today: date
) -> FrameworkReadiness | None:
    """Counts for one framework; None when it has no requirements (the dossier reuses it)."""
    requirements = _requirements(session, key)
    if not requirements:
        return None
    codes = {r.code for r in requirements}
    assessed = {c: a for c, a in _assessments(session, org, key).items() if c in codes}
    assigned = {c: a for c, a in _assignments(session, org, key).items() if c in codes}
    states = Counter(
        "not_applicable" if a.applicability == "not_applicable" else a.implementation
        for a in assessed.values()
    )
    done = {
        c
        for c, a in assessed.items()
        if a.applicability == "not_applicable" or a.implementation == "implemented"
    }
    open_codes = codes - done
    owners = Counter(
        assigned[c].owner_user_id for c in open_codes if c in assigned and assigned[c].owner_user_id
    )
    review = _review(session, org, key)
    dues = [assigned[c].due_on for c in open_codes if c in assigned]
    owned = {c for c, a in assigned.items() if a.owner_user_id is not None}
    return FrameworkReadiness(
        key=key,
        name=name,
        total=len(codes),
        assessed=len(assessed),
        implemented=states["implemented"],
        partial=states["partially_implemented"],
        not_implemented=states["not_implemented"],
        not_applicable=states["not_applicable"],
        has_axes=bool(_axes(requirements)),
        scope_defined=_scope(session, org, key) is not None,
        review_on=review.reviewed_on if review else None,
        overdue=len([d for d in dues if d is not None and d < today]),
        unowned_open=len([c for c in open_codes if c not in owned]),
        open_by_owner={u: n for u, n in owners.items() if u is not None},
        last_assessed_at=max((a.recorded_at for a in assessed.values()), default=None),
    )
