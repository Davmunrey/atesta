"""Organization list and detail (operator-portal spec, "Organization list and detail", "Metadata
fields", acceptance criteria "List", "Detail" and "Never returned"). Real Postgres, read as
atesta_operator; seeds committed as the superuser.
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from . import seed
from .conftest import Issuer, MakeStaff, bearer


@pytest.fixture
def as_role(staff_pool: Issuer, make_staff: MakeStaff) -> Any:
    def headers(role: str) -> dict[str, str]:
        return bearer(staff_pool.token(make_staff(role)))

    return headers


def names(body: dict[str, Any]) -> list[str]:
    return [row["name"] for row in body["rows"]]


def test_search_by_name_or_exact_id(client: TestClient, superuser: Engine, as_role: Any) -> None:
    tag = uuid.uuid4().hex[:8]
    a, b = seed.org(superuser, f"Acme {tag}"), seed.org(superuser, f"Beta {tag}")
    by_name = client.get(
        "/api/v1/organizations", params={"q": f"acme {tag}"}, headers=as_role("support")
    )
    assert by_name.status_code == 200 and names(by_name.json()) == [a.name]
    by_id = client.get("/api/v1/organizations", params={"q": str(b.id)}, headers=as_role("support"))
    assert names(by_id.json()) == [b.name]
    wildcard = client.get("/api/v1/organizations", params={"q": "%"}, headers=as_role("support"))
    assert all("%" in n for n in names(wildcard.json()))  # escaped, not a wildcard


def test_filters_by_state_plan_health_and_billing(
    client: TestClient, superuser: Engine, as_role: Any
) -> None:
    tag = uuid.uuid4().hex[:8]
    plain = seed.org(superuser, f"Plain {tag}")
    suspended = seed.org(
        superuser, f"Paused {tag}", suspended_at=seed.NOW, suspension_reason="non_payment"
    )
    closing = seed.org(superuser, f"Closing {tag}", closure_requested_at=seed.NOW)
    seed.subscription(superuser, suspended, "pro")
    seed.billing(superuser, plain)
    seed.billing(superuser, closing, complete=False)
    seed.connection(superuser, closing, "revoked")
    seed.connection(superuser, plain, "active")

    def listed(**params: str) -> list[str]:
        response = client.get(
            "/api/v1/organizations", params={"q": tag, **params}, headers=as_role("billing")
        )
        assert response.status_code == 200
        return sorted(names(response.json()))

    assert listed(state="suspended") == [suspended.name]
    assert listed(state="closing") == [closing.name]
    assert listed(state="active") == [plain.name]
    assert listed(plan="pro") == [suspended.name]
    assert listed(plan="default") == sorted([plain.name, closing.name])
    assert listed(health="attention") == [closing.name]
    assert listed(billing="missing") == sorted([suspended.name, closing.name])
    assert listed(plan="default", billing="missing") == [closing.name]


def test_rows_carry_the_list_columns(client: TestClient, superuser: Engine, as_role: Any) -> None:
    tag = uuid.uuid4().hex[:8]
    o = seed.org(superuser, f"Columns {tag}")
    seed.add_user(superuser, o, "admin")
    seed.connection(superuser, o, "active")
    seed.subscription(superuser, o, "starter")
    body = client.get("/api/v1/organizations", params={"q": tag}, headers=as_role("support")).json()
    assert body["total"] == 1 and body["page"] == 1 and body["page_size"] == 50
    row = body["rows"][0]
    assert set(row) == {
        "id", "name", "state", "plan", "plan_default", "members", "health", "last_activity",
        "created_at",
    }  # fmt: skip
    assert row["id"] == str(o.id) and row["state"] == "active"
    assert (row["plan"], row["plan_default"], row["members"], row["health"]) == (
        "starter", False, 2, "ok",
    )  # fmt: skip


def test_sorting_and_pages(client: TestClient, superuser: Engine, as_role: Any) -> None:
    tag = uuid.uuid4().hex[:8]
    for i in range(52):
        seed.org(superuser, f"P{i:02d} {tag}")
    first = client.get(
        "/api/v1/organizations", params={"q": tag}, headers=as_role("support")
    ).json()
    second = client.get(
        "/api/v1/organizations", params={"q": tag, "page": 2}, headers=as_role("support")
    ).json()
    assert first["total"] == 52 and len(first["rows"]) == 50 and len(second["rows"]) == 2
    assert names(first)[0].startswith("P00") and names(second)[-1].startswith("P51")
    newest = client.get(
        "/api/v1/organizations", params={"q": tag, "sort": "created"}, headers=as_role("support")
    ).json()
    assert len(newest["rows"]) == 50
    bad = client.get("/api/v1/organizations", params={"sort": "plan"}, headers=as_role("support"))
    assert bad.status_code == 422


def operator_rows(engine: Engine, action: str, org_id: uuid.UUID | None = None) -> list[Any]:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "SELECT staff_role, reason, request_id, metadata, organization_id"
                " FROM operator_audit_events WHERE action = :a"
                " AND (CAST(:o AS uuid) IS NULL OR organization_id = :o) ORDER BY occurred_at"
            ),
            {"a": action, "o": org_id},
        ).all()


def test_a_search_is_in_the_operator_trail_without_its_text(
    client: TestClient, superuser: Engine, as_role: Any
) -> None:
    tag = f"needle-{uuid.uuid4().hex[:8]}"
    client.get("/api/v1/organizations", params={"q": tag}, headers=as_role("support"))
    with superuser.begin() as conn:
        leaked = conn.execute(
            text("SELECT count(*) FROM operator_audit_events WHERE metadata::text LIKE :t"),
            {"t": f"%{tag}%"},
        ).scalar()
    assert leaked == 0
    assert operator_rows(superuser, "organizations.searched")[-1][:2] == ("support", None)


def detail(client: TestClient, as_role: Any, org_id: uuid.UUID, role: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/organizations/{org_id}", headers=as_role(role))
    assert response.status_code == 200, response.json()
    body: dict[str, Any] = response.json()
    return body


@pytest.fixture
def rich(superuser: Engine) -> seed.Org:
    o = seed.org(superuser, "Rich", closure_requested_at=seed.NOW - timedelta(days=2))
    seed.add_user(superuser, o, "admin")
    seed.add_user(superuser, o, "member")
    seed.connection(superuser, o, "active")
    seed.connection(superuser, o, "over_privileged", provider="google_workspace")
    seed.connection(superuser, o, "disconnected")
    seed.scan(superuser, o, "succeeded")
    seed.subscription(superuser, o, "pro", ("trust_center",))
    seed.billing(superuser, o)
    return o


def test_detail_has_every_metadata_field(client: TestClient, as_role: Any, rich: seed.Org) -> None:
    body = detail(client, as_role, rich.id, "admin")
    assert set(body) == {
        "id", "name", "locale", "created_at", "trial_ends_at", "trial_ended", "last_activity",
        "state", "suspended_at", "suspension_reason", "closure", "plan", "billing", "members",
        "pending_invitations", "connections", "scans", "api_keys", "api_calls_30_days", "erasure",
    }  # fmt: skip
    assert body["state"] == "closing" and body["closure"]["origin"] == "operator"
    assert body["plan"] == {
        "plan": "pro", "default": False, "addons": ["trust_center"], "note": "",
        "updated_at": body["plan"]["updated_at"],
    }  # fmt: skip
    assert body["members"] == {"owner": 1, "admin": 1, "member": 1}
    assert body["connections"]["health"] == "attention"
    assert body["connections"]["in_use"] == 2 and body["connections"]["limit"] == 3
    assert body["connections"]["by_provider"]["m365"] == {"active": 1, "disconnected": 1}
    assert body["scans"]["last_30_days"] == {"succeeded": 1}
    assert body["trial_ended"] is False


def test_support_gets_no_tax_id_address_or_billing_email(
    client: TestClient, as_role: Any, rich: seed.Org
) -> None:
    support = detail(client, as_role, rich.id, "support")["billing"]
    assert support == {"view": "summary", "legal_name": f"{rich.name} S.L.", "complete": True}
    for role in ("admin", "billing"):
        full = detail(client, as_role, rich.id, role)["billing"]
        assert full["view"] == "full" and full["tax_id"] == "B12345678"
        assert full["contact_email"] == "facturas@customer.test"


def test_a_detail_view_is_in_the_operator_trail_only(
    client: TestClient, superuser: Engine, as_role: Any, rich: seed.Org
) -> None:
    detail(client, as_role, rich.id, "billing")
    assert operator_rows(superuser, "organization.viewed", rich.id)[-1][:2] == ("billing", None)
    with superuser.begin() as conn:
        seen = conn.execute(
            text("SELECT count(*) FROM audit_events WHERE organization_id = :o"), {"o": rich.id}
        ).scalar()
    assert seen == 0


def test_an_unknown_organization_is_404(client: TestClient, as_role: Any) -> None:
    response = client.get(f"/api/v1/organizations/{uuid.uuid4()}", headers=as_role("support"))
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "operator.not_found"}}


@pytest.mark.parametrize("role", ["admin", "billing", "support"])
def test_no_response_holds_a_person_or_a_connection_identity(
    client: TestClient, as_role: Any, rich: seed.Org, role: str
) -> None:
    """Spec, "Never returned": member names or emails, connection display names or tenants."""
    headers = as_role(role)
    bodies = [
        client.get("/api/v1/organizations", params={"q": rich.name}, headers=headers).text,
        client.get(f"/api/v1/organizations/{rich.id}", headers=headers).text,
    ]
    if role != "support":
        bodies.append(
            client.get(f"/api/v1/organizations/{rich.id}/billing-profile", headers=headers).text
        )
    for body in bodies:
        assert not any(secret.lower() in body.lower() for secret in seed.SECRETS), body
