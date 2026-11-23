"""Recorded routines, part A (recorded-routines spec), on real PostgreSQL with RLS."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth
from .test_members import events, org_with
from .test_rbac import _add, _future


def _review(client: TestClient, org: str, sub: str, **over: object) -> dict:  # type: ignore[type-arg]  # JSON body
    body = {
        "title": "Q4",
        "system": "Microsoft 365",
        "accounts": [
            {"account": "ana@example.com", "detail": "Global admin"},
            {"account": "luis@example.com"},
        ],
        **over,
    }
    response = client.post(f"/api/v1/orgs/{org}/access-reviews", json=body, headers=auth(sub))
    assert response.status_code == 201, response.text
    return response.json()


def _statements(superuser: Engine, org: str, control: str) -> list[str]:
    with superuser.begin() as conn:
        return list(
            conn.scalars(
                text(
                    "SELECT s.statement FROM evidence_statements s JOIN evidence e"
                    " ON e.organization_id = s.organization_id"
                    " AND e.id = s.evidence_id WHERE s.organization_id = :o ORDER BY e.collected_at"
                ),
                {"o": org},
            )
        )


def test_an_access_review_is_decided_closed_and_leaves_evidence(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, ana="member")
    review = _review(client, org, subs["owner"])
    assert (review["total"], review["pending"]) == (2, 2)
    url = f"/api/v1/orgs/{org}/access-reviews/{review['id']}"
    first, second = review["entries"]
    assert (
        client.post(url + "/close", headers=auth(subs["owner"])).json()["detail"]["code"]
        == "compliance.access_review_pending"
    )
    for entry, decision in (
        (first, "revoke"),
        (first, "keep"),
        (second, "revoke"),
    ):  # latest decision wins
        response = client.post(
            url + "/decisions",
            json={"entry_id": entry["id"], "decision": decision},
            headers=auth(subs["ana"]),
        )
        assert response.status_code == 201, response.text
    assert client.post(url + "/close", headers=auth(subs["ana"])).status_code == 403  # admins close
    closed = client.post(url + "/close", headers=auth(subs["owner"]))
    assert closed.status_code == 200, closed.text
    assert (closed.json()["keep"], closed.json()["revoke"], closed.json()["pending"]) == (1, 1, 0)
    assert closed.json()["closed_at"]
    again = client.post(
        url + "/decisions",
        json={"entry_id": first["id"], "decision": "revoke"},
        headers=auth(subs["owner"]),
    )
    assert (
        again.status_code == 409
        and again.json()["detail"]["code"] == "compliance.access_review_closed"
    )
    statements = _statements(superuser, org, "ctl.access_review")
    assert len(statements) == 1
    assert (
        "Revisión de accesos «Q4» (Microsoft 365). Cuentas revisadas: 2; mantener: 1; retirar: 1."
        in statements[0]
    )
    assert events(superuser, org, "access_review.closed") == 1


def test_access_reviews_check_roles_and_input(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, ana="member")
    body = {"title": "Q4", "system": "M365", "accounts": [{"account": "a"}]}
    assert (
        client.post(
            f"/api/v1/orgs/{org}/access-reviews", json=body, headers=auth(subs["ana"])
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/orgs/{org}/access-reviews",
            json={**body, "accounts": []},
            headers=auth(subs["owner"]),
        ).status_code
        == 422
    )
    for blank in ({"title": "   "}, {"accounts": [{"account": " \t "}]}):
        response = client.post(
            f"/api/v1/orgs/{org}/access-reviews",
            json={**body, **blank},
            headers=auth(subs["owner"]),
        )
        assert response.status_code == 422  # never a database check error
    review = _review(client, org, subs["owner"])
    auditor = _add(superuser, client, org, "auditor", _future())
    assert (
        client.get(
            f"/api/v1/orgs/{org}/access-reviews/{review['id']}", headers=auth(auditor)
        ).status_code
        == 200
    )
    decision = {"entry_id": review["entries"][0]["id"], "decision": "keep"}
    assert (
        client.post(
            f"/api/v1/orgs/{org}/access-reviews/{review['id']}/decisions",
            json=decision,
            headers=auth(auditor),
        ).status_code
        == 403
    )


def test_another_organization_never_sees_or_decides_a_review(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    other, other_subs = org_with(client, superuser)
    review = _review(client, org, subs["owner"])
    assert (
        client.get(
            f"/api/v1/orgs/{other}/access-reviews/{review['id']}", headers=auth(other_subs["owner"])
        ).status_code
        == 404
    )
    decision = {"entry_id": review["entries"][0]["id"], "decision": "keep"}
    assert (
        client.post(
            f"/api/v1/orgs/{other}/access-reviews/{review['id']}/decisions",
            json=decision,
            headers=auth(other_subs["owner"]),
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/orgs/{other}/access-reviews", headers=auth(other_subs["owner"])).json()
        == []
    )


def test_a_policy_is_approved_with_its_hash_and_falls_due(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, ana="member")
    owner = auth(subs["owner"])
    body = {
        "title": "Política de seguridad",
        "location_url": "https://example.sharepoint.com/pol.pdf",
        "review_months": 12,
    }
    assert (
        client.post(
            f"/api/v1/orgs/{org}/policies", json=body, headers=auth(subs["ana"])
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/orgs/{org}/policies",
            json={**body, "location_url": "http://insecure"},
            headers=owner,
        ).status_code
        == 422
    )
    policy = client.post(f"/api/v1/orgs/{org}/policies", json=body, headers=owner).json()
    due = client.get(f"/api/v1/orgs/{org}/routines/due", headers=owner).json()
    assert [(d["kind"], d["title"]) for d in due] == [
        ("policy_unapproved", "Política de seguridad")
    ]
    long_ago = (date.today() - timedelta(days=400)).isoformat()
    approval = {
        "version": "1.0",
        "approver_name": "Comité de seguridad",
        "approved_on": long_ago,
        "sha256": "a" * 64,
    }
    approved = client.post(
        f"/api/v1/orgs/{org}/policies/{policy['id']}/approvals", json=approval, headers=owner
    )
    assert approved.status_code == 201, approved.text
    assert approved.json()["latest"]["version"] == "1.0"
    due = client.get(f"/api/v1/orgs/{org}/routines/due", headers=owner).json()
    assert [(d["kind"], d["overdue"]) for d in due] == [("policy_review", True)]
    fresh = {**approval, "version": "1.1", "approved_on": date.today().isoformat(), "sha256": None}
    client.post(f"/api/v1/orgs/{org}/policies/{policy['id']}/approvals", json=fresh, headers=owner)
    assert client.get(f"/api/v1/orgs/{org}/routines/due", headers=owner).json() == []
    statements = _statements(superuser, org, "ctl.security_governance")
    assert "versión 1.0, aprobada por Comité de seguridad" in statements[0]
    assert "Huella SHA-256 del documento: " + "a" * 64 in statements[0]


def test_an_open_review_past_its_date_falls_due(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser)
    review = _review(
        client, org, subs["owner"], due_on=(date.today() - timedelta(days=1)).isoformat()
    )
    due = client.get(f"/api/v1/orgs/{org}/routines/due", headers=auth(subs["owner"])).json()
    assert [(d["kind"], d["id"]) for d in due] == [("access_review_overdue", review["id"])]


@pytest.mark.parametrize(
    "table", ["access_review_entries", "access_review_decisions", "policies", "policy_approvals"]
)
def test_routine_records_are_append_only(superuser: Engine, table: str) -> None:
    with superuser.begin() as conn:
        grants = set(
            conn.scalars(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants"
                    " WHERE grantee = 'atesta_app' AND table_name = :t"
                ),
                {"t": table},
            )
        )
    assert grants == {"SELECT", "INSERT"}


def test_a_policy_link_that_is_itself_a_credential_is_refused(
    client: TestClient, superuser: Engine
) -> None:
    """Its approval copies the link into append-only evidence (rule 2, #256)."""
    org, subs = org_with(client, superuser)
    body = {
        "title": "Política",
        "location_url": "https://acct.blob.core.windows.net/c/pol.pdf?sv=2024-01-01&sig=abc",
        "review_months": 12,
    }
    result = client.post(f"/api/v1/orgs/{org}/policies", json=body, headers=auth(subs["owner"]))
    assert result.status_code == 422
