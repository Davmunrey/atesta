"""Self-assessment proposals from API keys (mcp-server spec, #339; ADR-005, ADR-016).

A key with assessment:propose stores a pending proposal; it changes no measure, score or count.
A person who may assess the measure confirms it, which records the assessment as theirs, or
rejects it. Free text is customer content: stored and returned, never logged (rule 2).
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from atesta_api.modules.billing.api import require_framework
from atesta_api.modules.compliance.models import AssessmentProposal, Framework
from atesta_api.modules.compliance.plan_gate import framework_in_plan
from atesta_api.modules.compliance.register import (
    AssessmentIn,
    AssessmentOut,
    _clean,
    _framework,
    check_assessment,
    may_assess,
    requirement_of,
    write_assessment,
)
from atesta_api.modules.identity.api import (
    ApiCaller,
    Member,
    QueryFreeRoute,
    Role,
    require_role,
    require_scope,
)
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession

router = APIRouter(
    prefix="/api/v1/orgs/{org_id}/frameworks/{framework_key}",
    tags=["compliance"],
    dependencies=[Depends(framework_in_plan)],
)
token_router = APIRouter(prefix="/api/v1", tags=["api-keys"], route_class=QueryFreeRoute)
Proposer = Annotated[ApiCaller, Depends(require_scope("assessment:propose"))]
Assessor = Annotated[Member, Depends(require_role(Role.MEMBER))]


class ProposalIn(AssessmentIn):
    rationale: str  # why the agent proposes it; a person reads it before deciding

    @field_validator("rationale")
    @classmethod
    def reason(cls, value: str) -> str:
        return _clean(value, 2000, minimum=1)


class ProposalRecord(BaseModel):
    id: uuid.UUID
    framework_key: str
    code: str
    status: Literal["pending", "confirmed", "rejected"]
    proposed_at: datetime
    decided_at: datetime | None


def _record_out(row: AssessmentProposal) -> ProposalRecord:
    return ProposalRecord(
        id=row.id,
        framework_key=row.framework_key,
        code=row.requirement_code,
        status=row.status,  # type: ignore[arg-type]  # CHECK constraint: one of the three
        proposed_at=row.proposed_at,
        decided_at=row.decided_at,
    )


def framework_for_key(session: Session, org: uuid.UUID, framework_key: str) -> Framework:
    """404 for an unknown framework, then 403 billing.plan_limit, as framework_in_plan does."""
    framework = _framework(session, framework_key)
    require_framework(session, org, framework_key)
    return framework


@token_router.post("/frameworks/{framework_key}/measures/{code}/proposals", status_code=201)
def propose(
    framework_key: str, code: str, body: ProposalIn, caller: Proposer, session: DbSession
) -> ProposalRecord:
    org = caller.organization_id
    framework = framework_for_key(session, org, framework_key)
    requirement = requirement_of(session, framework_key, code)
    check_assessment(session, org, framework, requirement, body)
    values = body.model_dump()
    values["evidence_statement_ids"] = sorted(set(body.evidence_statement_ids))
    statement = (
        insert(AssessmentProposal)
        .values(
            id=uuid.uuid4(),
            organization_id=org,
            framework_key=framework_key,
            requirement_code=code,
            token_id=caller.token_id,
            proposed_by=caller.created_by,
            **values,
        )
        .on_conflict_do_nothing(
            index_elements=["organization_id", "framework_key", "requirement_code"],
            index_where=AssessmentProposal.status == "pending",
        )
        .returning(AssessmentProposal.id)
    )
    proposal_id = session.scalar(statement)
    if proposal_id is None:
        raise HTTPException(409, detail={"code": "compliance.proposal_pending"})
    record(
        session,
        organization_id=org,
        action="assessment_proposal.created",
        target_type="requirement",
        target_id=f"{framework_key}:{code}",
        actor_user_id=caller.created_by,
        metadata={
            "via": "api_token",
            "token_id": str(caller.token_id),
            "token": caller.prefix,
            "proposal_id": str(proposal_id),
        },
    )
    row = session.get_one(AssessmentProposal, proposal_id)
    return _record_out(row)


def _pending(
    session: Session, member: Member, framework_key: str, proposal_id: uuid.UUID
) -> AssessmentProposal:
    row = session.scalar(
        select(AssessmentProposal).where(
            AssessmentProposal.organization_id == member.organization_id,
            AssessmentProposal.framework_key == framework_key,
            AssessmentProposal.id == proposal_id,
        )
    )
    if row is None:
        raise HTTPException(404, detail={"code": "compliance.proposal_not_found"})
    if row.status != "pending":
        raise HTTPException(409, detail={"code": "compliance.proposal_decided"})
    may_assess(session, member, framework_key, row.requirement_code)
    return row


def _decide(
    session: Session,
    member: Member,
    row: AssessmentProposal,
    status: str,
    action: str,
    assessment_id: uuid.UUID | None = None,
) -> AssessmentProposal:
    """Only a pending row changes, once: a concurrent decision gets 409."""
    decided = session.scalar(
        update(AssessmentProposal)
        .where(
            AssessmentProposal.organization_id == member.organization_id,
            AssessmentProposal.id == row.id,
            AssessmentProposal.status == "pending",
        )
        .values(
            status=status,
            decided_by=member.user_id,
            decided_at=datetime.now(UTC),
            assessment_id=assessment_id,
        )
        .returning(AssessmentProposal)
        .execution_options(populate_existing=True)
    )
    if decided is None:
        raise HTTPException(409, detail={"code": "compliance.proposal_decided"})
    record(
        session,
        organization_id=member.organization_id,
        action=action,
        target_type="requirement",
        target_id=f"{row.framework_key}:{row.requirement_code}",
        actor_user_id=member.user_id,
        metadata={"proposal_id": str(row.id), "token_id": str(row.token_id)},
    )
    return decided


@router.post("/proposals/{proposal_id}/confirm", status_code=201)
def confirm(
    framework_key: str, proposal_id: uuid.UUID, member: Assessor, session: DbSession
) -> AssessmentOut:
    """The person's assessment, exactly as proposed; checked again against today's rules."""
    row = _pending(session, member, framework_key, proposal_id)
    org = member.organization_id
    framework = _framework(session, framework_key)
    requirement = requirement_of(session, framework_key, row.requirement_code)
    body = AssessmentIn.model_validate(row, from_attributes=True)
    differs = check_assessment(session, org, framework, requirement, body)
    assessment = write_assessment(
        session, org, requirement, body, member.user_id, differs, from_proposal=True
    )
    _decide(
        session,
        member,
        row,
        "confirmed",
        action="assessment_proposal.confirmed",
        assessment_id=assessment.id,
    )
    return AssessmentOut.model_validate(assessment, from_attributes=True)


@router.post("/proposals/{proposal_id}/reject")
def reject(
    framework_key: str, proposal_id: uuid.UUID, member: Assessor, session: DbSession
) -> ProposalRecord:
    row = _pending(session, member, framework_key, proposal_id)
    return _record_out(
        _decide(session, member, row, "rejected", action="assessment_proposal.rejected")
    )
