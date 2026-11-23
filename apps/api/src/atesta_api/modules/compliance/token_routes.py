"""What an API key may read and record (api-keys-v2 spec #341; mcp-server spec #333).

Reads: the compliance state and incidents. Writes (routines:write): incidents and their updates,
training campaigns and access reviews; deciding or closing a review stays with a person. The
author of a write is the admin who owns the key, and its audit event names the key.

Every route runs in the key's own organization, which identity resolved from the key (ADR-012
amendment 6); no route takes an organization. The answers reuse the functions behind the app's
routes, so a key reads what a member reads. The plan decides frameworks as it does in the app.
Free text in answers is customer content: the MCP server frames it as data (rule 5).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.billing.api import entitlements, has_framework
from atesta_api.modules.compliance.catalog_schema import ExpectedEvidenceItem, RequirementContext
from atesta_api.modules.compliance.detail_context import public_context
from atesta_api.modules.compliance.incidents import (
    IncidentIn,
    IncidentOut,
    UpdateIn,
    _incident,
    _out,
    _updates,
    add_incident_update,
    clock_defs,
    open_incidents,
    record_incident,
)
from atesta_api.modules.compliance.models import Mapping
from atesta_api.modules.compliance.proposal_view import pending_proposals
from atesta_api.modules.compliance.proposals import framework_for_key
from atesta_api.modules.compliance.readiness import FrameworkReadiness, framework_readiness
from atesta_api.modules.compliance.register import (
    AssessmentOut,
    ProposalOut,
    _assessments,
    _assignments,
    _profile_levels,
    _proposal,
    _requirements,
    _scope,
)
from atesta_api.modules.compliance.routines import (
    AccessReviewIn,
    AccessReviewOut,
    DueItem,
    due_items,
    start_access_review,
)
from atesta_api.modules.compliance.scoring import FrameworkInfo, active_frameworks
from atesta_api.modules.compliance.training import CampaignIn, CreatedCampaign, start_campaign
from atesta_api.modules.identity.api import (
    ApiCaller,
    QueryFreeRoute,
    annotate_scopes,
    require_scope,
)
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/api/v1", tags=["api-keys"], route_class=QueryFreeRoute)
ComplianceReader = Annotated[ApiCaller, Depends(require_scope("compliance:read"))]
IncidentReader = Annotated[ApiCaller, Depends(require_scope("incidents:read"))]
RoutineWriter = Annotated[ApiCaller, Depends(require_scope("routines:write"))]

type GapState = Literal["not_assessed", "not_implemented", "partially_implemented"]


class MeasureOut(BaseModel):
    code: str
    title_es: str
    title_en: str | None
    proposal: ProposalOut
    assessment: AssessmentOut | None
    due_on: date | None
    pending_proposal_id: uuid.UUID | None  # an API key's proposal awaiting a person


class Citation(BaseModel):
    source: str
    section: str | None
    source_sha256: str | None
    catalog_version: str | None
    framework_version: str


class MeasureDetail(BaseModel):
    framework_key: str
    code: str
    title_es: str
    title_en: str | None
    official_text_es: str | None
    official_text_en: str | None
    applicability_es: str | None
    citation: Citation
    expected_evidence: list[ExpectedEvidenceItem]
    controls: list[str]
    assessment: AssessmentOut | None


class Gap(BaseModel):
    framework_key: str
    framework_name: str
    code: str
    title_es: str
    title_en: str | None
    state: GapState
    due_on: date | None


def _today() -> date:
    return datetime.now().astimezone().date()


def _granted(session: Session, org: uuid.UUID) -> list[FrameworkInfo]:
    held = entitlements(session, org)
    return [
        f for f in active_frameworks(session) if has_framework(held.plan, f.key, addons=held.addons)
    ]


@router.get("/frameworks")
def list_frameworks(caller: ComplianceReader, session: DbSession) -> list[FrameworkReadiness]:
    org, today = caller.organization_id, _today()
    found = (
        framework_readiness(session, org, f.key, f.name, today) for f in _granted(session, org)
    )
    return [f for f in found if f is not None]


@router.get("/frameworks/{framework_key}/measures")
def list_measures(
    framework_key: str, caller: ComplianceReader, session: DbSession
) -> list[MeasureOut]:
    org = caller.organization_id
    framework = framework_for_key(session, org, framework_key)
    scope = _scope(session, org, framework_key)
    profile = _profile_levels(framework, scope)
    assessed = _assessments(session, org, framework_key)
    assigned = _assignments(session, org, framework_key)
    pending = pending_proposals(session, org, framework_key)
    return [
        MeasureOut(
            code=r.code,
            title_es=r.title_es,
            title_en=r.title_en,
            proposal=_proposal(r, scope, profile),
            assessment=assessed.get(r.code),
            due_on=assigned[r.code].due_on if r.code in assigned else None,
            pending_proposal_id=pending[r.code].id if r.code in pending else None,
        )
        for r in _requirements(session, framework_key)
    ]


@router.get("/frameworks/{framework_key}/measures/{code}")
def read_measure(
    framework_key: str, code: str, caller: ComplianceReader, session: DbSession
) -> MeasureDetail:
    org = caller.organization_id
    framework = framework_for_key(session, org, framework_key)
    requirement = next((r for r in _requirements(session, framework_key) if r.code == code), None)
    if requirement is None:
        raise HTTPException(404, detail={"code": "compliance.requirement_not_found"})
    context = public_context(RequirementContext, requirement.attributes)
    controls = session.scalars(
        select(Mapping.control_key)
        .where(
            Mapping.framework_key == framework_key,
            Mapping.requirement_code == code,
            Mapping.retired_at.is_(None),
        )
        .order_by(Mapping.control_key)
    )
    return MeasureDetail(
        framework_key=framework_key,
        code=code,
        title_es=requirement.title_es,
        title_en=requirement.title_en,
        official_text_es=context.official_text_es if context else None,
        official_text_en=context.official_text_en if context else None,
        applicability_es=context.applicability_es if context else None,
        citation=Citation(
            source=requirement.source,
            section=context.section if context else None,
            source_sha256=context.source_sha256 if context else None,
            catalog_version=framework.catalog_version,
            framework_version=framework.version,
        ),
        expected_evidence=context.expected_evidence.items
        if context and context.expected_evidence
        else [],
        controls=list(controls),
        assessment=_assessments(session, org, framework_key).get(code),
    )


@router.get("/gaps")
def list_gaps(caller: ComplianceReader, session: DbSession) -> list[Gap]:
    """Measures not assessed, not implemented or partially implemented, per granted framework."""
    org = caller.organization_id
    gaps: list[Gap] = []
    for framework in _granted(session, org):
        assessed = _assessments(session, org, framework.key)
        assigned = _assignments(session, org, framework.key)
        for r in _requirements(session, framework.key):
            latest = assessed.get(r.code)
            if latest is None:
                state: GapState = "not_assessed"
            elif latest.applicability == "not_applicable" or latest.implementation == "implemented":
                continue
            elif latest.implementation == "not_implemented":
                state = "not_implemented"
            else:
                state = "partially_implemented"
            gaps.append(
                Gap(
                    framework_key=framework.key,
                    framework_name=framework.name,
                    code=r.code,
                    title_es=r.title_es,
                    title_en=r.title_en,
                    state=state,
                    due_on=assigned[r.code].due_on if r.code in assigned else None,
                )
            )
    return gaps


@router.get("/due")
def list_due(caller: ComplianceReader, session: DbSession) -> list[DueItem]:
    return due_items(session, caller.organization_id)


@router.get("/incidents")
def list_incidents(caller: IncidentReader, session: DbSession) -> list[IncidentOut]:
    return open_incidents(session, caller.organization_id)


@router.get("/incidents/{incident_id}")
def read_incident(
    incident_id: uuid.UUID, caller: IncidentReader, session: DbSession
) -> IncidentOut:
    org = caller.organization_id
    incident = _incident(session, org, incident_id)
    return _out(incident, _updates(session, org, [incident_id]), clock_defs(session))


def _via(caller: ApiCaller) -> dict[str, str]:
    """Audit metadata naming the key; the event's actor is the admin who owns it."""
    return {"via": "api_token", "token_id": str(caller.token_id), "token": caller.prefix}


@router.post("/incidents", status_code=201)
def create_incident(body: IncidentIn, caller: RoutineWriter, session: DbSession) -> IncidentOut:
    org, author = caller.organization_id, caller.created_by
    return record_incident(session, org, author, body, _via(caller))


@router.post("/incidents/{incident_id}/updates", status_code=201)
def update_incident(
    incident_id: uuid.UUID, body: UpdateIn, caller: RoutineWriter, session: DbSession
) -> IncidentOut:
    org, author = caller.organization_id, caller.created_by
    return add_incident_update(session, org, author, incident_id, body, _via(caller))


@router.post("/training-campaigns", status_code=201)
def create_campaign(
    body: CampaignIn, request: Request, caller: RoutineWriter, session: DbSession
) -> CreatedCampaign:
    base = request.app.state.web_base_url
    return start_campaign(
        session, caller.organization_id, caller.created_by, body, base, _via(caller)
    )


@router.post("/access-reviews", status_code=201)
def create_access_review(
    body: AccessReviewIn, caller: RoutineWriter, session: DbSession
) -> AccessReviewOut:
    org, author = caller.organization_id, caller.created_by
    return start_access_review(session, org, author, body, _via(caller))


annotate_scopes(router)
