"""Identity's functions for the operator service (operator-portal spec, ADR-017, ADR-008).

Each runs on a session of the `atesta_operator` role, which crosses organizations by design and
never sets a tenant context (ADR-012 amendment 8). They read only the granted columns, and write
through lightweight table constructs: the ORM's `onupdate` would add `organizations.updated_at`,
which the role cannot write. None joins another module's tables; the operator service composes
the results and writes both audit trails.
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sqlalchemy import ColumnElement, Select, column, func, select, table, update
from sqlalchemy.orm import Session

from atesta_api.modules.identity.closure import GRACE, erase_after
from atesta_api.modules.identity.models import ApiToken, ApiTokenUsage, Invitation, Membership
from atesta_api.platform.audit import AuditEvent
from atesta_api.platform.tenancy import Organization

PAGE_SIZE = 50
SUSPENSION_REASONS = (
    "non_payment",
    "contract_ended",
    "customer_request",
    "security_review",
    "other",
)
type State = Literal["active", "suspended", "closing"]
type Sort = Literal["name", "created", "activity"]

# The columns the role may write (and the derived origin), so no default joins an UPDATE.
_ORG_WRITE = table(
    "organizations",
    *map(column, ("id", "suspended_at", "suspension_reason", "closure_requested_at")),
    column("closure_origin"),
)


class OperatorError(Exception):
    """A refusal the operator API turns into `operator.<code>` (spec, "API")."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class OrganizationMetadata:
    id: uuid.UUID
    name: str
    locale: str
    created_at: datetime
    trial_ends_at: datetime
    suspended_at: datetime | None
    suspension_reason: str | None
    closure_requested_at: datetime | None
    closure_origin: str | None
    last_activity: datetime | None = None

    @property
    def state(self) -> State:
        """Suspended wins for the badge; `closing` still shows through closure_requested_at."""
        if self.suspended_at is not None:
            return "suspended"
        return "active" if self.closure_requested_at is None else "closing"

    @property
    def erase_after(self) -> datetime | None:
        return erase_after(self.closure_requested_at)


@dataclass(frozen=True, slots=True)
class OrganizationFilters:
    """`within` and `exclude` carry the other modules' filters (plan, health, billing) as ids."""

    state: State | None = None
    within: frozenset[uuid.UUID] | None = None
    exclude: frozenset[uuid.UUID] = field(default_factory=frozenset)
    sort: Sort = "name"


@dataclass(frozen=True, slots=True)
class OrganizationPage:
    rows: list[OrganizationMetadata]
    total: int


@dataclass(frozen=True, slots=True)
class ApiKeyCounts:
    active: int
    calls: int


_META = (
    Organization.id,
    Organization.name,
    Organization.locale,
    Organization.created_at,
    Organization.trial_ends_at,
    Organization.suspended_at,
    Organization.suspension_reason,
    Organization.closure_requested_at,
    Organization.closure_origin,
)


def _activity() -> Select[uuid.UUID, datetime]:
    """Last customer activity: staff actions (`operator.*`) are not the customer's."""
    return (
        select(AuditEvent.organization_id, func.max(AuditEvent.occurred_at).label("at"))
        .where(AuditEvent.action.not_like("operator.%"))
        .group_by(AuditEvent.organization_id)
    )


def organization_metadata(session: Session, org_id: uuid.UUID) -> OrganizationMetadata | None:
    row = session.execute(select(*_META).where(Organization.id == org_id)).one_or_none()
    return None if row is None else OrganizationMetadata(*row)


def _search(query: str) -> ColumnElement[bool]:
    text = query.strip()
    try:
        return Organization.id == uuid.UUID(text)
    except ValueError:
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return Organization.name.ilike(f"%{escaped}%", escape="\\")


def organization_rows(
    session: Session, query: str, filters: OrganizationFilters, page: int
) -> OrganizationPage:
    """One page of organizations by name or exact id, filtered and sorted (spec, "Screens")."""
    activity = _activity().subquery()
    where: list[ColumnElement[bool]] = [_search(query)] if query.strip() else []
    if filters.state == "suspended":
        where.append(Organization.suspended_at.is_not(None))
    elif filters.state == "closing":
        where.append(Organization.closure_requested_at.is_not(None))
    elif filters.state == "active":
        where += [Organization.suspended_at.is_(None), Organization.closure_requested_at.is_(None)]
    if filters.within is not None:
        where.append(Organization.id.in_(filters.within))
    if filters.exclude:
        where.append(Organization.id.not_in(filters.exclude))
    order = {
        "name": (Organization.name, Organization.id),
        "created": (Organization.created_at.desc(), Organization.id),
        "activity": (activity.c.at.desc().nulls_last(), Organization.name, Organization.id),
    }[filters.sort]
    rows = session.execute(
        select(*_META, activity.c.at)
        .outerjoin(activity, activity.c.organization_id == Organization.id)
        .where(*where)
        .order_by(*order)
        .limit(PAGE_SIZE)
        .offset((max(page, 1) - 1) * PAGE_SIZE)
    ).all()
    total = session.scalar(select(func.count()).select_from(Organization).where(*where)) or 0
    return OrganizationPage([OrganizationMetadata(*r) for r in rows], int(total))


def member_counts(
    session: Session, org_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, dict[str, int]]:
    rows = session.execute(
        select(Membership.organization_id, Membership.role, func.count())
        .where(Membership.organization_id.in_(org_ids))
        .group_by(Membership.organization_id, Membership.role)
    )
    counts: dict[uuid.UUID, dict[str, int]] = {}
    for org_id, role, count in rows:
        counts.setdefault(org_id, {})[role] = count
    return counts


def invitation_counts(session: Session, org_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Pending invitations: not accepted, not revoked, not expired."""
    rows = session.execute(
        select(Invitation.organization_id, func.count())
        .where(
            Invitation.organization_id.in_(org_ids),
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > func.now(),
        )
        .group_by(Invitation.organization_id)
    )
    return {org_id: count for org_id, count in rows}


def last_activity(session: Session, org_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    query = _activity().where(AuditEvent.organization_id.in_(org_ids))
    return {org_id: at for org_id, at in session.execute(query)}


def api_key_counts(
    session: Session, org_ids: Collection[uuid.UUID], *, since: datetime
) -> dict[uuid.UUID, ApiKeyCounts]:
    """Active keys (not revoked, not expired) and calls since a moment, per organization."""
    active = dict(
        session.execute(
            select(ApiToken.organization_id, func.count())
            .where(
                ApiToken.organization_id.in_(org_ids),
                ApiToken.revoked_at.is_(None),
                ApiToken.expires_at > func.now(),
            )
            .group_by(ApiToken.organization_id)
        ).all()
    )
    calls = dict(
        session.execute(
            select(ApiTokenUsage.organization_id, func.count())
            .where(ApiTokenUsage.organization_id.in_(org_ids), ApiTokenUsage.at >= since)
            .group_by(ApiTokenUsage.organization_id)
        ).all()
    )
    return {o: ApiKeyCounts(active.get(o, 0), calls.get(o, 0)) for o in {*active, *calls}}


# --- writes ----------------------------------------------------------------------------------


def _refuse(session: Session, org_id: uuid.UUID, code: str) -> OperatorError:
    """`not_found` for an unknown organization, else the conflict the caller names."""
    known = session.scalar(select(Organization.id).where(Organization.id == org_id))
    return OperatorError(code if known is not None else "not_found")


def suspend(session: Session, org_id: uuid.UUID, reason_code: str) -> datetime:
    if reason_code not in SUSPENSION_REASONS:
        raise ValueError(f"unknown suspension reason {reason_code!r}")
    since = session.scalar(
        update(_ORG_WRITE)
        .where(_ORG_WRITE.c.id == org_id, _ORG_WRITE.c.suspended_at.is_(None))
        .values(suspended_at=func.now(), suspension_reason=reason_code)
        .returning(_ORG_WRITE.c.suspended_at)
    )
    if since is None:
        raise _refuse(session, org_id, "already_suspended")
    return since  # type: ignore[no-any-return]


def reactivate(session: Session, org_id: uuid.UUID) -> None:
    done = session.scalar(
        update(_ORG_WRITE)
        .where(_ORG_WRITE.c.id == org_id, _ORG_WRITE.c.suspended_at.is_not(None))
        .values(suspended_at=None, suspension_reason=None)
        .returning(_ORG_WRITE.c.id)
    )
    if done is None:
        raise _refuse(session, org_id, "not_suspended")


def start_operator_closure(session: Session, org_id: uuid.UUID) -> datetime:
    """The existing 30-day closure, with no person: `closure_origin` derives to `operator`."""
    started = session.scalar(
        update(_ORG_WRITE)
        .where(_ORG_WRITE.c.id == org_id, _ORG_WRITE.c.closure_requested_at.is_(None))
        .values(closure_requested_at=func.now())
        .returning(_ORG_WRITE.c.closure_requested_at)
    )
    if started is None:
        raise _refuse(session, org_id, "closure_exists")
    return started + GRACE  # type: ignore[no-any-return]


def cancel_operator_closure(session: Session, org_id: uuid.UUID) -> None:
    """Only a closure the operator started; an owner's stays the owner's to cancel."""
    done = session.scalar(
        update(_ORG_WRITE)
        .where(_ORG_WRITE.c.id == org_id, _ORG_WRITE.c.closure_origin == "operator")
        .values(closure_requested_at=None)
        .returning(_ORG_WRITE.c.id)
    )
    if done is None:
        origin = session.scalar(
            select(Organization.closure_origin).where(Organization.id == org_id)
        )
        raise _refuse(session, org_id, "closure_by_owner" if origin == "owner" else "no_closure")
