"""Plan and billing details (operator-portal spec, "Screens" 4 and 5; ADR-009 amendments 2, 3).

Setting a plan upserts `subscriptions`, which the customer API reads through
`billing.api.entitlements` on its next request; no route here decides access by plan name.
"""

import uuid
from datetime import datetime
from typing import Annotated

from atesta_api.modules.billing.api import (
    Feature,
    Plan,
    UnknownAddonError,
    billing_profile,
    connector_limit,
    has_feature,
    known_addons,
    set_billing_profile,
    set_subscription,
)
from atesta_api.modules.identity.api import organization_metadata
from atesta_api.platform.db import DbSession
from fastapi import APIRouter
from pydantic import BaseModel, Field

from atesta_operator import trail
from atesta_operator.auth import CurrentStaff
from atesta_operator.errors import operator_error
from atesta_operator.formats import LENGTHS, invalid_field
from atesta_operator.organizations import BillingFullOut

router = APIRouter(prefix="/api/v1", tags=["billing"])
Reason = Annotated[str, Field(min_length=1, max_length=500)]


class PlanInfo(BaseModel):
    plan: Plan
    connector_limit: int | None
    features: list[Feature]


class PlansOut(BaseModel):
    plans: list[PlanInfo]
    addons: list[str]


@router.get("/plans")
def plans(staff: CurrentStaff) -> PlansOut:
    """What the plan editor offers: plans with their limits and features, and every add-on."""
    return PlansOut(
        plans=[
            PlanInfo(
                plan=p,
                connector_limit=connector_limit(p),
                features=[f for f in Feature if has_feature(p, f)],
            )
            for p in Plan
        ],
        addons=sorted(known_addons()),
    )


def _known(session: DbSession, org_id: uuid.UUID) -> None:
    if organization_metadata(session, org_id) is None:
        raise operator_error("operator.not_found")


class SubscriptionIn(BaseModel):
    plan: Annotated[str, Field(max_length=50)]
    addons: Annotated[list[Annotated[str, Field(max_length=100)]], Field(max_length=50)] = []
    note: Annotated[str, Field(max_length=500)] = ""  # kept with the plan: nothing internal
    reason: Reason


class SubscriptionOut(BaseModel):
    plan: Plan
    previous_plan: Plan | None
    addons: list[str]


@router.put("/organizations/{org_id}/subscription")
def put_subscription(
    org_id: uuid.UUID,
    body: SubscriptionIn,
    staff: CurrentStaff,
    session: DbSession,
    request_id: trail.RequestId,
) -> SubscriptionOut:
    _known(session, org_id)
    if body.plan not in {p.value for p in Plan}:
        raise operator_error("operator.invalid_plan")
    addons = frozenset(body.addons)
    try:
        previous = set_subscription(session, org_id, Plan(body.plan), addons, body.note)
    except UnknownAddonError:
        raise operator_error("operator.invalid_plan") from None
    trail.write(
        session,
        staff,
        request_id,
        "operator.plan_changed",
        organization_id=org_id,
        reason=body.reason,
        metadata={
            "plan": body.plan,
            "previous_plan": None if previous is None else previous.value,
            "addons": ",".join(sorted(addons)),
        },
    )
    return SubscriptionOut(plan=Plan(body.plan), previous_plan=previous, addons=sorted(addons))


@router.get("/organizations/{org_id}/billing-profile")
def get_billing_profile(
    org_id: uuid.UUID, staff: CurrentStaff, session: DbSession, request_id: trail.RequestId
) -> BillingFullOut:
    _known(session, org_id)
    details = billing_profile(session, org_id)
    if details is None:
        raise operator_error("operator.no_billing_profile")
    trail.read(session, staff, request_id, "billing_profile.viewed", organization_id=org_id)
    return BillingFullOut(
        **{f: getattr(details, f) for f in BillingFullOut.model_fields if f != "view"}
    )


class BillingProfileIn(BaseModel):
    """Every field as text, checked in code so a bad one names itself (`operator.invalid_field`)."""

    legal_name: str | None = None
    tax_id: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    postal_code: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    contact_email: str | None = None
    reason: Reason


class BillingProfileOut(BaseModel):
    changed: list[str]
    updated_at: datetime | None


@router.put("/organizations/{org_id}/billing-profile")
def put_billing_profile(
    org_id: uuid.UUID,
    body: BillingProfileIn,
    staff: CurrentStaff,
    session: DbSession,
    request_id: trail.RequestId,
) -> BillingProfileOut:
    _known(session, org_id)
    values = {name: getattr(body, name) for name in LENGTHS}
    bad = invalid_field(values)
    if bad is not None:
        raise operator_error("operator.invalid_field", field=bad)
    changed = set_billing_profile(session, org_id, values)
    if changed:  # field names only: the values are personal data (spec, "Audit events")
        trail.write(
            session,
            staff,
            request_id,
            "operator.billing_profile_updated",
            organization_id=org_id,
            reason=body.reason,
            metadata={"fields": ",".join(changed)},
        )
    details = billing_profile(session, org_id)
    return BillingProfileOut(
        changed=list(changed), updated_at=None if details is None else details.updated_at
    )
