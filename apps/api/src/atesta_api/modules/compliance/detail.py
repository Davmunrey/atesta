"""Recorded requirement results with current catalog guidance, without rescoring history."""

import os
import uuid
from collections import defaultdict
from typing import Annotated, cast

from atesta_core.controls import control_status
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.catalog_schema import Coverage, PackContext, RequirementContext
from atesta_api.modules.compliance.detail_context import preparation_controls, public_context
from atesta_api.modules.compliance.detail_schema import (
    CheckDetail,
    ControlDetail,
    FrameworkDetail,
    Observation,
    RecordedStatus,
    RequirementDetail,
)
from atesta_api.modules.compliance.models import (
    Control,
    Framework,
    Mapping,
    Requirement,
    ScoreSnapshot,
)
from atesta_api.modules.compliance.overview import latest_snapshots
from atesta_api.modules.compliance.plan_gate import framework_in_plan
from atesta_api.modules.compliance.reviews import current_reviews
from atesta_api.modules.compliance.scoring import active_control_checks, active_frameworks
from atesta_api.modules.identity.api import Member, require_member
from atesta_api.modules.scanning.api import ScanNotFoundError, latest_check_results
from atesta_api.platform.db import DbSession
from atesta_api.platform.devenv import DEV_ENVS

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["compliance"])
_RECORDED = {"pass", "fail", "manual", "not_applicable"}


def _observation(values: list[str]) -> Observation | None:
    if not values:
        return None
    value = control_status(values)
    return cast(Observation, value.value if value else "not_evaluated")


def _controls(
    session: Session,
    organization_id: uuid.UUID,
    key: str,
    snapshot: ScoreSnapshot | None,
    matches: bool,
) -> dict[str, list[ControlDetail]]:
    observations: dict[tuple[str, str], list[str]] = defaultdict(list)
    if snapshot is not None and matches:
        try:
            for engine, check, status in latest_check_results(session, snapshot.scan_id):
                observations[engine, check].append(status)
        except ScanNotFoundError:
            pass  # Old snapshots may outlive their scan; absence is never a passing result.
    rows = session.execute(
        select(Mapping, Control)
        .join(Control, Control.key == Mapping.control_key)
        .where(
            Mapping.framework_key == key,
            Mapping.retired_at.is_(None),
            Control.retired_at.is_(None),
        )
        .order_by(Mapping.requirement_code, Control.key)
    ).all()
    checks: dict[str, list[CheckDetail]] = defaultdict(list)
    configured = active_control_checks(session)
    for control_key in {control.key for _, control in rows}:
        checks[control_key] = [
            CheckDetail(
                engine=engine,
                check_id=check,
                observed_status=_observation(observations[engine, check]),
            )
            for engine, check in configured.get(control_key, [])
        ]
    reviews = current_reviews(
        session, organization_id, {control.key for _, control in rows if control.manual}
    )
    out: dict[str, list[ControlDetail]] = defaultdict(list)
    for mapping, control in rows:
        control_checks = checks[control.key]
        statuses = [
            status
            for check in control_checks
            for status in observations[check.engine, check.check_id]
        ]
        out[mapping.requirement_code].append(
            ControlDetail(
                key=control.key,
                title_es=control.title_es,
                title_en=control.title_en,
                description_es=control.description_es,
                description_en=control.description_en,
                manual=control.manual,
                remediation_refs=control.remediation_refs,
                mapping_reviewed=mapping.reviewed_by is not None,
                mapping_source=mapping.source,
                observed_status=_observation(statuses),
                checks=control_checks,
                review=reviews.get(control.key),
            )
        )
    return out


@router.get("/frameworks/{framework_key}", dependencies=[Depends(framework_in_plan)])
def framework_detail(
    framework_key: str, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> FrameworkDetail:
    if framework_key not in {f.key for f in active_frameworks(session)}:
        raise HTTPException(404, detail={"code": "compliance.not_found"})
    framework = session.get(Framework, framework_key)
    if framework is None:
        raise HTTPException(404, detail={"code": "compliance.not_found"})
    summary = latest_snapshots(session, member.organization_id, [framework_key]).get(framework_key)
    snapshot = (
        session.scalar(
            select(ScoreSnapshot).where(
                ScoreSnapshot.id == summary.id,
                ScoreSnapshot.organization_id == member.organization_id,
            )
        )
        if summary
        else None
    )
    matches = bool(
        snapshot
        and framework.catalog_version is not None
        and snapshot.framework_version == framework.version
        and snapshot.catalog_version == framework.catalog_version
    )
    requirements = {
        r.code: r
        for r in session.scalars(
            select(Requirement).where(
                Requirement.framework_key == framework_key, Requirement.retired_at.is_(None)
            )
        )
    }
    recorded = snapshot.requirement_results if snapshot else {}
    controls = _controls(session, member.organization_id, framework_key, snapshot, matches)
    details = []
    for code in sorted(requirements.keys() | recorded.keys()):
        requirement = requirements.get(code)
        status = recorded.get(code)
        details.append(
            RequirementDetail(
                code=code,
                title_es=requirement.title_es if requirement else None,
                title_en=requirement.title_en if requirement else None,
                source=requirement.source if requirement else None,
                applies_to=requirement.applies_to if requirement else [],
                in_current_catalog=requirement is not None,
                status=cast(RecordedStatus, status) if status in _RECORDED else "not_evaluated",
                controls=controls[code] if requirement else [],
                guidance=public_context(RequirementContext, requirement.attributes)
                if requirement
                else None,
            )
        )
    context = public_context(PackContext, framework.attributes)
    return FrameworkDetail(
        key=framework.key,
        name=framework.name,
        version=framework.version,
        status=framework.status,
        source=framework.source,
        catalog_version=framework.catalog_version,
        catalog_matches_snapshot=matches,
        snapshot=summary,
        requirements=details,
        development=os.environ.get("ATESTA_ENV") in DEV_ENVS,
        catalog_context=context,
        coverage=_coverage(framework.attributes.get("coverage")),
        preparation_controls=preparation_controls(session, context),
    )


def _coverage(raw: object) -> Coverage | None:
    """The pack's source ledger; a malformed or legacy value is never exposed."""
    if not isinstance(raw, dict):
        return None
    try:
        return Coverage.model_validate(raw)
    except ValidationError:
        return None
