"""The auditor dossier (auditor-dossier spec): one framework's pieces, gathered for the auditor,
with a summary for management. Counts and dates only, never a score (ADR-005, claims-honesty).
"""

from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from atesta_api.modules.billing.api import Feature, require_feature
from atesta_api.modules.compliance.catalog_schema import ExpectedEvidence
from atesta_api.modules.compliance.detail import framework_detail
from atesta_api.modules.compliance.detail_schema import Observation
from atesta_api.modules.compliance.incidents import IncidentSummary, list_incidents
from atesta_api.modules.compliance.plan_gate import framework_in_plan
from atesta_api.modules.compliance.readiness import FrameworkReadiness, framework_readiness
from atesta_api.modules.compliance.register import (
    NOT_A_CERTIFICATION,
    ApplicabilityRow,
    AssessmentReviewOut,
    _review,
    applicability_statement,
)
from atesta_api.modules.compliance.reviews import ReviewOut
from atesta_api.modules.compliance.routines import (
    AccessReviewSummary,
    PolicyOut,
    list_access_reviews,
    list_policies,
    routines_due,
)
from atesta_api.modules.compliance.training import CampaignOut, list_campaigns
from atesta_api.modules.evidence.api import statements_by_control
from atesta_api.modules.identity.api import Member, require_member
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession

router = APIRouter(
    prefix="/api/v1/orgs/{org_id}/frameworks/{framework_key}",
    tags=["compliance"],
    dependencies=[Depends(framework_in_plan)],
)

RECENT = timedelta(days=365)


class RoutineState(BaseModel):
    policies_due: int
    policies_unapproved: int
    access_reviews_overdue: int
    trainings_unclosed: int
    incident_clocks_overdue: int


class DossierSummary(BaseModel):
    counts: FrameworkReadiness | None  # None when the framework has no requirements
    review: AssessmentReviewOut | None
    routines: RoutineState


class EvidenceItem(BaseModel):
    title: str
    statement: str
    reference_url: str | None
    collected_at: datetime
    source_type: str


class DossierControl(BaseModel):
    key: str
    title_es: str
    title_en: str
    manual: bool
    observed_status: Observation | None
    review: ReviewOut | None
    evidence: list[EvidenceItem]


class DossierRequirement(BaseModel):
    code: str
    title_es: str | None
    title_en: str | None
    source: str | None
    decision: str
    implementation: str | None
    justification: str
    controls: list[DossierControl]
    expected_evidence: ExpectedEvidence | None  # the pack's candidate checklist, cited


class DossierRoutines(BaseModel):
    policies: list[PolicyOut]
    access_reviews: list[AccessReviewSummary]
    trainings: list[CampaignOut]
    incidents: list[IncidentSummary]


class Dossier(BaseModel):
    framework_key: str
    framework_name: str
    framework_version: str
    catalog_version: str | None
    generated_at: datetime
    statement: str = NOT_A_CERTIFICATION
    signer: dict[str, str | None]
    summary: DossierSummary
    applicability: list[ApplicabilityRow]
    requirements: list[DossierRequirement]
    routines: DossierRoutines


@router.get("/dossier")
def dossier(
    framework_key: str, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> Dossier:
    org = member.organization_id
    require_feature(session, org, Feature.EVIDENCE_EXPORT)
    detail = framework_detail(framework_key, member, session)  # 404 for an unknown framework
    statement = applicability_statement(session, org, framework_key)
    today = datetime.now().astimezone().date()
    counts = framework_readiness(session, org, detail.key, detail.name, today)
    due_items = routines_due(member, session)
    due = Counter(item.kind for item in due_items)
    clocks_overdue = sum(1 for i in due_items if i.kind == "incident_clock" and i.overdue)
    keys = {c.key for r in detail.requirements for c in r.controls}
    evidence = statements_by_control(session, org, keys)
    rows = {row.code: row for row in statement.rows}
    requirements = [
        DossierRequirement(
            code=r.code,
            title_es=r.title_es,
            title_en=r.title_en,
            source=r.source,
            decision=rows[r.code].decision if r.code in rows else "undecided",
            implementation=rows[r.code].implementation if r.code in rows else None,
            justification=rows[r.code].justification if r.code in rows else "",
            controls=[
                DossierControl(
                    key=c.key,
                    title_es=c.title_es,
                    title_en=c.title_en,
                    manual=c.manual,
                    observed_status=c.observed_status,
                    review=c.review,
                    evidence=[EvidenceItem(**asdict(e)) for e in evidence.get(c.key, [])],
                )
                for c in r.controls
            ],
            expected_evidence=r.guidance.expected_evidence if r.guidance else None,
        )
        for r in detail.requirements
        if r.in_current_catalog
    ]
    since = datetime.now(UTC) - RECENT
    record(
        session,
        organization_id=org,
        action="framework.dossier_viewed",
        target_type="framework",
        target_id=framework_key,
        actor_user_id=member.user_id,
    )
    return Dossier(
        framework_key=detail.key,
        framework_name=detail.name,
        framework_version=detail.version,
        catalog_version=detail.catalog_version,
        generated_at=datetime.now().astimezone(),
        signer=statement.signer,
        summary=DossierSummary(
            counts=counts,
            review=_review(session, org, framework_key),
            routines=RoutineState(
                policies_due=due["policy_review"],
                policies_unapproved=due["policy_unapproved"],
                access_reviews_overdue=due["access_review_overdue"],
                trainings_unclosed=due["training_unclosed"],
                incident_clocks_overdue=clocks_overdue,
            ),
        ),
        applicability=statement.rows,
        requirements=requirements,
        routines=DossierRoutines(
            policies=list_policies(member, session),
            access_reviews=[
                r
                for r in list_access_reviews(member, session)
                if r.closed_at and r.closed_at >= since
            ],
            trainings=[
                c for c in list_campaigns(member, session) if c.closed_at and c.closed_at >= since
            ],
            incidents=[
                i for i in list_incidents(member, session) if i.closed_at and i.closed_at >= since
            ],
        ),
    )
