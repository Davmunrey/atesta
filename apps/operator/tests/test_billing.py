"""Plan and billing details (operator-portal spec, "Plan and billing details", "Audit events" and
the "Audit" criteria): upserts, refusals, what each trail holds, and both trails in one
transaction or neither. Real Postgres as atesta_operator.
"""

import uuid
from typing import Any

import pytest
from atesta_api.modules.billing.api import Plan, entitlements
from atesta_operator import trail
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from . import seed
from .conftest import Issuer, MakeStaff, bearer
from .test_organizations import operator_rows

VALID = {
    "legal_name": "Ejemplo Servicios S.L.",
    "tax_id": "B12345678",
    "address_line1": "Calle Mayor 1",
    "address_line2": None,
    "postal_code": "28001",
    "city": "Madrid",
    "region": "Madrid",
    "country": "ES",
    "contact_email": "facturas@ejemplo.test",
    "reason": "Contract signed; ticket 42",
}


@pytest.fixture
def admin(staff_pool: Issuer, make_staff: MakeStaff) -> dict[str, str]:
    return bearer(staff_pool.token(make_staff("admin")))


@pytest.fixture
def billing_staff(staff_pool: Issuer, make_staff: MakeStaff) -> dict[str, str]:
    return bearer(staff_pool.token(make_staff("billing")))


def customer_events(engine: Engine, org_id: uuid.UUID) -> list[Any]:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "SELECT action, actor_user_id, metadata, request_id FROM audit_events"
                " WHERE organization_id = :o ORDER BY occurred_at"
            ),
            {"o": org_id},
        ).all()


def test_the_plan_editor_lists_plans_and_add_ons(
    client: TestClient, billing_staff: dict[str, str]
) -> None:
    body = client.get("/api/v1/plans", headers=billing_staff).json()
    assert [p["plan"] for p in body["plans"]] == ["starter", "pro", "business"]
    assert body["plans"][0]["connector_limit"] == 1 and body["plans"][2]["connector_limit"] is None
    assert "trust_center" in body["addons"]


def test_setting_a_plan_upserts_and_writes_both_trails(
    client: TestClient, superuser: Engine, billing_staff: dict[str, str]
) -> None:
    o = seed.org(superuser, "Plan")
    url = f"/api/v1/organizations/{o.id}/subscription"
    first = client.put(url, json={"plan": "starter", "reason": "Signed"}, headers=billing_staff)
    assert first.json() == {"plan": "starter", "previous_plan": None, "addons": []}
    second = client.put(
        url,
        json={"plan": "pro", "addons": ["trust_center"], "note": "Annual", "reason": "Upsell"},
        headers=billing_staff,
    )
    assert second.json() == {"plan": "pro", "previous_plan": "starter", "addons": ["trust_center"]}
    with Session(superuser) as session:  # what the customer API reads on its next request
        assert entitlements(session, o.id).plan is Plan.PRO
    events = customer_events(superuser, o.id)
    assert [e.action for e in events] == ["operator.plan_changed"] * 2
    assert events[1].actor_user_id is None
    assert events[1].metadata == {
        "plan": "pro",
        "previous_plan": "starter",
        "addons": "trust_center",
    }
    rows = operator_rows(superuser, "operator.plan_changed", o.id)
    assert [(r.staff_role, r.reason) for r in rows] == [
        ("billing", "Signed"),
        ("billing", "Upsell"),
    ]
    assert rows[1].request_id == events[1].request_id  # the trails link through the request id


@pytest.mark.parametrize(
    "body",
    [{"plan": "enterprise"}, {"plan": "pro", "addons": ["unknown_addon"]}],
    ids=["unknown plan", "unknown add-on"],
)
def test_an_unknown_plan_or_add_on_is_422(
    client: TestClient, superuser: Engine, billing_staff: dict[str, str], body: dict[str, Any]
) -> None:
    o = seed.org(superuser, "Bad plan")
    response = client.put(
        f"/api/v1/organizations/{o.id}/subscription",
        json={**body, "reason": "x"},
        headers=billing_staff,
    )
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "operator.invalid_plan"}}
    assert customer_events(superuser, o.id) == []


@pytest.mark.parametrize("reason", ["", "x" * 501, None])
def test_every_write_needs_a_reason_of_1_to_500_characters(
    client: TestClient, superuser: Engine, admin: dict[str, str], reason: str | None
) -> None:
    o = seed.org(superuser, "Reason")
    body: dict[str, Any] = {"plan": "pro"} if reason is None else {"plan": "pro", "reason": reason}
    response = client.put(f"/api/v1/organizations/{o.id}/subscription", json=body, headers=admin)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "request.invalid"


def test_billing_details_round_trip_and_name_only_the_changed_fields(
    client: TestClient, superuser: Engine, billing_staff: dict[str, str]
) -> None:
    o = seed.org(superuser, "Billing")
    url = f"/api/v1/organizations/{o.id}/billing-profile"
    assert client.get(url, headers=billing_staff).json() == {
        "detail": {"code": "operator.no_billing_profile"}
    }
    created = client.put(url, json=VALID, headers=billing_staff)
    assert created.status_code == 200
    assert created.json()["changed"] == sorted(
        k for k, v in VALID.items() if v is not None and k != "reason"
    )
    changed = client.put(
        url, json={**VALID, "contact_email": "otra@ejemplo.test"}, headers=billing_staff
    )
    assert changed.json()["changed"] == ["contact_email"]
    stored = client.get(url, headers=billing_staff).json()
    assert stored["contact_email"] == "otra@ejemplo.test" and stored["complete"] is True
    events = customer_events(superuser, o.id)
    assert events[-1].action == "operator.billing_profile_updated"
    assert events[-1].metadata == {"fields": "contact_email"}
    trail_rows = operator_rows(superuser, "operator.billing_profile_updated", o.id)
    assert trail_rows[-1].metadata == {"fields": "contact_email"}
    dumped = str([tuple(e) for e in events]) + str([tuple(r) for r in trail_rows])
    assert "otra@ejemplo.test" not in dumped and "B12345678" not in dumped  # names, never values
    assert "Contract signed" not in str([tuple(e) for e in events])  # the reason stays internal


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"tax_id": "12345678"}, "tax_id"),  # no letter
        ({"tax_id": "I1234567A"}, "tax_id"),  # I is no legal-form letter (Orden EHA/451/2008)
        ({"country": "es"}, "country"),
        ({"country": "FR", "tax_id": "FR-12/345"}, "tax_id"),
        ({"contact_email": "not-an-email"}, "contact_email"),
        ({"legal_name": None}, "legal_name"),
        ({"city": "   "}, "city"),
        ({"region": "Madrid\n"}, "region"),
        ({"postal_code": "2800\u0000"}, "postal_code"),
        ({"address_line1": "x" * 201}, "address_line1"),
    ],
)
def test_a_field_failing_its_format_is_422_with_its_name(
    client: TestClient,
    superuser: Engine,
    billing_staff: dict[str, str],
    change: dict[str, Any],
    field: str,
) -> None:
    o = seed.org(superuser, "Format")
    response = client.put(
        f"/api/v1/organizations/{o.id}/billing-profile",
        json={**VALID, **change},
        headers=billing_staff,
    )
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "operator.invalid_field", "field": field}}


@pytest.mark.parametrize(
    ("tax_id", "country"),
    [
        ("B-1234567-8", "ES"),  # an entity, with separators
        ("12345678Z", "ES"),  # a national's NIF
        ("X1234567L", "ES"),  # an NIE
        ("L1234567A", "ES"),  # a Spaniard resident abroad
        ("FR12345678901", "FR"),
    ],
)
def test_well_formed_tax_ids_pass(
    client: TestClient, superuser: Engine, billing_staff: dict[str, str], tax_id: str, country: str
) -> None:
    o = seed.org(superuser, "Tax")
    response = client.put(
        f"/api/v1/organizations/{o.id}/billing-profile",
        json={**VALID, "tax_id": tax_id, "country": country},
        headers=billing_staff,
    )
    assert response.status_code == 200, response.json()


def test_a_write_to_an_unknown_organization_is_404(
    client: TestClient, billing_staff: dict[str, str]
) -> None:
    for url, body in (
        (f"/api/v1/organizations/{uuid.uuid4()}/subscription", {"plan": "pro", "reason": "x"}),
        (f"/api/v1/organizations/{uuid.uuid4()}/billing-profile", VALID),
    ):
        response = client.put(url, json=body, headers=billing_staff)
        assert response.json() == {"detail": {"code": "operator.not_found"}}


def test_both_trails_and_the_write_commit_together_or_not_at_all(
    client: TestClient,
    superuser: Engine,
    billing_staff: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The operator trail row fails after the plan and the customer event were written: the
    request's one transaction rolls all three back."""
    o = seed.org(superuser, "Atomic")

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the operator trail could not be written")

    monkeypatch.setattr(trail, "record_operator", fail)
    failing = TestClient(client.app, base_url="https://testserver", raise_server_exceptions=False)
    response = failing.put(
        f"/api/v1/organizations/{o.id}/subscription",
        json={"plan": "starter", "reason": "x"},
        headers=billing_staff,
    )
    assert response.status_code == 500
    with superuser.begin() as conn:
        plans = conn.execute(
            text("SELECT count(*) FROM subscriptions WHERE organization_id = :o"), {"o": o.id}
        ).scalar()
    assert plans == 0 and customer_events(superuser, o.id) == []
    assert operator_rows(superuser, "operator.plan_changed", o.id) == []
