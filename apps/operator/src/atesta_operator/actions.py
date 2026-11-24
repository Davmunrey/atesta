"""Admin actions on an organization (operator-portal spec, "Screens" 6 to 8; ADR-017, "What staff
can do"): suspend and reactivate, the operator closure, and erasure requests.

Suspend, closure and erasure take the organization's exact name, typed (422
`operator.name_mismatch`), and a recent sign-in (`policy.POLICY`). The module functions hold the
state rules and refuse with `OperatorError`; every action writes both trails in the request's
transaction. The portal records erasure requests and never deletes: the erasure runner does.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from atesta_api.modules.identity.api import (
    OperatorError,
    OrganizationMetadata,
    approve_erasure,
    cancel_erasure,
    cancel_operator_closure,
    organization_metadata,
    reactivate,
    request_erasure,
    start_operator_closure,
    suspend,
)
from atesta_api.platform.db import DbSession
from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from atesta_operator import trail
from atesta_operator.auth import CurrentStaff
from atesta_operator.errors import operator_error, refusal

router = APIRouter(prefix="/api/v1", tags=["actions"])
Reason = Annotated[str, Field(min_length=1, max_length=500)]
TypedName = Annotated[str, Field(min_length=1, max_length=300)]
type ReasonCode = Literal[
    "non_payment", "contract_ended", "customer_request", "security_review", "other"
]


class ReasonIn(BaseModel):
    reason: Reason


class ConfirmedIn(BaseModel):
    confirm_name: TypedName
    reason: Reason


class SuspendIn(ConfirmedIn):
    reason_code: ReasonCode


class SuspendedOut(BaseModel):
    suspended_at: datetime


class ClosureOut(BaseModel):
    erase_after: datetime


class ErasureRequestOut(BaseModel):
    id: uuid.UUID


class ApprovedOut(BaseModel):
    not_before: datetime


def _confirmed(session: DbSession, org_id: uuid.UUID, typed: str | None) -> OrganizationMetadata:
    """The organization, checked against the typed name when one is required."""
    org = organization_metadata(session, org_id)
    if org is None:
        raise operator_error("operator.not_found")
    if typed is not None and typed != org.name:
        raise operator_error("operator.name_mismatch")
    return org


@router.post("/organizations/{org_id}/suspension")
def post_suspension(
    org_id: uuid.UUID,
    body: SuspendIn,
    staff: CurrentStaff,
    session: DbSession,
    request_id: trail.RequestId,
) -> SuspendedOut:
    _confirmed(session, org_id, body.confirm_name)
    try:
        since = suspend(session, org_id, body.reason_code)
    except OperatorError as error:
        raise refusal(error) from None
    trail.write(
        session,
        staff,
        request_id,
        "operator.suspended",
        organization_id=org_id,
        reason=body.reason,
        metadata={"reason_code": body.reason_code},
    )
    return SuspendedOut(suspended_at=since)


@router.delete("/organizations/{org_id}/suspension", status_code=204)
def delete_suspension(
    org_id: uuid.UUID,
    body: ReasonIn,
    staff: CurrentStaff,
    session: DbSession,
    request_id: trail.RequestId,
) -> Response:
    _confirmed(session, org_id, None)
    try:
        reactivate(session, org_id)
    except OperatorError as error:
        raise refusal(error) from None
    trail.write(
        session,
        staff,
        request_id,
        "operator.reactivated",
        organization_id=org_id,
        reason=body.reason,
    )
    return Response(status_code=204)


@router.post("/organizations/{org_id}/closure")
def post_closure(
    org_id: uuid.UUID,
    body: ConfirmedIn,
    staff: CurrentStaff,
    session: DbSession,
    request_id: trail.RequestId,
) -> ClosureOut:
    _confirmed(session, org_id, body.confirm_name)
    try:
        erase_after = start_operator_closure(session, org_id)
    except OperatorError as error:
        raise refusal(error) from None
    trail.write(
        session,
        staff,
        request_id,
        "operator.closure_started",
        organization_id=org_id,
        reason=body.reason,
        metadata={"erase_after": erase_after.date().isoformat()},
    )
    return ClosureOut(erase_after=erase_after)


@router.delete("/organizations/{org_id}/closure", status_code=204)
def delete_closure(
    org_id: uuid.UUID,
    body: ReasonIn,
    staff: CurrentStaff,
    session: DbSession,
    request_id: trail.RequestId,
) -> Response:
    _confirmed(session, org_id, None)
    try:
        cancel_operator_closure(session, org_id)
    except OperatorError as error:
        raise refusal(error) from None
    trail.write(
        session,
        staff,
        request_id,
        "operator.closure_cancelled",
        organization_id=org_id,
        reason=body.reason,
    )
    return Response(status_code=204)


@router.post("/organizations/{org_id}/erasure-requests", status_code=201)
def post_erasure_request(
    org_id: uuid.UUID,
    body: ConfirmedIn,
    staff: CurrentStaff,
    session: DbSession,
    request_id: trail.RequestId,
) -> ErasureRequestOut:
    _confirmed(session, org_id, body.confirm_name)
    try:
        created = request_erasure(session, org_id, staff.id)
    except OperatorError as error:
        raise refusal(error) from None
    trail.write(
        session,
        staff,
        request_id,
        "operator.erasure_requested",
        organization_id=org_id,
        target_id=str(created),
        reason=body.reason,
    )
    return ErasureRequestOut(id=created)


@router.post("/erasure-requests/{erasure_id}/approval")
def post_approval(
    erasure_id: uuid.UUID,
    body: ConfirmedIn,
    staff: CurrentStaff,
    session: DbSession,
    request_id: trail.RequestId,
) -> ApprovedOut:
    """The name is checked once the request names its organization; a mismatch raises, and the
    request's transaction rolls the approval back."""
    try:
        approved = approve_erasure(session, erasure_id, staff.id)
    except OperatorError as error:
        raise refusal(error) from None
    _confirmed(session, approved.organization_id, body.confirm_name)
    trail.write(
        session,
        staff,
        request_id,
        "operator.erasure_approved",
        organization_id=approved.organization_id,
        target_id=str(erasure_id),
        reason=body.reason,
        metadata={"not_before": approved.not_before.date().isoformat()},
    )
    return ApprovedOut(not_before=approved.not_before)


@router.delete("/erasure-requests/{erasure_id}", status_code=204)
def delete_erasure_request(
    erasure_id: uuid.UUID,
    body: ReasonIn,
    staff: CurrentStaff,
    session: DbSession,
    request_id: trail.RequestId,
) -> Response:
    try:
        org_id = cancel_erasure(session, erasure_id, staff.id)
    except OperatorError as error:
        raise refusal(error) from None
    trail.write(
        session,
        staff,
        request_id,
        "operator.erasure_cancelled",
        organization_id=org_id,
        target_id=str(erasure_id),
        reason=body.reason,
    )
    return Response(status_code=204)
