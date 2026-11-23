"""Recorded routines, part A (recorded-routines spec): access reviews and policy approvals.

Each finished routine writes an evidence statement on its common control through evidence.api,
in the language of the person who finishes it. Atesta records decisions; it never changes the
customer's systems (rule 1) and never decides whether a measure is met (ADR-005).
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal, cast

from atesta_core.dates import add_months
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.incidents import open_incidents
from atesta_api.modules.compliance.models import (
    AccessReview,
    AccessReviewDecision,
    AccessReviewEntry,
    Policy,
    PolicyApproval,
)
from atesta_api.modules.compliance.text import collapse, filled
from atesta_api.modules.compliance.training import unclosed_campaigns
from atesta_api.modules.evidence.api import record_attestation, refuse_credential_link
from atesta_api.modules.identity.api import Member, Role, person, require_member, require_role
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession
from atesta_api.platform.i18n import Locale, message

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["compliance"])

ACCESS_CONTROL = "ctl.access_review"
POLICY_CONTROL = "ctl.security_governance"
DUE_SOON_DAYS = 30

type Decision = Literal["keep", "revoke"]


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status, detail={"code": code})


def _say(locale: str, key: str, **values: object) -> str:
    lang = cast(Locale, locale if locale in ("es", "en") else "es")
    return message(lang, f"routines.{key}").format(**values)


# --- access reviews ------------------------------------------------------------------------


class AccountIn(BaseModel):
    account: str = Field(min_length=1, max_length=320)
    detail: str = Field(default="", max_length=200)

    @field_validator("account")
    @classmethod
    def tidy(cls, value: str) -> str:
        return filled(value)

    @field_validator("detail")
    @classmethod
    def tidy_detail(cls, value: str) -> str:
        return collapse(value)


class AccessReviewIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    system: str = Field(min_length=1, max_length=200)
    due_on: date | None = None
    accounts: list[AccountIn] = Field(min_length=1, max_length=2000)

    @field_validator("title", "system")
    @classmethod
    def tidy(cls, value: str) -> str:
        return filled(value)


class AccessReviewSummary(BaseModel):
    id: uuid.UUID
    title: str
    system: str
    due_on: date | None
    created_at: datetime
    closed_at: datetime | None
    total: int
    keep: int
    revoke: int
    pending: int


class EntryOut(BaseModel):
    id: uuid.UUID
    account: str
    detail: str
    decision: Decision | None
    note: str
    decided_at: datetime | None


class AccessReviewOut(AccessReviewSummary):
    entries: list[EntryOut]


class DecisionIn(BaseModel):
    entry_id: uuid.UUID
    decision: Decision
    note: str = Field(default="", max_length=1000)


def _review(session: Session, org: uuid.UUID, review_id: uuid.UUID) -> AccessReview:
    row = session.scalar(
        select(AccessReview).where(
            AccessReview.organization_id == org, AccessReview.id == review_id
        )
    )
    if row is None:
        raise _error(404, "compliance.access_review_not_found")
    return row


def _entries(session: Session, org: uuid.UUID, review_id: uuid.UUID) -> list[EntryOut]:
    latest = (
        select(AccessReviewDecision)
        .where(AccessReviewDecision.organization_id == org)
        .ext(distinct_on(AccessReviewDecision.entry_id))
        .order_by(
            AccessReviewDecision.entry_id,
            AccessReviewDecision.decided_at.desc(),
            AccessReviewDecision.id.desc(),
        )
        .subquery()
    )
    rows = session.execute(
        select(AccessReviewEntry, latest.c.decision, latest.c.note, latest.c.decided_at)
        .outerjoin(latest, latest.c.entry_id == AccessReviewEntry.id)
        .where(AccessReviewEntry.organization_id == org, AccessReviewEntry.review_id == review_id)
        .order_by(AccessReviewEntry.account, AccessReviewEntry.id)
    ).all()
    return [
        EntryOut(
            id=e.id, account=e.account, detail=e.detail, decision=d, note=n or "", decided_at=at
        )
        for e, d, n, at in rows
    ]


def _summary(row: AccessReview, entries: list[EntryOut]) -> AccessReviewSummary:
    keep = sum(1 for e in entries if e.decision == "keep")
    revoke = sum(1 for e in entries if e.decision == "revoke")
    return AccessReviewSummary(
        id=row.id,
        title=row.title,
        system=row.system,
        due_on=row.due_on,
        created_at=row.created_at,
        closed_at=row.closed_at,
        total=len(entries),
        keep=keep,
        revoke=revoke,
        pending=len(entries) - keep - revoke,
    )


@router.post("/access-reviews", status_code=201)
def create_access_review(
    body: AccessReviewIn,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> AccessReviewOut:
    return start_access_review(session, member.organization_id, member.user_id, body)


def start_access_review(
    session: Session,
    org: uuid.UUID,
    author: uuid.UUID,
    body: AccessReviewIn,
    via: Mapping[str, str] | None = None,
) -> AccessReviewOut:
    review = AccessReview(
        organization_id=org,
        title=body.title,
        system=body.system,
        due_on=body.due_on,
        created_by=author,
    )
    session.add(review)
    session.flush()
    session.add_all(
        AccessReviewEntry(
            organization_id=org, review_id=review.id, account=a.account, detail=a.detail
        )
        for a in body.accounts
    )
    session.flush()
    session.refresh(review)
    record(
        session,
        organization_id=org,
        action="access_review.created",
        target_type="access_review",
        target_id=str(review.id),
        actor_user_id=author,
        metadata={"accounts": len(body.accounts), **(via or {})},
    )
    entries = _entries(session, org, review.id)
    return AccessReviewOut(**_summary(review, entries).model_dump(), entries=entries)


@router.get("/access-reviews")
def list_access_reviews(
    member: Annotated[Member, Depends(require_member)], session: DbSession
) -> list[AccessReviewSummary]:
    org = member.organization_id
    reviews = session.scalars(
        select(AccessReview)
        .where(AccessReview.organization_id == org)
        .order_by(AccessReview.created_at.desc())
    ).all()
    return [_summary(r, _entries(session, org, r.id)) for r in reviews]


@router.get("/access-reviews/{review_id}")
def read_access_review(
    review_id: uuid.UUID, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> AccessReviewOut:
    review = _review(session, member.organization_id, review_id)
    entries = _entries(session, member.organization_id, review_id)
    return AccessReviewOut(**_summary(review, entries).model_dump(), entries=entries)


@router.post("/access-reviews/{review_id}/decisions", status_code=201)
def decide(
    review_id: uuid.UUID,
    body: DecisionIn,
    member: Annotated[Member, Depends(require_role(Role.MEMBER))],
    session: DbSession,
) -> EntryOut:
    org = member.organization_id
    review = _review(session, org, review_id)
    if review.closed_at is not None:
        raise HTTPException(409, detail={"code": "compliance.access_review_closed"})
    entry = session.scalar(
        select(AccessReviewEntry).where(
            AccessReviewEntry.organization_id == org,
            AccessReviewEntry.review_id == review_id,
            AccessReviewEntry.id == body.entry_id,
        )
    )
    if entry is None:
        raise _error(404, "compliance.access_review_entry_not_found")
    row = AccessReviewDecision(
        organization_id=org,
        entry_id=entry.id,
        decision=body.decision,
        note=collapse(body.note),
        decided_by=member.user_id,
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    record(
        session,
        organization_id=org,
        action="access_review.decided",
        target_type="access_review",
        target_id=str(review_id),
        actor_user_id=member.user_id,
        metadata={"decision": body.decision},
    )
    return EntryOut(
        id=entry.id,
        account=entry.account,
        detail=entry.detail,
        decision=body.decision,
        note=row.note,
        decided_at=row.decided_at,
    )


@router.post("/access-reviews/{review_id}/close")
def close_access_review(
    review_id: uuid.UUID,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> AccessReviewOut:
    org = member.organization_id
    review = _review(session, org, review_id)
    if review.closed_at is not None:
        raise HTTPException(409, detail={"code": "compliance.access_review_closed"})
    entries = _entries(session, org, review_id)
    summary = _summary(review, entries)
    if summary.pending:
        raise HTTPException(409, detail={"code": "compliance.access_review_pending"})
    now = datetime.now(UTC)
    session.execute(
        update(AccessReview)
        .where(
            AccessReview.organization_id == org,
            AccessReview.id == review_id,
            AccessReview.closed_at.is_(None),
        )
        .values(closed_at=now, closed_by=member.user_id)
    )
    email, locale = person(session, member.user_id)
    record_attestation(
        session,
        organization_id=org,
        author=member.user_id,
        control_key=ACCESS_CONTROL,
        title=_say(locale, "access_review_title", title=review.title),
        statement=_say(
            locale,
            "access_review_closed",
            title=review.title,
            system=review.system,
            total=summary.total,
            keep=summary.keep,
            revoke=summary.revoke,
            date=now.date().isoformat(),
            email=email,
        ),
    )
    record(
        session,
        organization_id=org,
        action="access_review.closed",
        target_type="access_review",
        target_id=str(review_id),
        actor_user_id=member.user_id,
        metadata={"keep": summary.keep, "revoke": summary.revoke},
    )
    session.refresh(review)
    return AccessReviewOut(**_summary(review, entries).model_dump(), entries=entries)


# --- policies ------------------------------------------------------------------------------


class PolicyIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    location_url: str = Field(min_length=9, max_length=2000, pattern=r"^https://\S+$")
    review_months: int = Field(ge=1, le=36)

    @field_validator("title")
    @classmethod
    def tidy(cls, value: str) -> str:
        return filled(value)

    @field_validator("location_url")
    @classmethod
    def no_credential_link(cls, value: str) -> str:
        """Approval copies it into append-only evidence (rule 2, #256)."""
        return refuse_credential_link(value)


class ApprovalIn(BaseModel):
    version: str = Field(min_length=1, max_length=50)
    approver_name: str = Field(min_length=1, max_length=200)
    approved_on: date
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("version", "approver_name")
    @classmethod
    def tidy(cls, value: str) -> str:
        return filled(value)


class ApprovalOut(BaseModel):
    version: str
    approver_name: str
    approved_on: date
    sha256: str | None
    recorded_at: datetime


class PolicyOut(BaseModel):
    id: uuid.UUID
    title: str
    location_url: str
    review_months: int
    created_at: datetime
    latest: ApprovalOut | None
    next_review_on: date | None


def _latest_approvals(session: Session, org: uuid.UUID) -> dict[uuid.UUID, PolicyApproval]:
    rows = session.scalars(
        select(PolicyApproval)
        .where(PolicyApproval.organization_id == org)
        .ext(distinct_on(PolicyApproval.policy_id))
        .order_by(
            PolicyApproval.policy_id, PolicyApproval.recorded_at.desc(), PolicyApproval.id.desc()
        )
    )
    return {r.policy_id: r for r in rows}


def _policy_out(policy: Policy, latest: PolicyApproval | None) -> PolicyOut:
    return PolicyOut(
        id=policy.id,
        title=policy.title,
        location_url=policy.location_url,
        review_months=policy.review_months,
        created_at=policy.created_at,
        latest=ApprovalOut.model_validate(latest, from_attributes=True) if latest else None,
        next_review_on=add_months(latest.approved_on, policy.review_months) if latest else None,
    )


@router.post("/policies", status_code=201)
def create_policy(
    body: PolicyIn, member: Annotated[Member, Depends(require_role(Role.ADMIN))], session: DbSession
) -> PolicyOut:
    policy = Policy(
        organization_id=member.organization_id,
        title=body.title,
        location_url=body.location_url,
        review_months=body.review_months,
        created_by=member.user_id,
    )
    session.add(policy)
    session.flush()
    session.refresh(policy)
    record(
        session,
        organization_id=member.organization_id,
        action="policy.created",
        target_type="policy",
        target_id=str(policy.id),
        actor_user_id=member.user_id,
    )
    return _policy_out(policy, None)


@router.get("/policies")
def list_policies(
    member: Annotated[Member, Depends(require_member)], session: DbSession
) -> list[PolicyOut]:
    org = member.organization_id
    latest = _latest_approvals(session, org)
    policies = session.scalars(
        select(Policy).where(Policy.organization_id == org).order_by(Policy.title, Policy.id)
    )
    return [_policy_out(p, latest.get(p.id)) for p in policies]


@router.post("/policies/{policy_id}/approvals", status_code=201)
def approve_policy(
    policy_id: uuid.UUID,
    body: ApprovalIn,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> PolicyOut:
    org = member.organization_id
    policy = session.scalar(
        select(Policy).where(Policy.organization_id == org, Policy.id == policy_id)
    )
    if policy is None:
        raise _error(404, "compliance.policy_not_found")
    approval = PolicyApproval(
        organization_id=org,
        policy_id=policy.id,
        version=body.version,
        sha256=body.sha256,
        approver_name=body.approver_name,
        approved_on=body.approved_on,
        recorded_by=member.user_id,
    )
    session.add(approval)
    session.flush()
    session.refresh(approval)
    email, locale = person(session, member.user_id)
    statement = _say(
        locale,
        "policy_approved",
        title=policy.title,
        version=body.version,
        approver=body.approver_name,
        date=body.approved_on.isoformat(),
        email=email,
    )
    if body.sha256:
        statement += _say(locale, "policy_hash", sha256=body.sha256)
    record_attestation(
        session,
        organization_id=org,
        author=member.user_id,
        control_key=POLICY_CONTROL,
        title=_say(locale, "policy_title", title=policy.title),
        statement=statement,
        reference_url=policy.location_url,
    )
    record(
        session,
        organization_id=org,
        action="policy.approved",
        target_type="policy",
        target_id=str(policy.id),
        actor_user_id=member.user_id,
        metadata={"version": body.version},
    )
    return _policy_out(policy, approval)


# --- what falls due ------------------------------------------------------------------------


class ClockLabel(BaseModel):
    es: str
    en: str
    framework: str


class DueItem(BaseModel):
    kind: Literal[
        "policy_review",
        "policy_unapproved",
        "access_review_overdue",
        "training_unclosed",
        "incident_clock",
    ]
    id: uuid.UUID
    title: str
    due_on: date | None
    overdue: bool
    due_at: datetime | None = None  # incident clocks run to the minute
    clock: ClockLabel | None = None


@router.get("/routines/due")
def routines_due(
    member: Annotated[Member, Depends(require_member)], session: DbSession
) -> list[DueItem]:
    return due_items(session, member.organization_id)


def due_items(session: Session, org: uuid.UUID) -> list[DueItem]:
    """What falls due in the organization, overdue first (the app and API keys share it)."""
    today = datetime.now().astimezone().date()
    soon = today + timedelta(days=DUE_SOON_DAYS)
    latest = _latest_approvals(session, org)
    items: list[DueItem] = []
    for policy in session.scalars(
        select(Policy).where(Policy.organization_id == org).order_by(Policy.title)
    ):
        approval = latest.get(policy.id)
        if approval is None:
            items.append(
                DueItem(
                    kind="policy_unapproved",
                    id=policy.id,
                    title=policy.title,
                    due_on=None,
                    overdue=False,
                )
            )
            continue
        due = add_months(approval.approved_on, policy.review_months)
        if due <= soon:
            items.append(
                DueItem(
                    kind="policy_review",
                    id=policy.id,
                    title=policy.title,
                    due_on=due,
                    overdue=due < today,
                )
            )
    overdue_reviews = session.scalars(
        select(AccessReview).where(
            AccessReview.organization_id == org,
            AccessReview.closed_at.is_(None),
            AccessReview.due_on.is_not(None),
            AccessReview.due_on < today,
        )
    )
    items += [
        DueItem(kind="access_review_overdue", id=r.id, title=r.title, due_on=r.due_on, overdue=True)
        for r in overdue_reviews
    ]
    items += [
        DueItem(kind="training_unclosed", id=c.id, title=c.title, due_on=c.closes_on, overdue=True)
        for c in unclosed_campaigns(session, org)
    ]
    for incident in open_incidents(session, org):
        for clock in incident.clocks:
            if clock.state not in ("running", "overdue") or clock.due_at is None:
                continue
            items.append(
                DueItem(
                    kind="incident_clock",
                    id=incident.id,
                    title=incident.title,
                    due_on=clock.due_at.date(),
                    due_at=clock.due_at,
                    overdue=clock.state == "overdue",
                    clock=ClockLabel(
                        es=clock.title_es, en=clock.title_en, framework=clock.framework_name
                    ),
                )
            )
    return sorted(
        items,
        key=lambda i: (
            not i.overdue,
            i.due_at or datetime.combine(i.due_on or date.max, datetime.min.time(), UTC),
        ),
    )
