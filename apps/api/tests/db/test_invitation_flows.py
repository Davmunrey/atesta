"""Invitation test-plan rows the first suite left open (identity-auth spec, Invitations, Audit,
Logs): demoted inviter, revoke vs accept, current email at accept, the token in audit rows and
logs, and every audit event's actor."""

import logging
import threading
import time
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import FakeProvider, auth, new_sub
from .test_invitations import accept, invite, token_of
from .test_members import org_with, uid


def outcomes(superuser: Engine, invitation_id: str) -> tuple[bool, bool]:
    """(accepted, revoked) as stored."""
    with superuser.connect() as conn:
        row = conn.execute(
            text(
                "SELECT accepted_at IS NOT NULL, revoked_at IS NOT NULL FROM invitations"
                " WHERE id = :i"
            ),
            {"i": invitation_id},
        ).one()
    return bool(row[0]), bool(row[1])


def revoke(client: TestClient, org: str, by: str, invitation_id: str) -> int:
    url = f"/v1/orgs/{org}/invitations/{invitation_id}"
    return client.delete(url, headers=auth(by)).status_code


def test_invitation_from_a_demoted_inviter_is_rejected(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    guest = new_sub()
    created = invite(client, org, subs["adm"], f"{guest}@example.com", role="admin")
    demote = client.patch(
        f"/v1/orgs/{org}/members/{uid(client, subs['adm'])}",
        json={"role": "member"},
        headers=auth(subs["owner"]),
    )
    assert demote.status_code == 200
    assert accept(client, guest, token_of(created["accept_link"])) == (
        410,
        "identity.invitation_invalid",
    )


def test_revoke_after_accept_is_404_and_accept_after_revoke_is_410(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    g1, g2 = new_sub(), new_sub()
    first = invite(client, org, subs["owner"], f"{g1}@example.com")
    assert accept(client, g1, token_of(first["accept_link"])) == (200, "member")
    assert revoke(client, org, subs["owner"], first["id"]) == 404
    assert outcomes(superuser, first["id"]) == (True, False)
    second = invite(client, org, subs["owner"], f"{g2}@example.com")
    assert revoke(client, org, subs["owner"], second["id"]) == 204
    assert accept(client, g2, token_of(second["accept_link"])) == (
        410,
        "identity.invitation_invalid",
    )
    assert outcomes(superuser, second["id"]) == (False, True)


def _race(superuser: Engine, held: str, invitation_id: str, request: Callable[[], int]) -> int:
    """Hold one outcome uncommitted, run the other through the API, commit, return its status."""
    result: list[int] = []
    with superuser.connect() as conn:
        tx = conn.begin()
        conn.execute(text(held), {"i": invitation_id})
        thread = threading.Thread(target=lambda: result.append(request()))
        thread.start()
        time.sleep(0.7)
        waited = thread.is_alive()
        tx.commit()
    thread.join(timeout=5)
    assert waited, "the request did not wait on the invitation row"
    return result[0]


def test_revoke_committing_while_accept_waits_leaves_one_outcome(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    guest = new_sub()
    client.get("/v1/me", headers=auth(guest))  # provisioned, so accept reaches the claim fast
    created = invite(client, org, subs["owner"], f"{guest}@example.com")
    token = token_of(created["accept_link"])
    status = _race(
        superuser,
        "UPDATE invitations SET revoked_at = now() WHERE id = :i"
        " AND accepted_at IS NULL AND revoked_at IS NULL",
        created["id"],
        lambda: (
            client.post(
                "/v1/invitations/accept", json={"token": token}, headers=auth(guest)
            ).status_code
        ),
    )
    assert status == 410
    assert outcomes(superuser, created["id"]) == (False, True)


def test_accept_committing_while_revoke_waits_leaves_one_outcome(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    created = invite(client, org, subs["owner"], f"{new_sub()}@example.com")
    status = _race(
        superuser,
        "UPDATE invitations SET accepted_at = now() WHERE id = :i"
        " AND accepted_at IS NULL AND revoked_at IS NULL",
        created["id"],
        lambda: revoke(client, org, subs["owner"], created["id"]),
    )
    assert status == 404
    assert outcomes(superuser, created["id"]) == (True, False)


def test_accept_decides_on_the_current_email_and_verification(
    client: TestClient, superuser: Engine, provider: FakeProvider
) -> None:
    """Provisioned with the invited, verified address; Cognito changes it before accept."""
    org, subs = org_with(client, superuser)
    moved, unverified = new_sub(), new_sub()
    tokens = {}
    for guest in (moved, unverified):
        address = f"{guest}@example.com"
        assert client.get("/v1/me", headers=auth(guest)).json()["email"] == address
        tokens[guest] = token_of(invite(client, org, subs["owner"], address)["accept_link"])
    provider.emails[moved] = "elsewhere@example.com"
    provider.unverified.add(unverified)
    assert accept(client, moved, tokens[moved]) == (403, "identity.email_mismatch")
    assert accept(client, unverified, tokens[unverified]) == (403, "identity.email_unverified")


def test_token_never_reaches_audit_rows_or_logs(
    client: TestClient, superuser: Engine, provider: FakeProvider, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    org, subs = org_with(client, superuser)
    guest, stranger = new_sub(), new_sub()
    token = token_of(invite(client, org, subs["owner"], f"{guest}@example.com")["accept_link"])
    assert accept(client, stranger, token) == (403, "identity.email_mismatch")  # failure path
    assert accept(client, guest, token) == (200, "member")
    assert accept(client, guest, token) == (410, "identity.invitation_invalid")
    with superuser.connect() as conn:
        rows = (
            conn.execute(
                text("SELECT row_to_json(a)::text FROM audit_events a WHERE organization_id = :o"),
                {"o": org},
            )
            .scalars()
            .all()
        )
    assert rows
    assert not any(token in row for row in rows)
    assert token not in caplog.text
    assert f"tok-{guest}" not in caplog.text


def test_every_action_writes_one_event_with_its_actor_and_target(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    owner, adm = uid(client, subs["owner"]), uid(client, subs["adm"])
    guest = new_sub()
    dropped = invite(client, org, subs["adm"], f"{new_sub()}@example.com")
    kept = invite(client, org, subs["adm"], f"{guest}@example.com")
    assert revoke(client, org, subs["owner"], dropped["id"]) == 204
    assert accept(client, guest, token_of(kept["accept_link"])) == (200, "member")
    guest_id = uid(client, guest)
    member_url = f"/v1/orgs/{org}/members/{guest_id}"
    assert (
        client.patch(member_url, json={"role": "admin"}, headers=auth(subs["owner"])).status_code
        == 200
    )
    assert (
        client.patch(member_url, json={"role": "member"}, headers=auth(subs["owner"])).status_code
        == 200
    )
    assert client.delete(member_url, headers=auth(subs["adm"])).status_code == 204
    with superuser.connect() as conn:
        events = conn.execute(
            text(
                "SELECT action, actor_user_id::text, target_id FROM audit_events"
                " WHERE organization_id = :o ORDER BY occurred_at, action"
            ),
            {"o": org},
        ).all()
    by_action: dict[str, list[tuple[str, str]]] = {}
    for action, actor, target in events:
        by_action.setdefault(action, []).append((actor, target))
    assert by_action == {
        "org.created": [(owner, org)],
        "invitation.created": [(adm, dropped["id"]), (adm, kept["id"])],
        "invitation.revoked": [(owner, dropped["id"])],
        "invitation.accepted": [(guest_id, kept["id"])],
        "membership.role_changed": [(owner, guest_id), (owner, guest_id)],
        "membership.removed": [(adm, guest_id)],
    }
    uuid.UUID(org)  # targets are ids, not emails or tokens
