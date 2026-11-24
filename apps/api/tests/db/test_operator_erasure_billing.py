"""Erasure requests and billing functions for the operator service (operator-portal spec).

As in test_operator_functions: real Postgres, `atesta_operator` through SET LOCAL ROLE in one
superuser transaction that rolls back.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from atesta_api.modules.billing.api import (
    DEFAULT_PLAN,
    Plan,
    UnknownAddonError,
    billing_profile,
    billing_summaries,
    known_addons,
    set_billing_profile,
    set_subscription,
    subscriptions_for,
)
from atesta_api.modules.identity.api import (
    OperatorError,
    approve_erasure,
    cancel_erasure,
    request_erasure,
)
from sqlalchemy.orm import Session

from .test_operator_functions import NOW, OP, as_operator, org, seed, sql

__all__ = ["seed"]  # the fixture, imported for this module's tests


def staff(session: Session, role: str = "admin", disabled: bool = False) -> uuid.UUID:
    staff_id = uuid.uuid4()
    sql(
        session,
        "INSERT INTO operator_staff (id, cognito_sub, email, role, disabled_at)"
        " VALUES (:i, :s, :e, :r, :d)",
        i=staff_id,
        s=f"staff-{staff_id}",
        e=f"{staff_id}@atesta.test",
        r=role,
        d=NOW if disabled else None,
    )
    return staff_id


# --- erasure requests ----------------------------------------------------------------------


@pytest.fixture
def closing(seed: Session) -> uuid.UUID:
    return org(seed, "Leaving", closure_requested_at=datetime.now(UTC) - timedelta(days=31))


def _age(session: Session, request: uuid.UUID, hours: int) -> None:
    """Move a request back in time, as the superuser: the role can never write requested_at."""
    sql(session, "RESET ROLE")
    sql(
        session,
        "UPDATE erasure_requests SET requested_at = requested_at - make_interval(hours => :h)"
        " WHERE id = :r",
        h=hours,
        r=request,
    )
    sql(session, OP)


def test_erasure_needs_a_closure_and_one_open_request(seed: Session, closing: uuid.UUID) -> None:
    first, second = staff(seed), staff(seed)
    open_org = org(seed, "Open")
    session = as_operator(seed)
    with pytest.raises(OperatorError) as no_closure:
        request_erasure(session, open_org, first)
    assert no_closure.value.code == "no_closure"
    request = request_erasure(session, closing, first)
    with pytest.raises(OperatorError) as pending:
        request_erasure(session, closing, second)
    assert pending.value.code == "erasure_pending"
    assert request


def test_a_new_request_cancels_an_expired_one(seed: Session, closing: uuid.UUID) -> None:
    first, second = staff(seed), staff(seed)
    session = as_operator(seed)
    old = request_erasure(session, closing, first)
    _age(session, old, 24 * 8)
    new = request_erasure(session, closing, second)
    row = sql(
        seed,
        "SELECT cancelled_by, cancelled_at IS NOT NULL FROM erasure_requests WHERE id = :r",
        r=old,
    ).one()
    assert tuple(row) == (second, True)
    assert new != old


def test_a_second_admin_approves(seed: Session, closing: uuid.UUID) -> None:
    first, second = staff(seed), staff(seed)
    session = as_operator(seed)
    request = request_erasure(session, closing, first)
    with pytest.raises(OperatorError) as same:
        approve_erasure(session, request, first)
    assert same.value.code == "same_approver"
    approved = approve_erasure(session, request, second)
    assert approved.organization_id == closing
    assert approved.not_before.date() == (datetime.now(UTC) - timedelta(days=1)).date()
    with pytest.raises(OperatorError) as twice:
        approve_erasure(session, request, second)
    assert twice.value.code == "erasure_approved"


def test_a_sole_admin_approves_their_own_after_72_hours(seed: Session, closing: uuid.UUID) -> None:
    sql(seed, "UPDATE operator_staff SET disabled_at = now() WHERE role = 'admin'")
    sole = staff(seed)
    staff(seed, role="billing")
    staff(seed, disabled=True)
    session = as_operator(seed)
    request = request_erasure(session, closing, sole)
    with pytest.raises(OperatorError) as early:
        approve_erasure(session, request, sole)
    assert early.value.code == "cooling_off"
    _age(session, request, 73)
    assert approve_erasure(session, request, sole).organization_id == closing


def test_expired_and_cancelled_requests_are_not_approved(seed: Session, closing: uuid.UUID) -> None:
    first, second = staff(seed), staff(seed)
    session = as_operator(seed)
    request = request_erasure(session, closing, first)
    _age(session, request, 24 * 7 + 1)
    with pytest.raises(OperatorError) as expired:
        approve_erasure(session, request, second)
    assert expired.value.code == "erasure_expired"
    assert cancel_erasure(session, request, second) == closing
    with pytest.raises(OperatorError) as cancelled:
        approve_erasure(session, request, second)
    assert cancelled.value.code == "erasure_cancelled"
    with pytest.raises(OperatorError) as again:
        cancel_erasure(session, request, second)
    assert again.value.code == "erasure_cancelled"
    with pytest.raises(OperatorError) as unknown:
        cancel_erasure(session, uuid.uuid4(), second)
    assert unknown.value.code == "not_found"


def test_an_executed_request_cannot_be_cancelled(seed: Session, closing: uuid.UUID) -> None:
    first, second = staff(seed), staff(seed)
    session = as_operator(seed)
    request = request_erasure(session, closing, first)
    approve_erasure(session, request, second)
    sql(seed, "RESET ROLE")
    receipt = uuid.uuid4()
    sql(
        seed,
        "INSERT INTO erasure_receipts (id, organization_id, closure_requested_at, note, row_counts)"
        " VALUES (:i, :o, now(), '', '{}')",
        i=receipt,
        o=closing,
    )
    sql(
        seed,
        "UPDATE erasure_requests SET executed_at = now(), receipt_id = :i WHERE id = :r",
        i=receipt,
        r=request,
    )
    with pytest.raises(OperatorError) as executed:
        cancel_erasure(as_operator(seed), request, second)
    assert executed.value.code == "erasure_executed"


# --- billing -------------------------------------------------------------------------------


def test_set_subscription_upserts_and_returns_the_previous_plan(seed: Session) -> None:
    target = org(seed, "Plan")
    session = as_operator(seed)
    assert subscriptions_for(session, [target]) == {}  # no row: DEFAULT_PLAN applies
    assert set_subscription(session, target, Plan.STARTER, frozenset(), "contract 1") is None
    addon = sorted(known_addons())[0]
    previous = set_subscription(session, target, Plan.PRO, frozenset({addon}), "contract 2")
    assert previous == Plan.STARTER
    row = subscriptions_for(session, [target])[target]
    assert (row.plan, row.addons, row.note) == (Plan.PRO, frozenset({addon}), "contract 2")
    with pytest.raises(UnknownAddonError):
        set_subscription(session, target, Plan.PRO, frozenset({"not_an_addon"}), "x")
    assert DEFAULT_PLAN == Plan.BUSINESS


def test_known_addons_are_features_and_framework_addons() -> None:
    assert "evidence_export" in known_addons()
    assert all(a == a.strip() and a for a in known_addons())


def test_billing_profile_round_trip_and_changed_fields(seed: Session) -> None:
    target = org(seed, "Billing")
    session = as_operator(seed)
    assert billing_profile(session, target) is None
    assert billing_summaries(session, [target]) == {}
    fields = {
        "legal_name": "Ejemplo S.L.",
        "tax_id": "B00000000",
        "address_line1": "Calle 1",
        "postal_code": "28001",
        "city": "Madrid",
        "region": "Madrid",
        "country": "ES",
    }
    assert set_billing_profile(session, target, fields) == tuple(sorted(fields))
    summary = billing_summaries(session, [target])[target]
    assert (summary.legal_name, summary.complete) == ("Ejemplo S.L.", False)
    changed = set_billing_profile(
        session, target, {"contact_email": "billing@example.com", "city": "Madrid"}
    )
    assert changed == ("contact_email",)
    details = billing_profile(session, target)
    assert details is not None and details.complete and details.address_line2 is None
    assert set_billing_profile(session, target, {"city": "Madrid"}) == ()
    with pytest.raises(ValueError, match="field"):
        set_billing_profile(session, target, {"organization_id": "x"})
