"""Connection endpoints: create, list, get, disconnect (scanner-connectors spec, Endpoints)."""

import uuid

import pytest
from atesta_api.modules.connections.api import active_connection_ids, create_connection
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_core.connectors.readonly import GOOGLE_V1, M365_V1
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from .conftest import ORG_A, auth
from .test_members import events, org_with


def create(client: TestClient, org: str, sub: str, **body: str) -> dict[str, object]:
    payload = {"provider": "m365", "display_name": "Contoso M365", **body}
    response = client.post(f"/api/v1/orgs/{org}/connections", json=payload, headers=auth(sub))
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_an_admin_creates_connections_in_their_first_state(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    m365 = create(client, org, subs["adm"])
    google = create(client, org, subs["adm"], provider="google_workspace", display_name="Contoso")
    assert {k: m365[k] for k in ("provider", "status", "allowlist_version")} == {
        "provider": "m365",
        "status": "pending_setup",  # waits for the admin's Microsoft sign-in and consent
        "allowlist_version": "m365-v1",
    }
    assert {k: google[k] for k in ("provider", "status", "allowlist_version")} == {
        "provider": "google_workspace",
        "status": "pending_provisioning",  # waits for its two service accounts
        "allowlist_version": "google-v1",
    }
    assert events(superuser, org, "connection.created") == 2


def test_members_read_but_only_admins_create(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, mem="member")
    url = f"/api/v1/orgs/{org}/connections"
    body = {"provider": "m365", "display_name": "x"}
    denied = client.post(url, json=body, headers=auth(subs["mem"]))
    assert (denied.status_code, denied.json()["detail"]["code"]) == (403, "identity.forbidden")
    made = create(client, org, subs["owner"])
    listed = client.get(url, headers=auth(subs["mem"]))
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [made["id"]]


def test_the_detail_shows_exactly_what_the_customer_grants(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    cases = {
        "m365": {"permissions": sorted(r.name for r in M365_V1.app_roles)},
        "google_workspace": {
            "scan_scopes": sorted(GOOGLE_V1.scan_scopes),
            "verifier_scopes": sorted(GOOGLE_V1.verifier_scopes),
        },
    }
    for provider, expected in cases.items():
        made = create(client, org, subs["owner"], provider=provider)
        url = f"/api/v1/orgs/{org}/connections/{made['id']}"
        detail = client.get(url, headers=auth(subs["owner"]))
        assert detail.status_code == 200
        access = detail.json()["expected_access"]
        assert {k: v for k, v in access.items() if v} == expected


def test_another_orgs_connection_is_not_found(client: TestClient, superuser: Engine) -> None:
    org_a, subs_a = org_with(client, superuser)
    org_b, subs_b = org_with(client, superuser)
    theirs = create(client, org_b, subs_b["owner"])
    for connection_id in (theirs["id"], str(uuid.uuid4())):
        url = f"/api/v1/orgs/{org_a}/connections/{connection_id}"
        response = client.get(url, headers=auth(subs_a["owner"]))
        code = response.json()["detail"]["code"]
        assert (response.status_code, code) == (404, "connections.not_found")
    listed = client.get(f"/api/v1/orgs/{org_a}/connections", headers=auth(subs_a["owner"]))
    assert listed.json() == []


def test_disconnecting_keeps_the_row_and_happens_once(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    made = create(client, org, subs["owner"])
    url = f"/api/v1/orgs/{org}/connections/{made['id']}"
    assert client.delete(url, headers=auth(subs["mem"])).status_code == 403
    gone = client.delete(url, headers=auth(subs["owner"]))
    assert (gone.status_code, gone.json()["status"]) == (200, "disconnected")
    again = client.delete(url, headers=auth(subs["owner"]))
    code = again.json()["detail"]["code"]
    assert (again.status_code, code) == (409, "connections.state_invalid")
    assert client.get(url, headers=auth(subs["owner"])).json()["status"] == "disconnected"
    assert events(superuser, org, "connection.disconnected") == 1


@pytest.mark.parametrize(
    "body",
    [
        {"provider": "aws", "display_name": "x"},
        {"provider": "m365", "display_name": "   "},
        {"provider": "m365", "display_name": "x" * 201},
        {"provider": "m365"},
    ],
)
def test_invalid_input_is_refused(
    client: TestClient, superuser: Engine, body: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    url = f"/api/v1/orgs/{org}/connections"
    response = client.post(url, json=body, headers=auth(subs["owner"]))
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "request.invalid")


def test_active_connection_ids_lists_only_this_orgs_active_connections(
    db_rollback: Session,
) -> None:
    enter_org_context(db_rollback, ORG_A, ContextReason.JOB)
    made = {}
    for status in ("active", "pending_setup", "over_privileged", "disconnected"):
        connection = create_connection(
            db_rollback,
            organization_id=ORG_A,
            provider="m365",
            display_name=status,
            created_by=uuid.uuid4(),
        )
        tenant = str(uuid.uuid4()) if status == "active" else None
        connection.status, connection.external_tenant_id = status, tenant
        made[status] = connection.id
    db_rollback.flush()
    assert active_connection_ids(db_rollback) == [made["active"]]
