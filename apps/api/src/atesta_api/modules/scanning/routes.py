"""Scan endpoints (scanner-connectors spec, Endpoints): scan now, scans, findings.

Findings hold tenant data (message and resource_name may name people): returned only to members
of the org, never logged, rendered as text (rules 2 and 5).
"""

import math
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from atesta_api.modules.identity.api import Member, Role, require_member, require_role
from atesta_api.modules.scanning.lifecycle import (
    AlreadyQueuedError,
    ConnectionNotActiveError,
    ConnectionNotFoundError,
    DailyLimitError,
    queue_scan,
)
from atesta_api.modules.scanning.models import Finding, Scan
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["scanning"])

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=1_000_000)]


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


class ScanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connection_id: uuid.UUID
    provider: Literal["m365", "google_workspace"]
    trigger: Literal["schedule", "user", "activation"]
    status: Literal["queued", "running", "collected", "succeeded", "partial", "failed", "blocked"]
    attempts: int
    error_code: str | None
    expected_checks: int
    evaluated_checks: int
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ScanPage(BaseModel):
    items: list[ScanOut]
    total: int
    limit: int
    offset: int


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    check_id: str
    status: Literal["pass", "fail", "manual"]
    muted: bool
    severity: str
    service: str
    resource_type: str
    resource_uid: str
    resource_name: str
    region: str
    message: str
    created_at: datetime


class FindingPage(BaseModel):
    items: list[FindingOut]
    total: int
    limit: int
    offset: int


def _count(session: Session, query: Select[Any]) -> int:
    return int(session.execute(select(func.count()).select_from(query.subquery())).scalar_one())


@router.post("/connections/{connection_id}/scans", status_code=202)
def scan_now(
    connection_id: uuid.UUID,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> ScanOut:
    try:
        scan = queue_scan(
            session,
            member.organization_id,
            connection_id,
            trigger="user",
            requested_by=member.user_id,
        )
    except ConnectionNotFoundError:
        raise _error(404, "connections.not_found") from None
    except ConnectionNotActiveError:
        raise _error(409, "scanning.connection_not_active") from None
    except AlreadyQueuedError:
        raise _error(409, "scanning.already_queued") from None
    except DailyLimitError as limit:
        raise _daily_limit(limit.retry_at) from None
    return ScanOut.model_validate(scan)


def _daily_limit(retry_at: datetime) -> HTTPException:
    """429 with the next Madrid midnight, as ISO 8601 in UTC and as Retry-After seconds (#265)."""
    wait = max(1, math.ceil((retry_at - datetime.now(UTC)).total_seconds()))
    return HTTPException(
        status_code=429,
        detail={
            "code": "scanning.daily_limit",
            "retry_at": retry_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        },
        headers={"Retry-After": str(wait)},
    )


@router.get("/scans")
def list_scans(
    member: Annotated[Member, Depends(require_member)],
    session: DbSession,
    connection_id: uuid.UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> ScanPage:
    query = select(Scan).where(Scan.organization_id == member.organization_id)
    if connection_id is not None:
        query = query.where(Scan.connection_id == connection_id)
    rows = session.scalars(
        query.order_by(Scan.queued_at.desc(), Scan.id.desc()).limit(limit).offset(offset)
    )
    return ScanPage(
        items=[ScanOut.model_validate(r) for r in rows],
        total=_count(session, query),
        limit=limit,
        offset=offset,
    )


def _scan(session: Session, member: Member, scan_id: uuid.UUID) -> Scan:
    scan = session.scalars(
        select(Scan).where(Scan.id == scan_id, Scan.organization_id == member.organization_id)
    ).one_or_none()
    if scan is None:
        raise _error(404, "scanning.not_found")
    return scan


@router.get("/scans/{scan_id}")
def get_scan(
    scan_id: uuid.UUID,
    member: Annotated[Member, Depends(require_member)],
    session: DbSession,
) -> ScanOut:
    return ScanOut.model_validate(_scan(session, member, scan_id))


@router.get("/scans/{scan_id}/findings")
def list_findings(
    scan_id: uuid.UUID,
    member: Annotated[Member, Depends(require_member)],
    session: DbSession,
    status: Literal["pass", "fail", "manual"] | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> FindingPage:
    scan = _scan(session, member, scan_id)
    query = select(Finding).where(
        Finding.organization_id == scan.organization_id, Finding.scan_id == scan.id
    )
    if status is not None:
        query = query.where(Finding.status == status)
    order = (Finding.check_id, Finding.resource_uid, Finding.id)
    rows = session.scalars(query.order_by(*order).limit(limit).offset(offset))
    return FindingPage(
        items=[FindingOut.model_validate(r) for r in rows],
        total=_count(session, query),
        limit=limit,
        offset=offset,
    )
