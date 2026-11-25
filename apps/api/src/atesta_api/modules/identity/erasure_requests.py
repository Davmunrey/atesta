"""Erasure requests for the operator service (operator-portal spec, "Erasure"; owner answer 3).

On an `atesta_operator` session. The database holds the time rules (approval within 7 days, a
requester's own approval only after 72 hours, one open request per organization); these
functions hold the two rules that need `operator_staff` or a sequence of writes: a requester
approves their own request only as the sole enabled admin, and a new request cancels an expired,
unapproved one in the same transaction. Executing a request is the erasure runner's, never these.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import (
    ColumnElement,
    Interval,
    Row,
    column,
    func,
    insert,
    literal_column,
    select,
    table,
    update,
)
from sqlalchemy.orm import Session

from atesta_api.modules.identity.closure import GRACE
from atesta_api.modules.identity.for_operator import OperatorError
from atesta_api.modules.identity.models import ErasureRequest, OperatorStaff
from atesta_api.platform.tenancy import Organization

# Compared with the database clock, as the erasure_requests CHECKs are.
APPROVAL_WINDOW = literal_column("interval '7 days'", Interval)
COOLING_OFF = literal_column("interval '72 hours'", Interval)
# The columns the role may write, so the requested_at default stays the database's.
_REQUEST_WRITE = table(
    "erasure_requests",
    *map(column, ("id", "organization_id", "requested_by", "approved_by", "approved_at")),
    *map(column, ("cancelled_by", "cancelled_at")),
)


@dataclass(frozen=True, slots=True)
class ApprovedErasure:
    organization_id: uuid.UUID
    not_before: datetime


def _expired() -> ColumnElement[bool]:
    return ErasureRequest.requested_at + APPROVAL_WINDOW < func.now()


def request_erasure(session: Session, org_id: uuid.UUID, staff_id: uuid.UUID) -> uuid.UUID:
    """A request needs a closure. An open request blocks a new one unless it expired unapproved,
    in which case the same admin's new request cancels it in this transaction."""
    closure = session.execute(
        select(Organization.closure_requested_at).where(Organization.id == org_id)
    ).one_or_none()
    if closure is None:
        raise OperatorError("not_found")
    if closure.closure_requested_at is None:
        raise OperatorError("no_closure")
    open_request = session.execute(
        select(ErasureRequest.id, ErasureRequest.approved_at, _expired().label("expired"))
        .where(
            ErasureRequest.organization_id == org_id,
            ErasureRequest.cancelled_at.is_(None),
            ErasureRequest.executed_at.is_(None),
        )
        .with_for_update()
    ).one_or_none()
    if open_request is not None:
        if open_request.approved_at is not None or not open_request.expired:
            raise OperatorError("erasure_pending")
        _cancel(session, open_request.id, staff_id)
    request_id = uuid.uuid4()
    session.execute(
        insert(_REQUEST_WRITE).values(id=request_id, organization_id=org_id, requested_by=staff_id)
    )
    return request_id


def _cancel(session: Session, request_id: uuid.UUID, staff_id: uuid.UUID) -> None:
    session.execute(
        update(_REQUEST_WRITE)
        .where(_REQUEST_WRITE.c.id == request_id)
        .values(cancelled_by=staff_id, cancelled_at=func.now())
    )


type _Request = Row[
    uuid.UUID, uuid.UUID, datetime | None, datetime | None, datetime | None, bool, bool
]


def _locked_request(session: Session, request_id: uuid.UUID) -> _Request:
    row = session.execute(
        select(
            ErasureRequest.organization_id,
            ErasureRequest.requested_by,
            ErasureRequest.approved_at,
            ErasureRequest.cancelled_at,
            ErasureRequest.executed_at,
            _expired().label("expired"),
            (ErasureRequest.requested_at + COOLING_OFF > func.now()).label("cooling"),
        )
        .where(ErasureRequest.id == request_id)
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise OperatorError("not_found")
    if row.executed_at is not None:
        raise OperatorError("erasure_executed")
    if row.cancelled_at is not None:
        raise OperatorError("erasure_cancelled")
    return row


def approve_erasure(
    session: Session, request_id: uuid.UUID, staff_id: uuid.UUID
) -> ApprovedErasure:
    """A second admin approves within 7 days. The requester may approve only as the sole enabled
    admin, and only after the 72-hour cooling-off (the database holds the time rules too)."""
    row = _locked_request(session, request_id)
    if row.approved_at is not None:
        raise OperatorError("erasure_approved")
    if row.expired:
        raise OperatorError("erasure_expired")
    if row.requested_by == staff_id:
        admins = session.scalar(
            select(func.count()).where(
                OperatorStaff.role == "admin", OperatorStaff.disabled_at.is_(None)
            )
        )
        if admins != 1:
            raise OperatorError("same_approver")
        if row.cooling:
            raise OperatorError("cooling_off")
    closure = session.scalar(
        select(Organization.closure_requested_at).where(Organization.id == row.organization_id)
    )
    if closure is None:
        raise OperatorError("no_closure")
    session.execute(
        update(_REQUEST_WRITE)
        .where(_REQUEST_WRITE.c.id == request_id)
        .values(approved_by=staff_id, approved_at=func.now())
    )
    return ApprovedErasure(row.organization_id, closure + GRACE)


def cancel_erasure(session: Session, request_id: uuid.UUID, staff_id: uuid.UUID) -> uuid.UUID:
    """Cancel before the runner executes it; returns the organization, for its Activity."""
    row = _locked_request(session, request_id)
    _cancel(session, request_id, staff_id)
    organization_id: uuid.UUID = row.organization_id
    return organization_id


# --- reads for the admin's erasure screens (spec, "Screens" 8 and 9) --------------------------


@dataclass(frozen=True, slots=True)
class ErasureStatus:
    id: uuid.UUID
    requested_by: uuid.UUID
    requested_at: datetime
    approved_at: datetime | None
    cancelled_at: datetime | None
    executed_at: datetime | None
    receipt_id: uuid.UUID | None


def latest_erasure(session: Session, org_id: uuid.UUID) -> ErasureStatus | None:
    """The organization's most recent erasure request, open or not."""
    row = session.execute(
        select(
            ErasureRequest.id,
            ErasureRequest.requested_by,
            ErasureRequest.requested_at,
            ErasureRequest.approved_at,
            ErasureRequest.cancelled_at,
            ErasureRequest.executed_at,
            ErasureRequest.receipt_id,
        )
        .where(ErasureRequest.organization_id == org_id)
        .order_by(ErasureRequest.requested_at.desc(), ErasureRequest.id)
        .limit(1)
    ).one_or_none()
    return None if row is None else ErasureStatus(*row)
