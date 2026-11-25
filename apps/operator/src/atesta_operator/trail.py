"""Both audit trails (ADR-017, "Audit: two trails"; spec, "Audit events").

Every write records the customer's event (when the spec's table says the customer sees it) and
the operator trail row in the request's one transaction, so both commit with the write or none
does. The request id links the two. A reason goes only to the operator trail; customer metadata
is scalar and never holds a reason or a billing value.
"""

import uuid
from typing import Annotated

from atesta_api.platform.audit import Scalar, record_by_atesta, record_operator
from fastapi import Depends
from sqlalchemy.orm import Session

from atesta_operator.auth import Staff


def new_request_id() -> str:
    return uuid.uuid4().hex


RequestId = Annotated[str, Depends(new_request_id)]


def write(
    session: Session,
    staff: Staff,
    request_id: str,
    action: str,
    *,
    organization_id: uuid.UUID | None,
    reason: str,
    target_id: str | None = None,
    customer_sees: bool = True,
    metadata: dict[str, Scalar] | None = None,
) -> None:
    """A staff write. `metadata` is what the customer sees, and the operator trail keeps it too."""
    if customer_sees:
        if organization_id is None:
            raise ValueError("a customer-visible event needs its organization")
        record_by_atesta(
            session,
            organization_id=organization_id,
            action=action,
            target_type="organization",
            target_id=target_id or str(organization_id),
            request_id=request_id,
            metadata=metadata,
        )
    record_operator(
        session,
        staff_id=staff.id,
        staff_role=staff.role,
        action=action,
        request_id=request_id,
        organization_id=organization_id,
        target_id=target_id,
        reason=reason,
        metadata=metadata,
    )


def read(
    session: Session,
    staff: Staff,
    request_id: str,
    action: str,
    *,
    organization_id: uuid.UUID | None = None,
) -> None:
    """A staff read: the operator trail only (spec, owner answer 5). No search text is stored."""
    record_operator(
        session,
        staff_id=staff.id,
        staff_role=staff.role,
        action=action,
        request_id=request_id,
        organization_id=organization_id,
    )
