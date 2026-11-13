"""Bounded, non-sensitive scan summaries for organization read surfaces."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
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


def recent_scans(session: Session, organization_id: uuid.UUID) -> list[ScanSummary]:
    rows = session.scalars(
        select(Scan)
        .where(Scan.organization_id == organization_id)
        .order_by(Scan.queued_at.desc(), Scan.id.desc())
        .limit(5)
    )
    return [ScanSummary.model_validate(row) for row in rows]
