"""Scan endpoints (scanner-connectors spec, Endpoints): scan now, scans, findings."""

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth
from .test_connections_http import create
from .test_members import events, org_with


def active(superuser: Engine, connection_id: object) -> None:
    """Verification is not built yet (PR 9): the test sets the state it would reach."""
    with superuser.begin() as conn:
        conn.execute(
            text(
                "UPDATE connections SET status = 'active',"
                " external_tenant_id = gen_random_uuid()::text WHERE id = :id"
            ),
            {"id": connection_id},
        )


def scan_now(client: TestClient, org: str, sub: str, connection_id: object) -> tuple[int, dict]:
    url = f"/api/v1/orgs/{org}/connections/{connection_id}/scans"
    response = client.post(url, headers=auth(sub))
    return response.status_code, response.json()


def code(body: dict) -> str:
    return str(body["detail"]["code"])


def test_an_admin_scans_an_active_connection_now_once_at_a_time(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    made = create(client, org, subs["adm"])
    active(superuser, made["id"])
    status, scan = scan_now(client, org, subs["adm"], made["id"])
    assert status == 202
    assert {k: scan[k] for k in ("connection_id", "provider", "trigger", "status")} == {
        "connection_id": made["id"],
        "provider": "m365",
        "trigger": "user",
        "status": "queued",
    }
    again, body = scan_now(client, org, subs["owner"], made["id"])
    assert (again, code(body)) == (409, "scanning.already_queued")
    assert events(superuser, org, "scan.requested") == 1


def test_members_read_scans_but_never_start_one(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, mem="member")
    made = create(client, org, subs["owner"])
    active(superuser, made["id"])
    status, body = scan_now(client, org, subs["mem"], made["id"])
    assert (status, code(body)) == (403, "identity.forbidden")
    _, scan = scan_now(client, org, subs["owner"], made["id"])
    listed = client.get(f"/api/v1/orgs/{org}/scans", headers=auth(subs["mem"]))
    assert listed.status_code == 200
    assert [s["id"] for s in listed.json()["items"]] == [scan["id"]]
    detail = client.get(f"/api/v1/orgs/{org}/scans/{scan['id']}", headers=auth(subs["mem"]))
    assert (detail.status_code, detail.json()["status"]) == (200, "queued")


def test_a_connection_that_is_not_active_is_not_scanned(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    made = create(client, org, subs["owner"])  # pending_setup
    status, body = scan_now(client, org, subs["owner"], made["id"])
    assert (status, code(body)) == (409, "scanning.connection_not_active")
    assert events(superuser, org, "scan.requested") == 0


def test_another_orgs_connection_and_scans_are_not_found(
    client: TestClient, superuser: Engine
) -> None:
    org_a, subs_a = org_with(client, superuser)
    org_b, subs_b = org_with(client, superuser)
    theirs = create(client, org_b, subs_b["owner"])
    active(superuser, theirs["id"])
    _, their_scan = scan_now(client, org_b, subs_b["owner"], theirs["id"])
    for connection_id in (theirs["id"], uuid.uuid4()):
        status, body = scan_now(client, org_a, subs_a["owner"], connection_id)
        assert (status, code(body)) == (404, "connections.not_found")
    for path in (their_scan["id"], f"{their_scan['id']}/findings", uuid.uuid4()):
        response = client.get(f"/api/v1/orgs/{org_a}/scans/{path}", headers=auth(subs_a["owner"]))
        assert (response.status_code, code(response.json())) == (404, "scanning.not_found")
    listed = client.get(f"/api/v1/orgs/{org_a}/scans", headers=auth(subs_a["owner"]))
    assert listed.json()["items"] == []


SCAN = text(
    "INSERT INTO scans (id, organization_id, connection_id, provider, trigger, status, engine,"
    " engine_version, queued_at) VALUES (:id, :org, :conn, 'm365', 'schedule', 'succeeded',"
    " 'prowler', '5.52.0', now() - make_interval(mins => :age))"
)
FINDING = text(
    "INSERT INTO findings (id, organization_id, scan_id, engine, check_id, status, severity,"
    " service, resource_type, resource_uid, resource_name, region, message) VALUES"
    " (gen_random_uuid(), :org, :scan, 'prowler', :check, :status, 'high', 'entra', 'User', :uid,"
    " 'Ana', 'global', 'MFA off')"
)


def seed(superuser: Engine, org: str, scans: int, findings: int) -> list[str]:
    """Scans of one connection, oldest first; the newest one has the findings."""
    ids = [str(uuid.uuid4()) for _ in range(scans)]
    conn_id = str(uuid.uuid4())
    with superuser.begin() as conn:
        for age, scan_id in zip(range(scans, 0, -1), ids, strict=True):
            conn.execute(SCAN, {"id": scan_id, "org": org, "conn": conn_id, "age": age})
        for n in range(findings):
            row = {"org": org, "scan": ids[-1], "check": f"check_{n % 3}", "uid": f"u{n:02d}"}
            conn.execute(FINDING, {**row, "status": "fail" if n % 2 else "pass"})
    return ids


def test_scans_are_listed_newest_first_and_filtered_by_connection(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    ids = seed(superuser, org, scans=3, findings=0)
    url = f"/api/v1/orgs/{org}/scans"
    page = client.get(url, params={"limit": 2}, headers=auth(subs["owner"])).json()
    assert ([s["id"] for s in page["items"]], page["total"]) == ([ids[2], ids[1]], 3)
    rest = client.get(url, params={"limit": 2, "offset": 2}, headers=auth(subs["owner"])).json()
    assert [s["id"] for s in rest["items"]] == [ids[0]]
    elsewhere = {"connection_id": str(uuid.uuid4())}
    other = client.get(url, params=elsewhere, headers=auth(subs["owner"]))
    assert other.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_findings_are_paged_in_a_stable_order(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, mem="member")
    scan_id = seed(superuser, org, scans=1, findings=5)[0]
    url = f"/api/v1/orgs/{org}/scans/{scan_id}/findings"
    first = client.get(url, params={"limit": 2}, headers=auth(subs["mem"])).json()
    second = client.get(url, params={"limit": 2, "offset": 2}, headers=auth(subs["mem"])).json()
    third = client.get(url, params={"limit": 2, "offset": 4}, headers=auth(subs["mem"])).json()
    pages = [first, second, third]
    seen = [(f["check_id"], f["resource_uid"]) for p in pages for f in p["items"]]
    assert seen == sorted(seen) and len(set(seen)) == 5
    assert {p["total"] for p in pages} == {5}
    failed = client.get(url, params={"status": "fail"}, headers=auth(subs["mem"])).json()
    assert (failed["total"], {f["status"] for f in failed["items"]}) == (2, {"fail"})
    assert set(first["items"][0]) == {
        "id",
        "check_id",
        "status",
        "muted",
        "severity",
        "service",
        "resource_type",
        "resource_uid",
        "resource_name",
        "region",
        "message",
        "created_at",
    }


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "passed"}]
)
def test_invalid_paging_is_refused(
    client: TestClient, superuser: Engine, params: dict[str, object]
) -> None:
    org, subs = org_with(client, superuser)
    scan_id = seed(superuser, org, scans=1, findings=0)[0]
    url = f"/api/v1/orgs/{org}/scans/{scan_id}/findings"
    response = client.get(url, params=params, headers=auth(subs["owner"]))
    assert (response.status_code, code(response.json())) == (422, "request.invalid")


def test_the_seventh_manual_scan_of_the_day_says_when_to_retry(
    client: TestClient, superuser: Engine
) -> None:
    """#265: 429 with a stable code, the next Madrid midnight and Retry-After; nothing written."""
    org, subs = org_with(client, superuser)
    made = create(client, org, subs["owner"])
    active(superuser, made["id"])
    with superuser.begin() as conn:
        for _ in range(6):
            conn.execute(
                text(
                    "INSERT INTO scans (id, organization_id, connection_id, provider, trigger,"
                    " status, engine, engine_version, finished_at) VALUES (gen_random_uuid(),"
                    " :o, :c, 'm365', 'user', 'failed', 'prowler', '5.49.0', now())"
                ),
                {"o": org, "c": made["id"]},
            )
        midnight = conn.execute(
            text(
                "SELECT (date_trunc('day', now() AT TIME ZONE 'Europe/Madrid') + interval '1 day')"
                " AT TIME ZONE 'Europe/Madrid'"
            )
        ).scalar_one()
    url = f"/api/v1/orgs/{org}/connections/{made['id']}/scans"
    response = client.post(url, headers=auth(subs["owner"]))
    assert response.status_code == 429
    body = response.json()
    assert code(body) == "scanning.daily_limit"
    assert datetime.fromisoformat(body["detail"]["retry_at"]) == midnight
    assert 0 < int(response.headers["Retry-After"]) <= 25 * 3600
    assert events(superuser, org, "scan.requested") == 0
