"""Stored organization-wide results; no rescoring or cross-module table access."""

import os
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.models import Requirement, ScoreSnapshot
from atesta_api.modules.compliance.scoring import active_frameworks
from atesta_api.modules.evidence.api import evidence_count
from atesta_api.modules.identity.api import Member, require_member
from atesta_api.modules.scanning.api import ScanSummary, recent_scans
from atesta_api.platform.db import DbSession
from atesta_api.platform.devenv import DEV_ENVS

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["compliance"])


class SnapshotSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scan_id: uuid.UUID
    framework_version: str
    catalog_version: str
    score: float | None
    passed: int
    failed: int
    manual: int
    not_applicable: int
    computed_at: datetime


class FrameworkSummary(BaseModel):
    key: str
    name: str
    version: str
    status: str
    requirements: int  # active requirements in the catalog, so empty templates sort last
    snapshot: SnapshotSummary | None


class OverviewOut(BaseModel):
    frameworks: list[FrameworkSummary]
    scans: list[ScanSummary]
    evidence_count: int
    development: bool


def latest_snapshots(
    session: Session, organization_id: uuid.UUID, keys: list[str]
) -> dict[str, SnapshotSummary]:
    if not keys:
        return {}
    ranked = (
        select(
            ScoreSnapshot.id,
            func.row_number()
            .over(
                partition_by=ScoreSnapshot.framework_key,
                order_by=(ScoreSnapshot.computed_at.desc(), ScoreSnapshot.id.desc()),
            )
            .label("position"),
        )
        .where(
            ScoreSnapshot.organization_id == organization_id,
            ScoreSnapshot.framework_key.in_(keys),
            ScoreSnapshot.scope_id.is_(None),
        )
        .subquery()
    )
    rows = session.scalars(
        select(ScoreSnapshot)
        .join(ranked, ranked.c.id == ScoreSnapshot.id)
        .where(ranked.c.position == 1, ScoreSnapshot.organization_id == organization_id)
    )
    return {row.framework_key: SnapshotSummary.model_validate(row) for row in rows}


@router.get("/overview")
def overview(member: Annotated[Member, Depends(require_member)], session: DbSession) -> OverviewOut:
    frameworks = active_frameworks(session)
    snapshots = latest_snapshots(session, member.organization_id, [f.key for f in frameworks])
    counts: dict[str, int] = {
        key: count
        for key, count in session.execute(
            select(Requirement.framework_key, func.count())
            .where(Requirement.retired_at.is_(None))
            .group_by(Requirement.framework_key)
        ).all()
    }
    return OverviewOut(
        frameworks=[
            FrameworkSummary(
                key=f.key,
                name=f.name,
                version=f.version,
                status=f.status,
                requirements=counts.get(f.key, 0),
                snapshot=snapshots.get(f.key),
            )
            for f in frameworks
        ],
        scans=recent_scans(session, member.organization_id),
        evidence_count=evidence_count(session, member.organization_id),
        development=os.environ.get("ATESTA_ENV") in DEV_ENVS,
    )
