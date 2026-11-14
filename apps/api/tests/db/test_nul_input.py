"""Text PostgreSQL cannot store is a client error (422), never a server error (500)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from .conftest import auth, new_sub
from .test_members import org_with


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/orgs", {"name": "Org\u0000"}),
        ("/api/v1/orgs/{org}/invitations", {"email": "ana\u0000@example.com", "role": "member"}),
        ("/api/v1/orgs/{org}/connections", {"provider": "m365", "display_name": "Tenant\u0000"}),
    ],
    ids=["organization name", "invitation email", "connection name"],
)
def test_a_nul_character_is_rejected_as_invalid_input(
    client: TestClient, superuser: Engine, path: str, body: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    response = client.post(path.format(org=org), json=body, headers=auth(subs["owner"]))
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "request.invalid"


def test_nothing_is_written_when_the_input_is_refused(client: TestClient) -> None:
    sub = new_sub()
    client.post("/api/v1/orgs", json={"name": "Org\u0000"}, headers=auth(sub))
    assert client.get("/api/v1/me", headers=auth(sub)).json()["memberships"] == []
