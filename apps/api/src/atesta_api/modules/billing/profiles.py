"""Billing details (operator-portal spec, ADR-012 amendment 8). The operator writes them; owners
read them in the console, in their organization's context. Format rules live in the operator API.
"""

import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass, fields
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from atesta_api.modules.billing.models import BILLING_FIELDS, BillingProfile

FIELDS = (*BILLING_FIELDS, "country")
# Every field but the second address line makes the details complete (spec, "Metadata fields").
REQUIRED = tuple(f for f in FIELDS if f != "address_line2")


@dataclass(frozen=True, slots=True)
class BillingDetails:
    legal_name: str | None
    tax_id: str | None
    address_line1: str | None
    address_line2: str | None
    postal_code: str | None
    city: str | None
    region: str | None
    country: str | None
    contact_email: str | None
    updated_at: datetime

    @property
    def complete(self) -> bool:
        return all(getattr(self, name) is not None for name in REQUIRED)


@dataclass(frozen=True, slots=True)
class BillingSummary:
    """What every staff role sees: the legal name and whether the details are complete."""

    legal_name: str | None
    complete: bool


_COLUMNS = tuple(getattr(BillingProfile, f.name) for f in fields(BillingDetails))


def billing_profile(session: Session, organization_id: uuid.UUID) -> BillingDetails | None:
    row = session.execute(
        select(*_COLUMNS).where(BillingProfile.organization_id == organization_id)
    ).one_or_none()
    return None if row is None else BillingDetails(*row)


def billing_summaries(
    session: Session, org_ids: Collection[uuid.UUID] | None
) -> dict[uuid.UUID, BillingSummary]:
    """Per organization with a row; None reads every organization (the list's billing filter)."""
    query = select(BillingProfile.organization_id, *_COLUMNS)
    if org_ids is not None:
        query = query.where(BillingProfile.organization_id.in_(org_ids))
    return {
        row[0]: BillingSummary(row[1], BillingDetails(*row[1:]).complete)
        for row in session.execute(query)
    }


def set_billing_profile(
    session: Session, organization_id: uuid.UUID, values: Mapping[str, str | None]
) -> tuple[str, ...]:
    """Upsert the given fields; returns the names of those that changed (never their values,
    which the audit trails must not hold). Nothing is written when nothing changed."""
    unknown = sorted(set(values) - set(FIELDS))
    if unknown:
        raise ValueError(f"unknown billing field {unknown[0]!r}")
    current = billing_profile(session, organization_id)
    changed = tuple(
        sorted(
            name
            for name, value in values.items()
            if (None if current is None else getattr(current, name)) != value
        )
    )
    if changed:
        session.execute(
            insert(BillingProfile)
            .values(organization_id=organization_id, **values)
            .on_conflict_do_update(
                index_elements=[BillingProfile.organization_id],
                set_={**{name: values[name] for name in changed}, "updated_at": func.now()},
            )
        )
    return changed
