"""What an API key may read (api-keys-v2 spec, #341): the compliance state and incidents.

Every route runs in the key's own organization, which identity resolved from the key (ADR-012
amendment 6); no route takes an organization. The answers reuse the functions behind the app's
routes, so a key reads what a member reads. The plan decides frameworks as it does in the app.
Free text in answers is customer content: the MCP server frames it as data (rule 5).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.billing.api import entitlements, has_framework, require_framework
from atesta_api.modules.compliance.catalog_schema import ExpectedEvidenceItem, RequirementContext
from atesta_api.modules.compliance.detail_context import public_context
from atesta_api.modules.compliance.incidents import (
    IncidentOut,
    _incident,
    _out,
    _updates,
    clock_defs,
    open_incidents,
)
from atesta_api.modules.compliance.models import Framework, Mapping
from atesta_api.modules.compliance.readiness import FrameworkReadiness, framework_readiness
from atesta_api.modules.compliance.register import (
    AssessmentOut,
    ProposalOut,
    _assessments,
    _assignments,
    _framework,
    _profile_levels,
    _proposal,
    _requirements,
    _scope,
)
from atesta_api.modules.compliance.routines import DueItem, due_items
from atesta_api.modules.compliance.scoring import FrameworkInfo, active_frameworks
from atesta_api.modules.identity.api import ApiCaller, QueryFreeRoute, require_scope
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/api/v1", tags=["api-keys"], route_class=QueryFreeRoute)
ComplianceReader = Annotated[ApiCaller, Depends(require_scope("compliance:read"))]
IncidentReader = Annotated[ApiCaller, Depends(require_scope("incidents:read"))]

type GapState = Literal["not_assessed", "not_implemented", "partially_implemented"]


class MeasureOut(BaseModel):
    code: str
    title_es: str
    title_en: str | None
    proposal: ProposalOut
    assessment: AssessmentOut | None
    due_on: date | None


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


def _in_plan(session: Session, org: uuid.UUID, framework_key: str) -> Framework:
    """404 for an unknown framework, then 403 billing.plan_limit, as framework_in_plan does."""
    framework = _framework(session, framework_key)
    require_framework(session, org, framework_key)
    return framework


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
    framework = _in_plan(session, org, framework_key)
    scope = _scope(session, org, framework_key)
    profile = _profile_levels(framework, scope)
    assessed = _assessments(session, org, framework_key)
    assigned = _assignments(session, org, framework_key)
    return [
        MeasureOut(
            code=r.code,
            title_es=r.title_es,
            title_en=r.title_en,
            proposal=_proposal(r, scope, profile),
            assessment=assessed.get(r.code),
            due_on=assigned[r.code].due_on if r.code in assigned else None,
        )
        for r in _requirements(session, framework_key)
    ]


@router.get("/frameworks/{framework_key}/measures/{code}")
def read_measure(
    framework_key: str, code: str, caller: ComplianceReader, session: DbSession
) -> MeasureDetail:
    org = caller.organization_id
    framework = _in_plan(session, org, framework_key)
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
