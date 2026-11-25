"""Admin views and staff management (operator-portal spec, "Screens" 9 to 11): erased
organizations' receipts, the team, and the operator trail. Staff changes go to the operator trail
only; the customer never sees them.
"""

import uuid
from datetime import datetime
from typing import Annotated

from atesta_api.modules.identity.api import (
    OperatorError,
    StaffRole,
    change_staff,
    erasure_receipts,
    staff_list,
)
from atesta_api.platform.audit import Scalar, operator_events
from atesta_api.platform.db import DbSession
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from atesta_operator import trail
from atesta_operator.auth import CurrentStaff
from atesta_operator.errors import refusal

router = APIRouter(prefix="/api/v1", tags=["admin"])
PAGE = 50
Page = Annotated[int, Query(ge=1, le=10_000)]


def _out[M: BaseModel](model: type[M], row: object) -> M:
    """A response model from a module's dataclass, field by field."""
    return model(**{name: getattr(row, name) for name in model.model_fields})


class Receipt(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    closure_requested_at: datetime
    erased_at: datetime
    rows: int


class Receipts(BaseModel):
    rows: list[Receipt]
    total: int
    page: int
    page_size: int


@router.get("/erasure-receipts")
def receipts(staff: CurrentStaff, session: DbSession, page: Page = 1) -> Receipts:
    found, total = erasure_receipts(session, page, PAGE)
    rows = [_out(Receipt, r) for r in found]
    return Receipts(rows=rows, total=total, page=page, page_size=PAGE)


class StaffOut(BaseModel):
    id: uuid.UUID
    email: str
    role: StaffRole
    disabled_at: datetime | None


@router.get("/staff")
def team(staff: CurrentStaff, session: DbSession) -> list[StaffOut]:
    return [_out(StaffOut, m) for m in staff_list(session)]


class StaffChangeIn(BaseModel):
    role: StaffRole | None = None
    disabled: bool | None = None
    reason: Annotated[str, Field(min_length=1, max_length=500)]


@router.patch("/staff/{staff_id}")
def change(
    staff_id: uuid.UUID,
    body: StaffChangeIn,
    staff: CurrentStaff,
    session: DbSession,
    request_id: trail.RequestId,
) -> StaffOut:
    try:
        before, after = change_staff(
            session, staff_id, actor_id=staff.id, role=body.role, disabled=body.disabled
        )
    except OperatorError as error:
        raise refusal(error) from None
    changes: list[tuple[str, dict[str, Scalar]]] = []
    if after.role != before.role:
        changes.append(("staff.role_changed", {"role": after.role, "previous_role": before.role}))
    if (after.disabled_at is None) != (before.disabled_at is None):
        changes.append(("staff.disabled" if after.disabled_at else "staff.enabled", {}))
    for action, metadata in changes:
        trail.write(
            session,
            staff,
            request_id,
            action,
            organization_id=None,
            target_id=str(staff_id),
            reason=body.reason,
            customer_sees=False,
            metadata=metadata,
        )
    return _out(StaffOut, after)


class EventOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    staff_id: uuid.UUID | None
    staff_role: str | None
    action: str
    organization_id: uuid.UUID | None
    target_id: str | None
    reason: str | None
    request_id: str | None
    metadata: dict[str, Scalar]


class Events(BaseModel):
    rows: list[EventOut]
    total: int
    page: int
    page_size: int


@router.get("/operator-events")
def events(
    staff: CurrentStaff,
    session: DbSession,
    org_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    page: Page = 1,
) -> Events:
    found, total = operator_events(
        session, organization_id=org_id, staff_id=staff_id, action=action, page=page, size=PAGE
    )
    return Events(
        rows=[
            EventOut(
                id=e.id,
                occurred_at=e.occurred_at,
                staff_id=e.staff_id,
                staff_role=e.staff_role,
                action=e.action,
                organization_id=e.organization_id,
                target_id=e.target_id,
                reason=e.reason,
                request_id=e.request_id,
                metadata=e.details,
            )
            for e in found
        ],
        total=total,
        page=page,
        page_size=PAGE,
    )
