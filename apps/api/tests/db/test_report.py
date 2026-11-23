"""Monthly report for management (management-report spec), on real PostgreSQL with RLS."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth
from .test_members import events, org_with
from .test_rbac import _add, _future


def _policy(client: TestClient, org: str, sub: str) -> None:
    policy = client.post(
        f"/api/v1/orgs/{org}/policies",
        json={"title": "Política", "location_url": "https://example.test/p", "review_months": 12},
        headers=auth(sub),
    ).json()
    response = client.post(
        f"/api/v1/orgs/{org}/policies/{policy['id']}/approvals",
        json={"version": "1", "approver_name": "Comité", "approved_on": date.today().isoformat()},
        headers=auth(sub),
    )
    assert response.status_code == 201, response.text


def test_the_report_counts_the_month_and_nothing_else(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    other, other_subs = org_with(client, superuser)
    _policy(client, org, subs["owner"])
    _policy(client, other, other_subs["owner"])
    month = date.today().strftime("%Y-%m")
    auditor = _add(superuser, client, org, "auditor", _future())
    response = client.get(f"/api/v1/orgs/{org}/report?month={month}", headers=auth(auditor))
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["month"] == month
    assert report["done"]["policies_approved"] == 1
    assert report["done"]["access_reviews_closed"] == 0
    assert report["status_is_current"] is True
    assert events(superuser, org, "organization.report_viewed") == 1
    with superuser.begin() as conn:  # an event from last year falls outside the month
        conn.execute(
            text(
                "UPDATE audit_events SET occurred_at = occurred_at - interval '400 days'"
                " WHERE organization_id = :o AND action = 'policy.approved'"
            ),
            {"o": org},
        )
    again = client.get(f"/api/v1/orgs/{org}/report?month={month}", headers=auth(subs["owner"]))
    assert again.json()["done"]["policies_approved"] == 0


def test_a_bad_or_future_month_is_refused(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser)
    for month in ("2026-13", "26-11", "2999-01", "nope"):
        response = client.get(
            f"/api/v1/orgs/{org}/report?month={month}", headers=auth(subs["owner"])
        )
        assert response.status_code == 422, month
    default = client.get(f"/api/v1/orgs/{org}/report", headers=auth(subs["owner"]))
    assert default.json()["month"] == date.today().strftime("%Y-%m")
