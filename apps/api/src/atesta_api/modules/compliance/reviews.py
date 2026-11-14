"""Human review of manual controls (manual-control-review spec, FR-07, ADR-005).

Only a person decides a manual control, and only for controls the catalog marks manual: a review
never overrides an automated check. The rationale is customer content: it is stored and returned
to members of the org, never logged and never copied into audit metadata (rule 2).
"""

import re
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.models import Control, ControlReview
from atesta_api.modules.identity.api import Member, Role, require_member, require_role
from atesta_api.modules.scanning.api import RESCORE_TASK
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession
from atesta_api.platform.queue import defer

MAX_VALIDITY = timedelta(days=3 * 365 + 1)  # three years, one leap day included
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # tab and line feed allowed

router = APIRouter(prefix="/api/v1/orgs/{org_id}/controls/{control_key}", tags=["compliance"])

type ReviewStatus = Literal["pass", "fail"]


def utc_today() -> date:
    return datetime.now(UTC).date()


class ReviewIn(BaseModel):
    status: ReviewStatus
    rationale: str
    valid_until: date

    @field_validator("rationale")
    @classmethod
    def clean_rationale(cls, value: str) -> str:
        text = value.replace("\r\n", "\n").strip()
        if not 1 <= len(text) <= 2000 or _CONTROL_CHARACTERS.search(text):
            raise ValueError("rationale must be 1-2000 characters without control characters")
        return text

    @field_validator("valid_until")
    @classmethod
    def within_validity(cls, value: date) -> date:
        today = utc_today()
        if not today < value <= today + MAX_VALIDITY:
            raise ValueError("valid_until must be after today and at most three years ahead")
        return value


class ReviewOut(BaseModel):
    id: uuid.UUID
    control_key: str
    status: ReviewStatus
    rationale: str
    valid_until: date
    reviewed_by: uuid.UUID
    reviewed_at: datetime
    expired: bool


def review_out(row: ControlReview, today: date | None = None) -> ReviewOut:
    return ReviewOut(
        id=row.id,
        control_key=row.control_key,
        status="pass" if row.status == "pass" else "fail",
        rationale=row.rationale,
        valid_until=row.valid_until,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        expired=row.valid_until < (today or utc_today()),
    )


def _not_found() -> HTTPException:
    return HTTPException(404, detail={"code": "compliance.control_not_found"})


def current_reviews(
    session: Session, organization_id: uuid.UUID, control_keys: Iterable[str]
) -> dict[str, ReviewOut]:
    """The latest review of each given control in the org, expired ones included."""
    keys = sorted(set(control_keys))
    if not keys:
        return {}
    rows = session.scalars(
        select(ControlReview)
        .where(
            ControlReview.organization_id == organization_id,
            ControlReview.control_key.in_(keys),
        )
        .ext(distinct_on(ControlReview.control_key))
        .order_by(
            ControlReview.control_key, ControlReview.reviewed_at.desc(), ControlReview.id.desc()
        )
    )
    today = utc_today()
    return {row.control_key: review_out(row, today) for row in rows}


@router.post("/reviews", status_code=201)
def record_review(
    control_key: str,
    body: ReviewIn,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> ReviewOut:
    manual = session.execute(
        select(Control.manual).where(Control.key == control_key, Control.retired_at.is_(None))
    ).scalar()
    if manual is None:
        raise _not_found()
    if not manual:
        raise HTTPException(409, detail={"code": "compliance.control_not_manual"})
    review = ControlReview(
        organization_id=member.organization_id,
        control_key=control_key,
        status=body.status,
        rationale=body.rationale,
        valid_until=body.valid_until,
        reviewed_by=member.user_id,
    )
    session.add(review)
    session.flush()
    session.refresh(review)
    record(
        session,
        organization_id=member.organization_id,
        action="control.reviewed",
        target_type="control",
        target_id=control_key,
        actor_user_id=member.user_id,
        metadata={"status": body.status, "valid_until": body.valid_until.isoformat()},
    )
    # The score moves through a correction of the latest snapshot, committed with the review.
    defer(session, RESCORE_TASK, queue="scans", organization_id=str(member.organization_id))
    return review_out(review)


@router.get("/reviews")
def list_reviews(
    control_key: str,
    member: Annotated[Member, Depends(require_member)],
    session: DbSession,
) -> list[ReviewOut]:
    rows = session.scalars(
        select(ControlReview)
        .where(
            ControlReview.organization_id == member.organization_id,
            ControlReview.control_key == control_key,
        )
        .order_by(ControlReview.reviewed_at.desc(), ControlReview.id.desc())
    )
    today = utc_today()
    return [review_out(row, today) for row in rows]
