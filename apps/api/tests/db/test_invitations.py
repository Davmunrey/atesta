"""Invitations end to end with RLS (identity-auth spec test plan "Invitations")."""

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import FakeProvider, auth, new_sub
from .test_members import events, org_with, uid


def invite(
    client: TestClient, org: str, by: str, email: str, role: str = "member"
) -> dict[str, str]:
    response = client.post(
        f"/api/v1/orgs/{org}/invitations", json={"email": email, "role": role}, headers=auth(by)
    )
    assert response.status_code == 201, response.text
    body: dict[str, str] = response.json()
    return body


def token_of(link: str) -> str:
    parts = urlsplit(link)
    assert (parts.query, parts.fragment[:6]) == ("", "token=")
    return parts.fragment.removeprefix("token=")


def accept(client: TestClient, sub: str, token: str) -> tuple[int, str]:
    response = client.post("/api/v1/invitations/accept", json={"token": token}, headers=auth(sub))
    body = response.json()
    return response.status_code, body.get("role") or body["detail"]["code"]


def test_happy_path_raw_token_never_stored(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser)
    guest = new_sub()
    created = invite(client, org, subs["owner"], f"  {guest.upper()}@Example.com ")
    token = token_of(created["accept_link"])
    with superuser.connect() as conn:
        stored = conn.execute(text("SELECT token_sha256 FROM invitations")).scalars().all()
    assert token not in stored and all(len(s) == 64 for s in stored)
    assert accept(client, guest, token) == (200, "member")
    assert accept(client, guest, token) == (410, "identity.invitation_invalid")
    assert (
        events(superuser, org, "invitation.created")
        == events(superuser, org, "invitation.accepted")
        == 1
    )


def test_role_cap_and_permissions(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, adm="admin", mem="member")
    body = {"email": "x@example.com", "role": "owner"}
    url = f"/api/v1/orgs/{org}/invitations"
    assert client.post(url, json=body, headers=auth(subs["adm"])).status_code == 403
    assert client.post(url, json=body, headers=auth(subs["owner"])).status_code == 201
    assert (
        client.post(url, json={**body, "role": "member"}, headers=auth(subs["mem"])).status_code
        == 403
    )


def test_rejections(client: TestClient, superuser: Engine, provider: FakeProvider) -> None:
    org, subs = org_with(client, superuser)
    guest, other, unverified = new_sub(), new_sub(), new_sub()
    provider.unverified.add(unverified)
    token = token_of(invite(client, org, subs["owner"], f"{guest}@example.com")["accept_link"])
    assert accept(client, other, token) == (403, "identity.email_mismatch")
    provider.emails[unverified] = f"{guest}@example.com"
    assert accept(client, unverified, token) == (403, "identity.email_unverified")
    assert accept(client, guest, "x" * 43) == (404, "identity.invitation_invalid")
    query = client.post(
        "/api/v1/invitations/accept?token=t", json={"token": token}, headers=auth(guest)
    )
    assert (query.status_code, query.json()["detail"]["code"]) == (400, "identity.token_in_query")
    with superuser.begin() as conn:
        conn.execute(
            text(
                "UPDATE invitations SET expires_at = now() - interval '1 second' WHERE email = :e"
            ),
            {"e": f"{guest}@example.com"},
        )
    assert accept(client, guest, token) == (410, "identity.invitation_invalid")


def test_revoked_and_removed_inviter(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    g1, g2 = new_sub(), new_sub()
    first = invite(client, org, subs["adm"], f"{g1}@example.com")
    second = invite(client, org, subs["adm"], f"{g2}@example.com")
    revoke = client.delete(
        f"/api/v1/orgs/{org}/invitations/{first['id']}", headers=auth(subs["owner"])
    )
    assert revoke.status_code == 204
    assert accept(client, g1, token_of(first["accept_link"])) == (
        410,
        "identity.invitation_invalid",
    )
    remove = client.delete(
        f"/api/v1/orgs/{org}/members/{uid(client, subs['adm'])}", headers=auth(subs["owner"])
    )
    assert remove.status_code == 204
    assert accept(client, g2, token_of(second["accept_link"])) == (
        410,
        "identity.invitation_invalid",
    )
    assert (
        client.get(f"/api/v1/orgs/{org}/invitations", headers=auth(subs["owner"])).json()[0]["id"]
        == second["id"]
    )


@pytest.mark.parametrize("role", ["owner", "member"])
def test_existing_member_gets_409_and_keeps_role(
    client: TestClient, superuser: Engine, role: str
) -> None:
    org, subs = org_with(client, superuser)
    me = client.get("/api/v1/me", headers=auth(subs["owner"])).json()["email"]
    token = token_of(invite(client, org, subs["owner"], me, role)["accept_link"])
    assert accept(client, subs["owner"], token) == (409, "identity.already_member")
    roles = [
        m["role"]
        for m in client.get("/api/v1/me", headers=auth(subs["owner"])).json()["memberships"]
    ]
    assert roles == ["owner"]
    pending = client.get(f"/api/v1/orgs/{org}/invitations", headers=auth(subs["owner"])).json()
    assert len(pending) == 1
