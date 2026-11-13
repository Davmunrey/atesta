"""Member endpoints: roles, last-owner invariant under concurrency, audit."""

import threading
import time
import uuid

from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_api.modules.identity.members import _keep_an_owner
from atesta_api.platform.db import make_engine
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from .conftest import APP_PASSWORD, auth, new_sub


def org_with(client: TestClient, superuser: Engine, **roles: str) -> tuple[str, dict[str, str]]:
    """Create an org owned by 'owner' and add the other subs with the given roles."""
    subs = {name: new_sub() for name in ("owner", *roles)}
    org = client.post("/api/v1/orgs", json={"name": "Org"}, headers=auth(subs["owner"])).json()[
        "id"
    ]
    with superuser.begin() as conn:
        for name, role in roles.items():
            user_id = client.get("/api/v1/me", headers=auth(subs[name])).json()["id"]
            conn.execute(
                text("INSERT INTO memberships VALUES (:o, :u, :r)"),
                {"o": org, "u": user_id, "r": role},
            )
    return org, subs


def uid(client: TestClient, sub: str) -> str:
    return str(client.get("/api/v1/me", headers=auth(sub)).json()["id"])


def events(superuser: Engine, org: str, action: str) -> int:
    with superuser.connect() as conn:
        query = text("SELECT count(*) FROM audit_events WHERE organization_id = :o AND action = :a")
        return int(conn.execute(query, {"o": org, "a": action}).scalar_one())


def test_list_members(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, ana="member")
    listed = client.get(f"/api/v1/orgs/{org}/members", headers=auth(subs["ana"])).json()
    assert sorted(m["role"] for m in listed) == ["member", "owner"]


def test_only_owner_changes_roles(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, adm="admin", mem="member")
    target = uid(client, subs["mem"])
    url = f"/api/v1/orgs/{org}/members/{target}"
    assert client.patch(url, json={"role": "admin"}, headers=auth(subs["adm"])).status_code == 403
    changed = client.patch(url, json={"role": "admin"}, headers=auth(subs["owner"]))
    assert (changed.status_code, changed.json()["role"]) == (200, "admin")
    assert events(superuser, org, "membership.role_changed") == 1


def test_admin_removes_members_only(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, adm="admin", adm2="admin", mem="member")
    base = f"/api/v1/orgs/{org}/members"
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
    url = f"/api/v1/orgs/{org}/members/{uid(client, subs['owner'])}"
    demote = client.patch(url, json={"role": "member"}, headers=auth(subs["owner"]))
    assert (demote.status_code, demote.json()["detail"]["code"]) == (409, "identity.last_owner")
    assert client.delete(url, headers=auth(subs["owner"])).status_code == 409


def test_owner_lock_makes_the_second_demotion_wait_and_fail(
    client: TestClient, superuser: Engine, database: URL
) -> None:
    """Deterministic race: tx 1 holds the owner lock uncommitted; tx 2 must block, then 409."""
    org_s, subs = org_with(client, superuser, co="owner")
    org, a, b = (
        uuid.UUID(org_s),
        uuid.UUID(uid(client, subs["owner"])),
        uuid.UUID(uid(client, subs["co"])),
    )
    engine = make_engine(
        database.set(username="atesta_app", password=APP_PASSWORD), sslmode="disable"
    )
    outcome: dict[str, int] = {}

    def second() -> None:
        with Session(engine) as tx2:
            enter_org_context(tx2, org, ContextReason.MEMBERSHIP)
            try:
                _keep_an_owner(tx2, org, b)
                outcome["status"] = 200
            except HTTPException as exc:
                outcome["status"] = exc.status_code

    with Session(engine) as tx1:
        enter_org_context(tx1, org, ContextReason.MEMBERSHIP)
        _keep_an_owner(tx1, org, a)
        tx1.execute(text("UPDATE memberships SET role = 'member' WHERE user_id = :a"), {"a": a})
        waiter = threading.Thread(target=second)
        waiter.start()
        time.sleep(0.5)
        assert waiter.is_alive(), "second demotion did not wait for the owner lock"
        tx1.commit()
    waiter.join(timeout=5)
    engine.dispose()
    assert outcome == {"status": 409}
