"""Organization list and detail (operator-portal spec, "Screens" 2 and 3, "Metadata fields").

Composed from each module's own functions, a handful of grouped queries per page (spec,
"Composition"); no function joins another module's tables. Responses hold metadata only: never a
member's name or email, a connection's display name or tenant, or any content row. Support's
billing details are the summary model, so the full fields are absent, not hidden.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from atesta_api.modules.billing.api import (
    DEFAULT_PLAN,
    Plan,
    billing_profile,
    billing_summaries,
    connector_limit,
    subscriptions_for,
)
from atesta_api.modules.connections.api import health_counts
from atesta_api.modules.identity.api import (
    PAGE_SIZE,
    OrganizationFilters,
    api_key_counts,
    invitation_counts,
    latest_erasure,
    member_counts,
    organization_metadata,
    organization_rows,
)
from atesta_api.modules.scanning.api import scan_activity
from atesta_api.platform.db import DbSession
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from atesta_operator import trail
from atesta_operator.auth import CurrentStaff
from atesta_operator.errors import operator_error
from atesta_operator.policy import FULL_BILLING_DETAILS

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])
WINDOW = timedelta(days=30)
type Health = Literal["none", "ok", "attention", "pending"]
type State = Literal["active", "suspended", "closing"]


class PlanOut(BaseModel):
    plan: Plan
    default: bool  # no subscription row: DEFAULT_PLAN, and the trial applies
    addons: list[str] = []
    note: str = ""
    updated_at: datetime | None = None


class OrganizationRow(BaseModel):
    id: uuid.UUID
    name: str
    state: State
    plan: Plan
    plan_default: bool
    members: int
    health: Health
    last_activity: datetime | None
    created_at: datetime


class OrganizationList(BaseModel):
    rows: list[OrganizationRow]
    total: int
    page: int
    page_size: int


def _filters(
    session: DbSession,
    state: State | None,
    plan: str | None,
    health: str | None,
    billing: str | None,
    sort: Literal["name", "created", "activity"],
) -> OrganizationFilters:
    """The plan, health and billing filters are other modules' data: turned into id sets."""
    within: set[uuid.UUID] | None = None
    exclude: set[uuid.UUID] = set()
    if plan is not None:
        subscriptions = subscriptions_for(session, None)
        if plan == "default":
            exclude |= set(subscriptions)
        else:
            within = {o for o, s in subscriptions.items() if s.plan.value == plan}
    if health == "attention":
        attention = {o for o, h in health_counts(session, None).items() if h.health == health}
        within = attention if within is None else within & attention
    if billing == "missing":  # no row, or a row without every required field
        exclude |= {o for o, b in billing_summaries(session, None).items() if b.complete}
    return OrganizationFilters(
        state=state,
        within=None if within is None else frozenset(within),
        exclude=frozenset(exclude),
        sort=sort,
    )


@router.get("")
def list_organizations(
    staff: CurrentStaff,
    session: DbSession,
    request_id: trail.RequestId,
    q: Annotated[str, Query(max_length=200)] = "",
    state: State | None = None,
    plan: Literal["starter", "pro", "business", "default"] | None = None,
    health: Literal["attention"] | None = None,
    billing: Literal["missing"] | None = None,
    sort: Literal["name", "created", "activity"] = "name",
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
) -> OrganizationList:
    found = organization_rows(
        session, q, _filters(session, state, plan, health, billing, sort), page
    )
    ids = [o.id for o in found.rows]
    members = member_counts(session, ids)
    plans = subscriptions_for(session, ids)
    healths = health_counts(session, ids)
    trail.read(session, staff, request_id, "organizations.searched")
    return OrganizationList(
        rows=[
            OrganizationRow(
                id=o.id,
                name=o.name,
                state=o.state,
                plan=plans[o.id].plan if o.id in plans else DEFAULT_PLAN,
                plan_default=o.id not in plans,
                members=sum(members.get(o.id, {}).values()),
                health=healths[o.id].health if o.id in healths else "none",
                last_activity=o.last_activity,
                created_at=o.created_at,
            )
            for o in found.rows
        ],
        total=found.total,
        page=page,
        page_size=PAGE_SIZE,
    )


class ClosureOut(BaseModel):
    requested_at: datetime
    origin: Literal["owner", "operator"]
    erase_after: datetime


class BillingSummaryOut(BaseModel):
    view: Literal["summary"] = "summary"
    legal_name: str | None
    complete: bool


class BillingFullOut(BaseModel):
    view: Literal["full"] = "full"
    legal_name: str | None
    tax_id: str | None
    address_line1: str | None
    address_line2: str | None
    postal_code: str | None
    city: str | None
    region: str | None
    country: str | None
    contact_email: str | None
    complete: bool
    updated_at: datetime


class ConnectionsOut(BaseModel):
    by_provider: dict[str, dict[str, int]]
    health: Health
    in_use: int
    limit: int | None


class ScansOut(BaseModel):
    last_30_days: dict[str, int]
    last_finished: datetime | None


class ErasureOut(BaseModel):
    """The latest erasure request, for the admin's Erase screen (spec, "Screens" 8)."""

    id: uuid.UUID
    state: Literal["pending", "approved", "cancelled", "executed"]
    requested_at: datetime
    requested_by_me: bool
    approved_at: datetime | None
    receipt_id: uuid.UUID | None


def _erasure(session: DbSession, org_id: uuid.UUID, staff_id: uuid.UUID) -> ErasureOut | None:
    found = latest_erasure(session, org_id)
    if found is None:
        return None
    state: Literal["pending", "approved", "cancelled", "executed"] = (
        "executed"
        if found.executed_at
        else "cancelled"
        if found.cancelled_at
        else "approved"
        if found.approved_at
        else "pending"
    )
    return ErasureOut(
        id=found.id,
        state=state,
        requested_at=found.requested_at,
        requested_by_me=found.requested_by == staff_id,
        approved_at=found.approved_at,
        receipt_id=found.receipt_id,
    )


class OrganizationDetail(BaseModel):
    id: uuid.UUID
    name: str
    locale: str
    created_at: datetime
    trial_ends_at: datetime
    trial_ended: bool
    last_activity: datetime | None
    state: State
    suspended_at: datetime | None
    suspension_reason: str | None
    closure: ClosureOut | None
    plan: PlanOut
    billing: Annotated[BillingFullOut | BillingSummaryOut, Field(discriminator="view")] | None
    members: dict[str, int]
    pending_invitations: int
    connections: ConnectionsOut
    scans: ScansOut
    api_keys: int
    api_calls_30_days: int
    erasure: ErasureOut | None


def _billing(
    session: DbSession, org_id: uuid.UUID, full: bool
) -> BillingFullOut | BillingSummaryOut | None:
    if full:
        details = billing_profile(session, org_id)
        if details is None:
            return None
        return BillingFullOut(
            **{f: getattr(details, f) for f in BillingFullOut.model_fields if f != "view"}
        )
    summary = billing_summaries(session, [org_id]).get(org_id)
    if summary is None:
        return None
    return BillingSummaryOut(legal_name=summary.legal_name, complete=summary.complete)


@router.get("/{org_id}")
def organization_detail(
    org_id: uuid.UUID, staff: CurrentStaff, session: DbSession, request_id: trail.RequestId
) -> OrganizationDetail:
    org = organization_metadata(session, org_id)
    if org is None:
        raise operator_error("operator.not_found")
    now = datetime.now(UTC)
    ids = [org_id]
    subscription = subscriptions_for(session, ids).get(org_id)
    plan = PlanOut(plan=DEFAULT_PLAN, default=True)
    if subscription is not None:
        plan = PlanOut(
            plan=subscription.plan,
            default=False,
            addons=sorted(subscription.addons),
            note=subscription.note,
            updated_at=subscription.updated_at,
        )
    connections = health_counts(session, ids).get(org_id)
    scans = scan_activity(session, ids, since=now - WINDOW).get(org_id)
    keys = api_key_counts(session, ids, since=now - WINDOW).get(org_id)
    trail.read(session, staff, request_id, "organization.viewed", organization_id=org_id)
    return OrganizationDetail(
        id=org.id,
        name=org.name,
        locale=org.locale,
        created_at=org.created_at,
        trial_ends_at=org.trial_ends_at,
        trial_ended=subscription is None and org.trial_ends_at <= now,
        last_activity=org.last_activity,
        state=org.state,
        suspended_at=org.suspended_at,
        suspension_reason=org.suspension_reason,
        closure=None
        if org.closure_requested_at is None or org.erase_after is None
        else ClosureOut(
            requested_at=org.closure_requested_at,
            origin="owner" if org.closure_origin == "owner" else "operator",
            erase_after=org.erase_after,
        ),
        plan=plan,
        billing=_billing(session, org_id, full=staff.role in FULL_BILLING_DETAILS),
        members=member_counts(session, ids).get(org_id, {}),
        pending_invitations=invitation_counts(session, ids).get(org_id, 0),
        connections=ConnectionsOut(
            by_provider=connections.by_provider if connections else {},
            health=connections.health if connections else "none",
            in_use=connections.in_use if connections else 0,
            limit=connector_limit(plan.plan),
        ),
        scans=ScansOut(
            last_30_days=scans.by_status if scans else {},
            last_finished=scans.last_finished if scans else None,
        ),
        api_keys=keys.active if keys else 0,
        api_calls_30_days=keys.calls if keys else 0,
        erasure=_erasure(session, org_id, staff.id),
    )
