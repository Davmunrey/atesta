"""Monthly report for management (management-report spec), on real PostgreSQL with RLS."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from atesta_api.modules.compliance.report import ACTIONS
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth
from .test_members import events, org_with
from .test_overview import overview_catalog as overview_catalog
from .test_rbac import _add, _future
from .test_requirement_register import SCOPE, assessment, base
from .test_requirement_register import pack as pack
from .test_routines_b import _incident
from .test_routines_b import clock_pack as clock_pack

MADRID = ZoneInfo("Europe/Madrid")


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


def _last_month() -> tuple[str, datetime, datetime]:
    """The previous calendar month in Madrid, and its first and following-first midnights."""
    first_this = datetime.now(MADRID).date().replace(day=1)
    first_last = (first_this - timedelta(days=1)).replace(day=1)
    start = datetime(first_last.year, first_last.month, 1, tzinfo=MADRID)
    end = datetime(first_this.year, first_this.month, 1, tzinfo=MADRID)
    return first_last.strftime("%Y-%m"), start, end


def test_every_line_counts_its_actions_within_the_madrid_month(
    client: TestClient, superuser: Engine
) -> None:
    """Half an hour after Madrid midnight on the first is still the previous month in UTC: the
    month is cut in Europe/Madrid. The other times are on the same side in both zones."""
    org, subs = org_with(client, superuser)
    month, start, end = _last_month()
    half, hours = timedelta(minutes=30), timedelta(hours=3)
    inside, outside = (start + half, end - hours), (start - hours, end + hours)
    assert (start + half).astimezone(ZoneInfo("UTC")).month != start.month
    with superuser.begin() as conn:
        for line, actions in ACTIONS.items():
            for action in actions:
                for at in (*inside, *outside):
                    conn.execute(
                        text(
                            "INSERT INTO audit_events (id, organization_id, action, target_type,"
                            " target_id, occurred_at) VALUES (gen_random_uuid(), :o, :a, 't',"
                            " :line, :at)"
                        ),
                        {"o": org, "a": action, "line": line, "at": at},
                    )
    report = client.get(f"/api/v1/orgs/{org}/report?month={month}", headers=auth(subs["owner"]))
    assert report.status_code == 200, report.text
    assert report.json()["done"] == {line: 2 * len(a) for line, a in ACTIONS.items()}


def test_recording_an_incident_counts_and_its_clocks_fall_due(
    client: TestClient, superuser: Engine, clock_pack: str
) -> None:
    org, subs = org_with(client, superuser)
    _incident(client, org, subs["owner"], 1, significant=True, personal_data=True)
    headers = auth(subs["owner"])
    report = client.get(f"/api/v1/orgs/{org}/report", headers=headers).json()
    assert report["done"]["incidents_recorded"] == 1
    due = client.get(f"/api/v1/orgs/{org}/routines/due", headers=headers).json()
    assert any(d.get("clock") for d in due) and report["due"] == due


def test_the_status_lists_each_framework_in_progress_as_it_is_now(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = org_with(client, superuser)
    owner = auth(subs["owner"])
    before = client.get(f"/api/v1/orgs/{org}/report", headers=owner).json()
    assert pack not in {f["key"] for f in before["frameworks"]}
    client.post(base(org, pack) + "/scope", json={"axis_values": SCOPE}, headers=owner)
    response = client.post(base(org, pack) + "/register/m.cat", json=assessment(), headers=owner)
    assert response.status_code == 201, response.text
    report = client.get(f"/api/v1/orgs/{org}/report", headers=owner).json()
    status = {f["key"]: f for f in report["frameworks"]}[pack]
    assert (status["assessed"], status["implemented"], status["scope_defined"]) == (1, 1, True)
    assert report["status_is_current"] is True
