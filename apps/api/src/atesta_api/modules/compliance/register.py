"""Requirement register and statement of applicability (requirement-register spec).

The organization records its scope, its own assessment of each requirement and its reviewer's
analysis; Atesta proposes applicability from the pack's selection rules and exports the result.
Nothing here changes a score (ADR-005) or names a framework (rule 9). Free text is customer
content: stored and returned to members, never logged or copied into audit metadata (rule 2).
"""

import csv
import io
import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from atesta_core.applicability import (
    PROFILE,
    axis_levels,
    profile_proposal,
    propose,
    valid_scope,
)
from atesta_core.history import Assessment as HistoryRow
from atesta_core.history import progress_history
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.models import (
    AssessmentReview,
    Framework,
    FrameworkScope,
    Requirement,
    RequirementAssessment,
    RequirementAssignment,
    ScoreSnapshot,
)
from atesta_api.modules.compliance.plan_gate import framework_in_plan
from atesta_api.modules.compliance.scoring import active_frameworks
from atesta_api.modules.evidence.api import statements_in_org
from atesta_api.modules.identity.api import Member, Role, is_member, require_member, require_role
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession
from atesta_api.platform.i18n import Locale, message

router = APIRouter(
    prefix="/api/v1/orgs/{org_id}/frameworks/{framework_key}",
    tags=["compliance"],
    dependencies=[Depends(framework_in_plan)],
)

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # tab and line feed allowed
NOT_A_CERTIFICATION = (
    f"{message('en', 'statement.not_a_certification')} / "
    f"{message('es', 'statement.not_a_certification')}"
)

type Applicability = Literal["applies", "not_applicable"]
type Implementation = Literal["not_implemented", "partially_implemented", "implemented"]


def _clean(value: str, maximum: int, minimum: int = 0) -> str:
    text = value.replace("\r\n", "\n").strip()
    if not minimum <= len(text) <= maximum or _CONTROL_CHARACTERS.search(text):
        raise ValueError(f"must be {minimum}-{maximum} characters without control characters")
    return text


class ScopeIn(BaseModel):
    axis_values: dict[str, str | dict[str, str]]


class ScopeOut(BaseModel):
    axis_values: dict[str, Any]
    decided_by: uuid.UUID
    decided_at: datetime


class AssessmentIn(BaseModel):
    applicability: Applicability
    implementation: Implementation
    regularly_reviewed: bool
    justification: str = ""
    performed_by: str = ""
    performed_on: date | None = None
    evidence_statement_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    notes: str = ""

    @field_validator("justification", "notes")
    @classmethod
    def long_text(cls, value: str) -> str:
        return _clean(value, 2000)

    @field_validator("performed_by")
    @classmethod
    def short_text(cls, value: str) -> str:
        return _clean(value, 200)


class AssessmentOut(BaseModel):
    applicability: Applicability
    implementation: Implementation
    regularly_reviewed: bool
    justification: str
    performed_by: str
    performed_on: date | None
    evidence_statement_ids: list[uuid.UUID]
    notes: str
    recorded_by: uuid.UUID
    recorded_at: datetime


class GuideRef(BaseModel):
    guide: str
    edition: str
    section: str
    page: int


class ProposalOut(BaseModel):
    decision: Literal["applies", "not_applicable", "undecided"]
    rule: str | None
    level: str | None  # the scope level, or the profile key when a profile proposed it
    source: GuideRef | None = None  # a profile's applicability table (issue 227)
    criterion: GuideRef | None = None  # where the profile's guide gives specific criteria


class ProfileOut(BaseModel):
    """A pack's scope profile as the scope step offers it (requirement-register spec)."""

    key: str
    title_es: str
    title_en: str
    summary_es: str
    summary_en: str
    refs: list[GuideRef]
    reviewed_by: str | None
    reviewed_on: date | None


class AssignmentIn(BaseModel):
    owner_user_id: uuid.UUID | None  # None clears the owner
    due_on: date | None = None


class AssignmentOut(BaseModel):
    owner_user_id: uuid.UUID | None
    due_on: date | None
    assigned_at: datetime


class RegisterItem(BaseModel):
    code: str
    title_es: str
    title_en: str | None
    selection_basis: str | None
    proposal: ProposalOut
    assessment: AssessmentOut | None
    assignment: AssignmentOut | None


class HistoryPoint(BaseModel):
    day: date
    assessed: int
    implemented: int
    not_applicable: int


class TrendPoint(BaseModel):
    computed_at: datetime
    score: float | None
    framework_version: str


class AssessmentReviewIn(BaseModel):
    reviewer_name: str
    reviewer_role: str
    reviewed_on: date
    conclusions: str
    corrective_actions: str = ""

    @field_validator("reviewer_name", "reviewer_role")
    @classmethod
    def names(cls, value: str) -> str:
        return _clean(value, 200, 1)

    @field_validator("conclusions")
    @classmethod
    def conclusions_text(cls, value: str) -> str:
        return _clean(value, 4000, 1)

    @field_validator("corrective_actions")
    @classmethod
    def actions_text(cls, value: str) -> str:
        return _clean(value, 4000)


class AssessmentReviewOut(AssessmentReviewIn):
    recorded_by: uuid.UUID
    recorded_at: datetime


class GroupTitle(BaseModel):
    prefix: str
    title: str
    title_en: str | None = None  # the official English heading, when the act has one


class TermLabelOut(BaseModel):
    term: str
    es: str
    en: str


class GuideStepOut(BaseModel):
    asset: Literal["information", "service"]
    key: str
    es: str
    en: str
    ref: GuideRef


class GuideNoteOut(BaseModel):
    es: str
    en: str
    ref: GuideRef


class ScopeGuideOut(BaseModel):
    """How to value the system, from the pack (requirement-register spec, issue 225)."""

    axis: str
    category_axis: str
    category_by_level: dict[str, str]
    steps: list[GuideStepOut]
    notes: list[GuideNoteOut]
    reviewed_by: str | None
    reviewed_on: date | None


class Register(BaseModel):
    framework_key: str
    framework_version: str
    catalog_version: str | None
    axes: dict[str, dict[str, list[str]]]
    profiles: list[ProfileOut]  # published profiles the scope may name (issue 227)
    scope_guide: ScopeGuideOut | None  # the pack's valuation steps (issue 225)
    groups_es: list[GroupTitle]  # official group headings in the source's order; empty if none
    term_labels: list[TermLabelOut]  # readable ES/EN labels for the official scope terms
    scope: ScopeOut | None
    items: list[RegisterItem]
    review: AssessmentReviewOut | None


class ApplicabilityRow(BaseModel):
    code: str
    title_es: str
    decision: Literal["applies", "not_applicable", "undecided"]
    decided_by_person: bool
    rule: str | None
    level: str | None
    justification: str
    implementation: Implementation | None


def _empty_signer() -> dict[str, str | None]:
    return {"name": None, "role": None, "date": None, "signature": None}


class ApplicabilityStatement(BaseModel):
    framework_key: str
    framework_name: str
    framework_version: str
    catalog_version: str | None
    scope: dict[str, Any] | None
    generated_at: datetime
    statement: str = NOT_A_CERTIFICATION
    signer: dict[str, str | None] = Field(default_factory=_empty_signer)
    rows: list[ApplicabilityRow]


def _not_found() -> HTTPException:
    return HTTPException(404, detail={"code": "compliance.not_found"})


def _framework(session: Session, framework_key: str) -> Framework:
    if framework_key not in {f.key for f in active_frameworks(session)}:
        raise _not_found()
    framework = session.get(Framework, framework_key)
    if framework is None:
        raise _not_found()
    return framework


def _requirements(session: Session, framework_key: str) -> list[Requirement]:
    return list(
        session.scalars(
            select(Requirement)
            .where(Requirement.framework_key == framework_key, Requirement.retired_at.is_(None))
            .order_by(Requirement.code)
        )
    )


def _axes(requirements: list[Requirement]) -> dict[str, dict[str, list[str]]]:
    return axis_levels(r.attributes for r in requirements)


def _scope(session: Session, organization_id: uuid.UUID, framework_key: str) -> ScopeOut | None:
    row = session.scalar(
        select(FrameworkScope)
        .where(
            FrameworkScope.organization_id == organization_id,
            FrameworkScope.framework_key == framework_key,
        )
        .order_by(FrameworkScope.decided_at.desc(), FrameworkScope.id.desc())
        .limit(1)
    )
    if row is None:
        return None
    return ScopeOut(
        axis_values=row.axis_values, decided_by=row.decided_by, decided_at=row.decided_at
    )


def _assessments(
    session: Session, organization_id: uuid.UUID, framework_key: str
) -> dict[str, AssessmentOut]:
    rows = session.scalars(
        select(RequirementAssessment)
        .where(
            RequirementAssessment.organization_id == organization_id,
            RequirementAssessment.framework_key == framework_key,
        )
        .ext(distinct_on(RequirementAssessment.requirement_code))
        .order_by(
            RequirementAssessment.requirement_code,
            RequirementAssessment.recorded_at.desc(),
            RequirementAssessment.id.desc(),
        )
    )
    return {
        row.requirement_code: AssessmentOut.model_validate(row, from_attributes=True)
        for row in rows
    }


def _review(
    session: Session, organization_id: uuid.UUID, framework_key: str
) -> AssessmentReviewOut | None:
    row = session.scalar(
        select(AssessmentReview)
        .where(
            AssessmentReview.organization_id == organization_id,
            AssessmentReview.framework_key == framework_key,
        )
        .order_by(AssessmentReview.recorded_at.desc(), AssessmentReview.id.desc())
        .limit(1)
    )
    return AssessmentReviewOut.model_validate(row, from_attributes=True) if row else None


def _term_labels(framework: Framework) -> list[TermLabelOut]:
    labels = framework.attributes.get("term_labels", [])
    if not isinstance(labels, list):
        return []
    return [TermLabelOut.model_validate(label) for label in labels if isinstance(label, dict)]


def _groups(framework: Framework) -> list[GroupTitle]:
    groups = framework.attributes.get("groups_es", [])
    if not isinstance(groups, list):
        return []
    return [
        GroupTitle(
            prefix=str(g["prefix"]),
            title=str(g["title"]),
            title_en=str(g["title_en"]) if g.get("title_en") else None,
        )
        for g in groups
        if isinstance(g, dict)
    ]


def _assignments(
    session: Session, organization_id: uuid.UUID, framework_key: str
) -> dict[str, AssignmentOut]:
    rows = session.scalars(
        select(RequirementAssignment)
        .where(
            RequirementAssignment.organization_id == organization_id,
            RequirementAssignment.framework_key == framework_key,
        )
        .ext(distinct_on(RequirementAssignment.requirement_code))
        .order_by(
            RequirementAssignment.requirement_code,
            RequirementAssignment.assigned_at.desc(),
            RequirementAssignment.id.desc(),
        )
    )
    return {
        row.requirement_code: AssignmentOut.model_validate(row, from_attributes=True)
        for row in rows
        if row.owner_user_id is not None or row.due_on is not None
    }


def _profiles(framework: Framework) -> list[ProfileOut]:
    return [ProfileOut(**p) for p in framework.attributes.get("scope_profiles", [])]


def _scope_guide(framework: Framework) -> ScopeGuideOut | None:
    guide = framework.attributes.get("scope_guide")
    return ScopeGuideOut(**guide) if guide else None


def _profile_levels(framework: Framework, scope: ScopeOut | None) -> dict[str, Any] | None:
    """The profile the scope names, as the pack publishes it; None without one."""
    chosen = scope.axis_values.get(PROFILE) if scope else None
    found = (p for p in framework.attributes.get("scope_profiles", []) if p["key"] == chosen)
    return next(found, None)


def _proposal(
    requirement: Requirement, scope: ScopeOut | None, profile: dict[str, Any] | None = None
) -> ProposalOut:
    if profile is not None:
        made = profile_proposal(profile["levels"].get(requirement.code), profile["key"])
        source = GuideRef(**profile["refs"][0])
        cited = profile.get("criteria", {}).get(requirement.code)
        return ProposalOut(
            **vars(made),
            source=source,
            criterion=source.model_copy(update=cited) if cited else None,
        )
    attributes = requirement.attributes
    made = propose(
        attributes.get("selection_basis"),
        attributes.get("selection_rules", []),
        scope.axis_values if scope else {},
    )
    return ProposalOut(**vars(made))


@router.get("/scope")
def read_scope(
    framework_key: str, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> dict[str, Any]:
    framework = _framework(session, framework_key)
    axes = _axes(_requirements(session, framework_key))
    return {
        "axes": axes,
        "profiles": _profiles(framework),
        "scope": _scope(session, member.organization_id, framework_key),
    }


@router.post("/scope", status_code=201)
def record_scope(
    framework_key: str,
    body: ScopeIn,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> ScopeOut:
    framework = _framework(session, framework_key)
    profiles = {p.key for p in _profiles(framework)}
    if not valid_scope(body.axis_values, _axes(_requirements(session, framework_key)), profiles):
        raise HTTPException(422, detail={"code": "compliance.scope_invalid"})
    row = FrameworkScope(
        organization_id=member.organization_id,
        framework_key=framework_key,
        axis_values=body.axis_values,
        decided_by=member.user_id,
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    record(
        session,
        organization_id=member.organization_id,
        action="framework.scope_recorded",
        target_type="framework",
        target_id=framework_key,
        actor_user_id=member.user_id,
        metadata={"axes": len(body.axis_values)},
    )
    return ScopeOut(
        axis_values=row.axis_values, decided_by=row.decided_by, decided_at=row.decided_at
    )


@router.get("/register")
def read_register(
    framework_key: str, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> Register:
    framework = _framework(session, framework_key)
    requirements = _requirements(session, framework_key)
    scope = _scope(session, member.organization_id, framework_key)
    profile = _profile_levels(framework, scope)
    assessments = _assessments(session, member.organization_id, framework_key)
    assignments = _assignments(session, member.organization_id, framework_key)
    items = [
        RegisterItem(
            code=r.code,
            title_es=r.title_es,
            title_en=r.title_en,
            selection_basis=r.attributes.get("selection_basis"),
            proposal=_proposal(r, scope, profile),
            assessment=assessments.get(r.code),
            assignment=assignments.get(r.code),
        )
        for r in requirements
    ]
    return Register(
        framework_key=framework.key,
        framework_version=framework.version,
        catalog_version=framework.catalog_version,
        axes=_axes(requirements),
        profiles=_profiles(framework),
        scope_guide=_scope_guide(framework),
        groups_es=_groups(framework),
        term_labels=_term_labels(framework),
        scope=scope,
        items=items,
        review=_review(session, member.organization_id, framework_key),
    )


@router.post("/register/{requirement_code}", status_code=201)
def record_assessment(
    framework_key: str,
    requirement_code: str,
    body: AssessmentIn,
    member: Annotated[Member, Depends(require_role(Role.MEMBER))],
    session: DbSession,
) -> AssessmentOut:
    """Admins assess any measure; a contributor only the measures they own (rbac spec)."""
    framework = _framework(session, framework_key)
    requirement = next(
        (r for r in _requirements(session, framework_key) if r.code == requirement_code), None
    )
    if requirement is None:
        raise HTTPException(404, detail={"code": "compliance.requirement_not_found"})
    if member.role == Role.MEMBER:
        owned = _assignments(session, member.organization_id, framework_key).get(requirement_code)
        if owned is None or owned.owner_user_id != member.user_id:
            raise HTTPException(403, detail={"code": "compliance.not_owner"})
    scope = _scope(session, member.organization_id, framework_key)
    proposal = _proposal(requirement, scope, _profile_levels(framework, scope))
    differs = proposal.decision != "undecided" and proposal.decision != body.applicability
    if (body.applicability == "not_applicable" or differs) and not body.justification:
        raise HTTPException(422, detail={"code": "compliance.justification_required"})
    wanted = set(body.evidence_statement_ids)
    if wanted - statements_in_org(session, member.organization_id, wanted):
        raise HTTPException(422, detail={"code": "compliance.evidence_not_found"})
    row = RequirementAssessment(
        organization_id=member.organization_id,
        framework_key=framework_key,
        requirement_code=requirement_code,
        applicability=body.applicability,
        implementation=body.implementation,
        regularly_reviewed=body.regularly_reviewed,
        justification=body.justification,
        performed_by=body.performed_by,
        performed_on=body.performed_on,
        evidence_statement_ids=sorted(wanted),
        notes=body.notes,
        recorded_by=member.user_id,
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    record(
        session,
        organization_id=member.organization_id,
        action="requirement.assessed",
        target_type="requirement",
        target_id=f"{framework_key}:{requirement_code}",
        actor_user_id=member.user_id,
        metadata={
            "applicability": body.applicability,
            "implementation": body.implementation,
            "regularly_reviewed": body.regularly_reviewed,
            "differs_from_proposal": differs,
            "evidence_count": len(wanted),
        },
    )
    return AssessmentOut.model_validate(row, from_attributes=True)


@router.post("/register/{requirement_code}/assignment", status_code=201)
def record_assignment(
    framework_key: str,
    requirement_code: str,
    body: AssignmentIn,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> AssignmentOut:
    _framework(session, framework_key)
    if requirement_code not in {r.code for r in _requirements(session, framework_key)}:
        raise HTTPException(404, detail={"code": "compliance.requirement_not_found"})
    if body.owner_user_id is not None and not is_member(
        session, member.organization_id, body.owner_user_id
    ):
        raise HTTPException(422, detail={"code": "compliance.owner_not_member"})
    row = RequirementAssignment(
        organization_id=member.organization_id,
        framework_key=framework_key,
        requirement_code=requirement_code,
        owner_user_id=body.owner_user_id,
        due_on=body.due_on,
        assigned_by=member.user_id,
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    record(
        session,
        organization_id=member.organization_id,
        action="requirement.assigned",
        target_type="requirement",
        target_id=f"{framework_key}:{requirement_code}",
        actor_user_id=member.user_id,
        metadata={"has_owner": body.owner_user_id is not None, "has_due": body.due_on is not None},
    )
    return AssignmentOut.model_validate(row, from_attributes=True)


@router.get("/register/history")
def read_history(
    framework_key: str, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> list[HistoryPoint]:
    _framework(session, framework_key)
    rows = session.execute(
        select(
            RequirementAssessment.recorded_at,
            RequirementAssessment.requirement_code,
            RequirementAssessment.applicability,
            RequirementAssessment.implementation,
        ).where(
            RequirementAssessment.organization_id == member.organization_id,
            RequirementAssessment.framework_key == framework_key,
        )
    ).all()
    today = datetime.now().astimezone().date()
    points = progress_history((HistoryRow(*row) for row in rows), today=today)
    return [HistoryPoint(**vars(p)) for p in points]


@router.get("/trend")
def read_trend(
    framework_key: str, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> list[TrendPoint]:
    _framework(session, framework_key)
    rows = session.scalars(
        select(ScoreSnapshot)
        .where(
            ScoreSnapshot.organization_id == member.organization_id,
            ScoreSnapshot.framework_key == framework_key,
            ScoreSnapshot.scope_id.is_(None),
        )
        .order_by(ScoreSnapshot.computed_at, ScoreSnapshot.id)
    )
    return [
        TrendPoint(
            computed_at=r.computed_at,
            score=float(r.score) if r.score is not None else None,
            framework_version=r.framework_version,
        )
        for r in rows
    ]


@router.post("/assessment-reviews", status_code=201)
def record_review(
    framework_key: str,
    body: AssessmentReviewIn,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> AssessmentReviewOut:
    _framework(session, framework_key)
    row = AssessmentReview(
        organization_id=member.organization_id,
        framework_key=framework_key,
        recorded_by=member.user_id,
        **body.model_dump(),
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    record(
        session,
        organization_id=member.organization_id,
        action="framework.assessment_reviewed",
        target_type="framework",
        target_id=framework_key,
        actor_user_id=member.user_id,
        metadata={"reviewed_on": body.reviewed_on.isoformat()},
    )
    return AssessmentReviewOut.model_validate(row, from_attributes=True)


@router.get("/assessment-reviews")
def list_reviews(
    framework_key: str, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> list[AssessmentReviewOut]:
    _framework(session, framework_key)
    rows = session.scalars(
        select(AssessmentReview)
        .where(
            AssessmentReview.organization_id == member.organization_id,
            AssessmentReview.framework_key == framework_key,
        )
        .order_by(AssessmentReview.recorded_at.desc(), AssessmentReview.id.desc())
    )
    return [AssessmentReviewOut.model_validate(row, from_attributes=True) for row in rows]


def _statement(session: Session, member: Member, framework_key: str) -> ApplicabilityStatement:
    statement = applicability_statement(session, member.organization_id, framework_key)
    record(
        session,
        organization_id=member.organization_id,
        action="framework.applicability_exported",
        target_type="framework",
        target_id=framework_key,
        actor_user_id=member.user_id,
        metadata={
            "rows": len(statement.rows),
            "decided": sum(r.decided_by_person for r in statement.rows),
        },
    )
    return statement


def applicability_statement(
    session: Session, organization_id: uuid.UUID, framework_key: str
) -> ApplicabilityStatement:
    """The statement of applicability, with no side effect (the dossier reuses it)."""
    framework = _framework(session, framework_key)
    requirements = _requirements(session, framework_key)
    scope = _scope(session, organization_id, framework_key)
    profile = _profile_levels(framework, scope)
    assessments = _assessments(session, organization_id, framework_key)
    rows = []
    for requirement in requirements:
        proposal = _proposal(requirement, scope, profile)
        assessment = assessments.get(requirement.code)
        rows.append(
            ApplicabilityRow(
                code=requirement.code,
                title_es=requirement.title_es,
                decision=assessment.applicability if assessment else proposal.decision,
                decided_by_person=assessment is not None,
                rule=proposal.rule,
                level=proposal.level,
                justification=assessment.justification if assessment else "",
                implementation=assessment.implementation if assessment else None,
            )
        )
    return ApplicabilityStatement(
        framework_key=framework.key,
        framework_name=framework.name,
        framework_version=framework.version,
        catalog_version=framework.catalog_version,
        scope=scope.axis_values if scope else None,
        generated_at=datetime.now().astimezone(),
        rows=rows,
    )


@router.get("/applicability")
def applicability(
    framework_key: str, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> ApplicabilityStatement:
    return _statement(session, member, framework_key)


@router.get("/applicability.csv", response_class=Response)
def applicability_csv(
    framework_key: str,
    member: Annotated[Member, Depends(require_member)],
    session: DbSession,
    lang: Locale = "es",
) -> Response:
    """The statement in the reader's language (i18n-complete spec). Official titles stay Spanish."""
    statement = _statement(session, member, framework_key)

    def say(key: str) -> str:
        return message(lang, f"applicability.{key}")

    buffer = io.StringIO()
    buffer.write("\ufeff")  # UTF-8 byte order mark: Excel then reads accents correctly
    writer = csv.writer(buffer)
    writer.writerow(["# " + message(lang, "statement.not_a_certification")])
    writer.writerow(
        ["# " + say("framework"), statement.framework_name, statement.framework_version]
    )
    writer.writerow(["# " + say("catalog_version"), statement.catalog_version or ""])
    writer.writerow(["# " + say("signer"), "", "", ""])
    fields = list(ApplicabilityRow.model_fields)
    writer.writerow(say(f"columns.{field}") for field in fields)
    for row in statement.rows:
        values: dict[str, object] = row.model_dump()
        values["decision"] = say(f"decision.{row.decision}")
        values["decided_by_person"] = say("yes" if row.decided_by_person else "no")
        if row.implementation is not None:
            values["implementation"] = say(f"implementation.{row.implementation}")
        # Spreadsheet formula injection: neutralise cells a customer typed (OWASP CSV injection).
        writer.writerow(_cell(values[field]) for field in fields)
    return Response(
        buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "content-disposition": f'attachment; filename="{framework_key}-applicability.csv"'
        },
    )


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text
