"""Member endpoints: roles, last-owner invariant under concurrency, audit."""

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from atesta_api.modules.identity import members
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_api.platform.db import make_engine
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from .conftest import APP_PASSWORD, auth, new_sub


def org_with(client: TestClient, superuser: Engine, **roles: str) -> tuple[str, dict[str, str]]:
    """Create an org owned by 'owner' and add the other subs with the given roles."""
    subs = {name: new_sub() for name in ("owner", *roles)}
    org = client.post("/v1/orgs", json={"name": "Org"}, headers=auth(subs["owner"])).json()["id"]
    with superuser.begin() as conn:
        for name, role in roles.items():
            user_id = client.get("/v1/me", headers=auth(subs[name])).json()["id"]
            conn.execute(
                text("INSERT INTO memberships VALUES (:o, :u, :r)"),
                {"o": org, "u": user_id, "r": role},
            )
    return org, subs


def uid(client: TestClient, sub: str) -> str:
    return str(client.get("/v1/me", headers=auth(sub)).json()["id"])


def events(superuser: Engine, org: str, action: str) -> int:
    with superuser.connect() as conn:
        query = text("SELECT count(*) FROM audit_events WHERE organization_id = :o AND action = :a")
        return int(conn.execute(query, {"o": org, "a": action}).scalar_one())


def test_list_members(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, ana="member")
    listed = client.get(f"/v1/orgs/{org}/members", headers=auth(subs["ana"])).json()
    assert sorted(m["role"] for m in listed) == ["member", "owner"]


def test_only_owner_changes_roles(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, adm="admin", mem="member")
    target = uid(client, subs["mem"])
    url = f"/v1/orgs/{org}/members/{target}"
    assert client.patch(url, json={"role": "admin"}, headers=auth(subs["adm"])).status_code == 403
    changed = client.patch(url, json={"role": "admin"}, headers=auth(subs["owner"]))
    assert (changed.status_code, changed.json()["role"]) == (200, "admin")
    assert events(superuser, org, "membership.role_changed") == 1


def test_admin_removes_members_only(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, adm="admin", adm2="admin", mem="member")
    base = f"/v1/orgs/{org}/members"
    assert (
        client.delete(f"{base}/{uid(client, subs['adm2'])}", headers=auth(subs["adm"])).status_code
        == 403
    )
    assert (
        client.delete(f"{base}/{uid(client, subs['mem'])}", headers=auth(subs["adm"])).status_code
        == 204
    )
    assert client.delete(f"{base}/{uuid.uuid4()}", headers=auth(subs["adm"])).status_code == 404
    assert events(superuser, org, "membership.removed") == 1


def test_last_owner_cannot_be_demoted_or_removed(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser)
    url = f"/v1/orgs/{org}/members/{uid(client, subs['owner'])}"
    demote = client.patch(url, json={"role": "member"}, headers=auth(subs["owner"]))
    assert (demote.status_code, demote.json()["detail"]["code"]) == (409, "identity.last_owner")
    assert client.delete(url, headers=auth(subs["owner"])).status_code == 409


def owners(superuser: Engine, org: str) -> set[str]:
    with superuser.connect() as conn:
        query = text(
            "SELECT user_id FROM memberships WHERE organization_id = :o AND role = 'owner'"
        )
        return {str(u) for u in conn.execute(query, {"o": org}).scalars()}


def call(result: dict[str, object], request: Callable[[], Response]) -> threading.Thread:
    """Run one HTTP request in a thread; a server error becomes status 500, not a lost thread."""

    def run() -> None:
        try:
            result["status"] = request().status_code
        except Exception as exc:  # noqa: BLE001  TestClient re-raises server errors
            result["status"], result["error"] = 500, type(exc).__name__

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def held(database: URL, org: str, statement: str, user: str) -> tuple[Engine, Session]:
    """An app-role transaction in the org context that ran one write and holds its row lock."""
    engine = make_engine(
        database.set(username="atesta_app", password=APP_PASSWORD), sslmode="disable"
    )
    tx = Session(engine)
    enter_org_context(tx, uuid.UUID(org), ContextReason.MEMBERSHIP)
    tx.execute(text(statement), {"u": user})
    return engine, tx


def wait_then_commit(thread: threading.Thread, engine: Engine, tx: Session) -> None:
    time.sleep(0.5)
    waited = thread.is_alive()
    tx.commit()  # always release the lock, so a failing check cannot leave the request blocked
    tx.close()
    thread.join(timeout=5)
    engine.dispose()
    assert waited, "the request did not wait for the uncommitted membership write"


def test_admin_cannot_remove_a_member_promoted_to_owner_meanwhile(
    client: TestClient, superuser: Engine, database: URL
) -> None:
    """The target row is locked before the 403 check, so the check sees the promotion."""
    org, subs = org_with(client, superuser, adm="admin", mem="member")
    target = uid(client, subs["mem"])
    engine, tx = held(
        database, org, "UPDATE memberships SET role = 'owner' WHERE user_id = :u", target
    )
    result: dict[str, object] = {}
    thread = call(
        result, lambda: client.delete(f"/v1/orgs/{org}/members/{target}", headers=auth(subs["adm"]))
    )
    wait_then_commit(thread, engine, tx)
    assert result == {"status": 403}
    assert target in owners(superuser, org)
    assert events(superuser, org, "membership.removed") == 0


def test_role_change_of_a_member_removed_meanwhile_is_404(
    client: TestClient, superuser: Engine, database: URL
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    target = uid(client, subs["mem"])
    engine, tx = held(database, org, "DELETE FROM memberships WHERE user_id = :u", target)
    result: dict[str, object] = {}
    thread = call(
        result,
        lambda: client.patch(
            f"/v1/orgs/{org}/members/{target}", json={"role": "admin"}, headers=auth(subs["owner"])
        ),
    )
    wait_then_commit(thread, engine, tx)
    assert result == {"status": 404}
    assert events(superuser, org, "membership.role_changed") == 0


def test_two_owners_demoting_each_other_leave_one_owner(
    client: TestClient, superuser: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Request 1 pauses after its UPDATE with its locks held; request 2 must wait, then 409."""
    org, subs = org_with(client, superuser, co="owner")
    a, b = uid(client, subs["owner"]), uid(client, subs["co"])
    paused, go = threading.Event(), threading.Event()
    original = members.record

    def pause_first(*args: Any, **kwargs: Any) -> None:
        if not paused.is_set():
            paused.set()
            assert go.wait(5)
        original(*args, **kwargs)

    monkeypatch.setattr(members, "record", pause_first)
    first: dict[str, object] = {}
    second: dict[str, object] = {}
    url = f"/v1/orgs/{org}/members"
    t1 = call(
        first,
        lambda: client.patch(f"{url}/{b}", json={"role": "member"}, headers=auth(subs["owner"])),
    )
    assert paused.wait(5)
    t2 = call(
        second,
        lambda: client.patch(f"{url}/{a}", json={"role": "member"}, headers=auth(subs["co"])),
    )
    time.sleep(0.5)
    waited = t2.is_alive()
    go.set()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert waited, "the second demotion did not wait for the first one's locks"
    assert (first, second) == ({"status": 200}, {"status": 409})
    assert owners(superuser, org) == {a}
