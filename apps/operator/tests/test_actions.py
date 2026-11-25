"""Admin actions (operator-portal spec, "Suspension", "Export and closure", "Erasure", "Staff
identity and roles" and "Audit" criteria): typed names, state refusals, both trails, and the
erasure rules (a second admin, or the sole admin after 72 hours; 7-day expiry). Real Postgres as
atesta_operator; time is moved by editing rows as the superuser.
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from atesta_api.modules.identity.api import OperatorError, change_staff
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from . import seed
from .conftest import OPERATOR_PASSWORD, Issuer, MakeStaff, bearer
from .test_billing import customer_events
from .test_organizations import operator_rows


def staff_id(engine: Engine, sub: str) -> uuid.UUID:
    found: uuid.UUID = seed.run(
        engine, "SELECT id FROM operator_staff WHERE cognito_sub = :s", s=sub
    ).scalar_one()
    return found


def org_row(engine: Engine, org_id: uuid.UUID) -> Any:
    return seed.run(
        engine,
        "SELECT suspended_at, suspension_reason, closure_requested_at, closure_origin"
        " FROM organizations WHERE id = :o",
        o=org_id,
    ).one()


@pytest.fixture
def admin_sub(make_staff: MakeStaff) -> str:
    return make_staff("admin")


@pytest.fixture
def admin(staff_pool: Issuer, admin_sub: str) -> dict[str, str]:
    return bearer(staff_pool.token(admin_sub))


def test_suspend_and_reactivate(
    client: TestClient, superuser: Engine, admin: dict[str, str]
) -> None:
    o = seed.org(superuser, "Suspend")
    url = f"/api/v1/organizations/{o.id}/suspension"
    body = {"reason_code": "non_payment", "confirm_name": o.name, "reason": "Invoice 7 unpaid"}
    done = client.post(url, json=body, headers=admin)
    assert done.status_code == 200 and "suspended_at" in done.json()
    assert org_row(superuser, o.id).suspension_reason == "non_payment"
    again = client.post(url, json=body, headers=admin)
    assert again.status_code == 409
    assert again.json() == {"detail": {"code": "operator.already_suspended"}}
    back = client.request("DELETE", url, json={"reason": "Paid"}, headers=admin)
    assert back.status_code == 204 and org_row(superuser, o.id).suspended_at is None
    twice = client.request("DELETE", url, json={"reason": "Paid"}, headers=admin)
    assert twice.json() == {"detail": {"code": "operator.not_suspended"}}
    events = customer_events(superuser, o.id)
    assert [(e.action, e.actor_user_id, e.metadata) for e in events] == [
        ("operator.suspended", None, {"reason_code": "non_payment"}),
        ("operator.reactivated", None, {}),
    ]
    assert [r.reason for r in operator_rows(superuser, "operator.suspended", o.id)] == [
        "Invoice 7 unpaid"
    ]


@pytest.mark.parametrize("typed", ["", "suspend", " Suspend", "Suspend "])
def test_a_typed_name_that_is_not_exact_is_422_and_changes_nothing(
    client: TestClient, superuser: Engine, admin: dict[str, str], typed: str
) -> None:
    o = seed.org(superuser, "Suspend")
    confirm = typed if typed == "" else typed.replace("uspend", "uspend " + o.name.split()[1])
    for path, body in (
        ("suspension", {"reason_code": "other", "confirm_name": confirm, "reason": "x"}),
        ("closure", {"confirm_name": confirm, "reason": "x"}),
        ("erasure-requests", {"confirm_name": confirm, "reason": "x"}),
    ):
        response = client.post(f"/api/v1/organizations/{o.id}/{path}", json=body, headers=admin)
        assert response.status_code == 422
        if typed:
            assert response.json() == {"detail": {"code": "operator.name_mismatch"}}
    assert tuple(org_row(superuser, o.id)) == (None, None, None, None)
    assert customer_events(superuser, o.id) == []


def test_operator_closure_start_and_cancel(
    client: TestClient, superuser: Engine, admin: dict[str, str]
) -> None:
    o = seed.org(superuser, "Close")
    url = f"/api/v1/organizations/{o.id}/closure"
    started = client.post(url, json={"confirm_name": o.name, "reason": "Left"}, headers=admin)
    assert started.status_code == 200
    assert org_row(superuser, o.id).closure_origin == "operator"
    again = client.post(url, json={"confirm_name": o.name, "reason": "Left"}, headers=admin)
    assert again.json() == {"detail": {"code": "operator.closure_exists"}}
    erase_after = started.json()["erase_after"][:10]
    assert customer_events(superuser, o.id)[0].metadata == {"erase_after": erase_after}
    cancelled = client.request("DELETE", url, json={"reason": "Stays"}, headers=admin)
    assert cancelled.status_code == 204 and org_row(superuser, o.id).closure_requested_at is None


def test_an_owner_closure_is_the_owners_to_cancel(
    client: TestClient, superuser: Engine, admin: dict[str, str]
) -> None:
    o = seed.org(superuser, "Owner closes")
    seed.run(
        superuser,
        "UPDATE organizations SET closure_requested_at = now(), closure_requested_by = :u"
        " WHERE id = :o",
        u=o.owner,
        o=o.id,
    )
    response = client.request(
        "DELETE", f"/api/v1/organizations/{o.id}/closure", json={"reason": "x"}, headers=admin
    )
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "operator.closure_by_owner"}}
    assert org_row(superuser, o.id).closure_origin == "owner"


def request_erasure(client: TestClient, o: seed.Org, headers: dict[str, str]) -> Any:
    return client.post(
        f"/api/v1/organizations/{o.id}/erasure-requests",
        json={"confirm_name": o.name, "reason": "Contract ended"},
        headers=headers,
    )


def approve(client: TestClient, o: seed.Org, erasure: str, headers: dict[str, str]) -> Any:
    return client.post(
        f"/api/v1/erasure-requests/{erasure}/approval",
        json={"confirm_name": o.name, "reason": "Checked"},
        headers=headers,
    )


def closed(superuser: Engine, prefix: str) -> seed.Org:
    return seed.org(superuser, prefix, closure_requested_at=seed.NOW - timedelta(days=31))


def test_erasure_needs_a_closure_and_one_open_request(
    client: TestClient, superuser: Engine, admin: dict[str, str]
) -> None:
    open_org = seed.org(superuser, "Open")
    assert request_erasure(client, open_org, admin).json() == {
        "detail": {"code": "operator.no_closure"}
    }
    o = closed(superuser, "Closed")
    first = request_erasure(client, o, admin)
    assert first.status_code == 201
    assert request_erasure(client, o, admin).json() == {
        "detail": {"code": "operator.erasure_pending"}
    }
    trail_row = operator_rows(superuser, "operator.erasure_requested", o.id)[0]
    assert trail_row.reason == "Contract ended"
    assert [e.action for e in customer_events(superuser, o.id)] == ["operator.erasure_requested"]


def test_a_second_admin_approves_and_the_requester_cannot(
    client: TestClient,
    superuser: Engine,
    admin: dict[str, str],
    staff_pool: Issuer,
    make_staff: MakeStaff,
) -> None:
    second = bearer(staff_pool.token(make_staff("admin")))
    o = closed(superuser, "Two admins")
    erasure = request_erasure(client, o, admin).json()["id"]
    assert approve(client, o, erasure, admin).json() == {
        "detail": {"code": "operator.same_approver"}
    }
    wrong = client.post(
        f"/api/v1/erasure-requests/{erasure}/approval",
        json={"confirm_name": "Someone else", "reason": "x"},
        headers=second,
    )
    assert wrong.json() == {"detail": {"code": "operator.name_mismatch"}}
    approved_at = seed.run(
        superuser, "SELECT approved_at FROM erasure_requests WHERE id = :e", e=erasure
    ).scalar()
    assert approved_at is None  # the mismatch rolled the approval back
    done = approve(client, o, erasure, second)
    assert done.status_code == 200
    assert done.json()["not_before"][:10] == (seed.NOW - timedelta(days=1)).date().isoformat()
    assert customer_events(superuser, o.id)[-1].metadata == {
        "not_before": done.json()["not_before"][:10]
    }
    assert approve(client, o, erasure, second).json() == {
        "detail": {"code": "operator.erasure_approved"}
    }


def test_a_sole_admin_approves_their_own_request_after_72_hours(
    client: TestClient, superuser: Engine, admin: dict[str, str]
) -> None:
    o = closed(superuser, "Sole admin")
    erasure = request_erasure(client, o, admin).json()["id"]
    assert approve(client, o, erasure, admin).json() == {"detail": {"code": "operator.cooling_off"}}
    seed.run(
        superuser,
        "UPDATE erasure_requests SET requested_at = now() - interval '73 hours' WHERE id = :e",
        e=erasure,
    )
    assert approve(client, o, erasure, admin).status_code == 200


def test_an_expired_request_is_refused_and_a_new_one_replaces_it(
    client: TestClient, superuser: Engine, admin: dict[str, str]
) -> None:
    o = closed(superuser, "Expired")
    erasure = request_erasure(client, o, admin).json()["id"]
    seed.run(
        superuser,
        "UPDATE erasure_requests SET requested_at = now() - interval '8 days' WHERE id = :e",
        e=erasure,
    )
    assert approve(client, o, erasure, admin).json() == {
        "detail": {"code": "operator.erasure_expired"}
    }
    renewed = request_erasure(client, o, admin)
    assert renewed.status_code == 201 and renewed.json()["id"] != erasure
    cancelled = seed.run(
        superuser, "SELECT cancelled_at FROM erasure_requests WHERE id = :e", e=erasure
    ).scalar()
    assert cancelled is not None


def test_cancel_before_it_runs_never_after(
    client: TestClient, superuser: Engine, admin: dict[str, str]
) -> None:
    o = closed(superuser, "Cancel")
    erasure = request_erasure(client, o, admin).json()["id"]
    url = f"/api/v1/erasure-requests/{erasure}"
    assert (
        client.request("DELETE", url, json={"reason": "Customer stays"}, headers=admin).status_code
        == 204
    )
    assert approve(client, o, erasure, admin).json() == {
        "detail": {"code": "operator.erasure_cancelled"}
    }
    assert customer_events(superuser, o.id)[-1].action == "operator.erasure_cancelled"
    executed = closed(superuser, "Executed")
    run = request_erasure(client, executed, admin).json()["id"]
    receipt = uuid.uuid4()
    seed.run(
        superuser,
        "INSERT INTO erasure_receipts (id, organization_id, closure_requested_at, note,"
        " row_counts) VALUES (:r, :o, now(), 'test', '{\"memberships\": 2, \"users\": 1}')",
        r=receipt,
        o=executed.id,
    )
    seed.run(
        superuser,
        "UPDATE erasure_requests SET approved_by = requested_by, requested_at = now() -"
        " interval '4 days', approved_at = now(), executed_at = now(), receipt_id = :r"
        " WHERE id = :e",
        r=receipt,
        e=run,
    )
    done = client.request(
        "DELETE", f"/api/v1/erasure-requests/{run}", json={"reason": "x"}, headers=admin
    )
    assert done.json() == {"detail": {"code": "operator.erasure_executed"}}
    receipts = client.get("/api/v1/erasure-receipts", headers=admin).json()
    mine = [r for r in receipts["rows"] if r["id"] == str(receipt)]
    assert mine and mine[0]["rows"] == 3 and mine[0]["organization_id"] == str(executed.id)
    assert set(mine[0]) == {"id", "organization_id", "closure_requested_at", "erased_at", "rows"}
    detail = client.get(f"/api/v1/organizations/{executed.id}", headers=admin).json()
    assert detail["erasure"]["state"] == "executed" and detail["erasure"]["receipt_id"] == str(
        receipt
    )


def test_staff_management(
    client: TestClient,
    superuser: Engine,
    admin: dict[str, str],
    admin_sub: str,
    staff_pool: Issuer,
    make_staff: MakeStaff,
) -> None:
    colleague = make_staff("support", email="new.colleague@atesta.test")
    colleague_id = staff_id(superuser, colleague)
    team = client.get("/api/v1/staff", headers=admin).json()
    assert {"id": str(colleague_id), "email": "new.colleague@atesta.test", "role": "support",
            "disabled_at": None} in team  # fmt: skip
    me = staff_id(superuser, admin_sub)
    own = client.patch(
        f"/api/v1/staff/{me}", json={"role": "billing", "reason": "x"}, headers=admin
    )
    assert own.json() == {"detail": {"code": "operator.self_change"}}
    promoted = client.patch(
        f"/api/v1/staff/{colleague_id}", json={"role": "billing", "reason": "Joins billing"},
        headers=admin,
    )  # fmt: skip
    assert promoted.json()["role"] == "billing"
    off = client.patch(
        f"/api/v1/staff/{colleague_id}", json={"disabled": True, "reason": "Left"}, headers=admin
    )
    assert off.json()["disabled_at"] is not None
    gone = client.get("/api/v1/me", headers=bearer(staff_pool.token(colleague)))
    assert gone.json() == {"detail": {"code": "operator.forbidden"}}
    rows = client.get(
        "/api/v1/operator-events", params={"action": "staff.role_changed"}, headers=admin
    ).json()["rows"]
    mine = [r for r in rows if r["target_id"] == str(colleague_id)]
    assert mine[0]["metadata"] == {"role": "billing", "previous_role": "support"}
    assert mine[0]["reason"] == "Joins billing" and mine[0]["organization_id"] is None
    assert operator_rows(superuser, "staff.disabled")[-1].reason == "Left"


def test_the_last_enabled_admin_is_never_demoted_or_disabled(
    database: Any, superuser: Engine, make_staff: MakeStaff
) -> None:
    """Through the API an admin acts and cannot change their own row, so two admins exist; the
    module function still refuses on its own, as when two admins demote each other at once."""
    from atesta_api.platform.db import make_engine

    only_admin = staff_id(superuser, make_staff("admin"))
    actor = staff_id(superuser, make_staff("billing"))
    engine = make_engine(
        database.set(username="atesta_operator", password=OPERATOR_PASSWORD), sslmode="disable"
    )
    try:
        for change in ({"role": "support"}, {"disabled": True}):
            with Session(engine) as session, pytest.raises(OperatorError) as refused:
                change_staff(session, only_admin, actor_id=actor, **change)  # type: ignore[arg-type]
            assert refused.value.code == "last_admin"
    finally:
        engine.dispose()
        seed.run(
            superuser, "UPDATE operator_staff SET disabled_at = now() WHERE disabled_at IS NULL"
        )


def test_the_operator_trail_filters_by_organization(
    client: TestClient, superuser: Engine, admin: dict[str, str]
) -> None:
    o = seed.org(superuser, "Trail")
    client.get(f"/api/v1/organizations/{o.id}", headers=admin)
    client.post(
        f"/api/v1/organizations/{o.id}/closure",
        json={"confirm_name": o.name, "reason": "Offboarding"},
        headers=admin,
    )
    body = client.get("/api/v1/operator-events", params={"org_id": str(o.id)}, headers=admin).json()
    assert body["total"] == 2
    assert [r["action"] for r in body["rows"]] == [
        "operator.closure_started",
        "organization.viewed",
    ]
    assert body["rows"][0]["reason"] == "Offboarding" and body["rows"][1]["reason"] is None
