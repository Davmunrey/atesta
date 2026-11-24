"""Bounded, non-sensitive scan summaries for organization read surfaces."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atesta_api.modules.scanning.models import Scan


class ScanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: Literal["m365", "google_workspace"]
    status: Literal["queued", "running", "collected", "succeeded", "partial", "failed", "blocked"]
    expected_checks: int
    evaluated_checks: int
    queued_at: datetime
    finished_at: datetime | None


def scan_counts(session: Session, organization_id: uuid.UUID, *, since: datetime) -> dict[str, int]:
    """Scans queued since a moment, by status (weekly summary, notifications spec PR 3)."""
    rows = session.execute(
        select(Scan.status, func.count())
        .where(Scan.organization_id == organization_id, Scan.queued_at >= since)
        .group_by(Scan.status)
    ).all()
    return {str(status): int(count) for status, count in rows}


def recent_scans(session: Session, organization_id: uuid.UUID) -> list[ScanSummary]:
    rows = session.scalars(
        select(Scan)
        .where(Scan.organization_id == organization_id)
        .order_by(Scan.queued_at.desc(), Scan.id.desc())
        .limit(5)
    )
    return [ScanSummary.model_validate(row) for row in rows]
