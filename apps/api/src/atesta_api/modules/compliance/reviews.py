"""Human review of manual controls (manual-control-review spec, FR-07, ADR-005).

Only a person decides a manual control, and only for controls the catalog marks manual: a review
never overrides an automated check. The rationale is customer content: it is stored and returned
to members of the org, never logged and never copied into audit metadata (rule 2).

A pass cites the evidence it rests on (#262): at least one item of the org linked to the control,
checked through evidence.api. A fail may cite none. Reviews recorded before cite none.
"""

import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.models import Control, ControlReview
from atesta_api.modules.evidence.api import CitedEvidence, cited_evidence
from atesta_api.modules.identity.api import Member, Role, require_member, require_role
from atesta_api.modules.scanning.api import RESCORE_TASK
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession
from atesta_api.platform.queue import defer

MAX_VALIDITY = timedelta(days=3 * 365 + 1)  # three years, one leap day included
MAX_CITED = 20  # control_reviews.evidence_ids CHECK
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # tab and line feed allowed

router = APIRouter(prefix="/api/v1/orgs/{org_id}/controls/{control_key}", tags=["compliance"])

type ReviewStatus = Literal["pass", "fail"]


def utc_today() -> date:
    return datetime.now(UTC).date()


class ReviewIn(BaseModel):
    status: ReviewStatus
    rationale: str
    valid_until: date
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_CITED)

    @field_validator("evidence_ids")
    @classmethod
    def each_once(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(value))  # first-seen order

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


class CitedEvidenceOut(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    collected_at: datetime


class ReviewOut(BaseModel):
    id: uuid.UUID
    control_key: str
    status: ReviewStatus
    rationale: str
    valid_until: date
    reviewed_by: uuid.UUID
    reviewed_at: datetime
    expired: bool
    evidence: list[CitedEvidenceOut]


def review_out(
    row: ControlReview, cited: Mapping[uuid.UUID, CitedEvidence], today: date | None = None
) -> ReviewOut:
    return ReviewOut(
        id=row.id,
        control_key=row.control_key,
        status="pass" if row.status == "pass" else "fail",
        rationale=row.rationale,
        valid_until=row.valid_until,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        expired=row.valid_until < (today or utc_today()),
        evidence=[
            CitedEvidenceOut(id=e.id, title=e.title, kind=e.kind, collected_at=e.collected_at)
            for e in (cited.get(i) for i in row.evidence_ids)
            if e is not None
        ],
    )


def _reviews_out(
    session: Session, organization_id: uuid.UUID, rows: Sequence[ControlReview]
) -> list[ReviewOut]:
    """Reviews with their cited evidence, read in one query."""
    cited = cited_evidence(session, organization_id, (i for r in rows for i in r.evidence_ids))
    today = utc_today()
    return [review_out(row, cited, today) for row in rows]


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
    ).all()
    return {r.control_key: r for r in _reviews_out(session, organization_id, rows)}


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
    if body.status == "pass" and not body.evidence_ids:
        raise HTTPException(422, detail={"code": "compliance.review_evidence_required"})
    cited = cited_evidence(session, member.organization_id, body.evidence_ids, control_key)
    if len(cited) != len(body.evidence_ids):  # another control's, another org's or unknown
        raise HTTPException(422, detail={"code": "compliance.review_evidence_invalid"})
    review = ControlReview(
        organization_id=member.organization_id,
        control_key=control_key,
        status=body.status,
        rationale=body.rationale,
        valid_until=body.valid_until,
        reviewed_by=member.user_id,
        evidence_ids=body.evidence_ids,
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
        metadata={
            "status": body.status,
            "valid_until": body.valid_until.isoformat(),
            "evidence_count": len(body.evidence_ids),
        },
    )
    # The score moves through a correction of the latest snapshot, committed with the review.
    defer(session, RESCORE_TASK, queue="scans", organization_id=str(member.organization_id))
    return review_out(review, cited)


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
    ).all()
    return _reviews_out(session, member.organization_id, rows)
