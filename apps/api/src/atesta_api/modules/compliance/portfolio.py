"""The portfolio: one row per organization of the caller (consultancy-portfolio spec, issue 228).

ADR-012 amendment 10: the caller's organizations are read one at a time, each in its own
read-only transaction and tenant context, through the caller's own membership. No query sees
two organizations. Counts only, never a compliance score (ADR-005).
"""

import logging
import uuid
from datetime import datetime

from atesta_core.portfolio import FrameworkCounts, Summary, summarize, urgency
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from atesta_api.modules.compliance.readiness import organization_readiness
from atesta_api.modules.compliance.routines import due_items
from atesta_api.modules.identity.api import (
    CurrentCaller,
    OwnOrganization,
    Role,
    member_read,
    own_organizations,
)
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/api/v1", tags=["compliance"])
MAX_ORGANIZATIONS = 250  # one request never reads more; the rest are counted in `not_shown`
log = logging.getLogger("atesta.portfolio")


class PortfolioSummary(BaseModel):
    frameworks_in_progress: int
    assessed: int
    total: int
    overdue: int
    pending: int
    pending_overdue: int
    last_assessed_at: datetime | None


class PortfolioRow(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    role: Role
    summary: PortfolioSummary | None  # None: this organization could not be read


class PortfolioOut(BaseModel):
    rows: list[PortfolioRow]  # most urgent first
    not_shown: int  # organizations beyond the limit, not read


def _summary(subject: str, user_id: uuid.UUID, org: OwnOrganization) -> Summary | None:
    """One organization, in its own transaction. A failure costs this row only (spec)."""
    try:
        with member_read(subject, user_id, org.organization_id) as (session, member):
            frameworks = organization_readiness(session, member.organization_id)
            due = due_items(session, member.organization_id)
    except HTTPException:
        return None  # access that expired, or a membership removed since the list was read
    except Exception as failure:  # noqa: BLE001 - one organization must not hide the others
        # The type and the id only: an error message can quote customer content (rule 2).
        log.warning(
            "portfolio row failed: organization %s, %s",
            org.organization_id,
            type(failure).__name__,
        )
        return None
    return summarize(
        (FrameworkCounts(f.total, f.assessed, f.overdue, f.last_assessed_at) for f in frameworks),
        [item.overdue for item in due],
    )


@router.get("/portfolio")
def read_portfolio(caller: CurrentCaller, session: DbSession) -> PortfolioOut:
    organizations = own_organizations(session, caller.user_id)
    read = organizations[:MAX_ORGANIZATIONS]
    found = [(org, _summary(caller.sub, caller.user_id, org)) for org in read]
    found.sort(key=lambda pair: urgency(pair[0].name, pair[1]))
    return PortfolioOut(
        rows=[
            PortfolioRow(
                organization_id=org.organization_id,
                organization_name=org.name,
                role=org.role,
                summary=(
                    None
                    if summary is None
                    else PortfolioSummary.model_validate(summary, from_attributes=True)
                ),
            )
            for org, summary in found
        ],
        not_shown=len(organizations) - len(read),
    )
