"""Organization export and closure (organization-closure spec), on real PostgreSQL with RLS.

Export and the closure request run as the app; erasure runs as atesta_owner, as an operator would.
"""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, Uuid, column, func, select, table, text
from sqlalchemy.exc import ProgrammingError

from .conftest import auth
from .test_members import events, org_with, uid


def _name(client: TestClient, org: str, sub: str) -> str:
    memberships = client.get("/api/v1/me", headers=auth(sub)).json()["memberships"]
    return str(next(m["organization_name"] for m in memberships if m["organization_id"] == org))


def _with_invitation(client: TestClient, org: str, owner: str) -> None:
    response = client.post(
        f"/api/v1/orgs/{org}/invitations",
        json={"email": f"{uuid.uuid4().hex}@example.com", "role": "member"},
        headers=auth(owner),
    )
    assert response.status_code == 201, response.text


# --- export --------------------------------------------------------------------------------


def test_the_owner_exports_only_their_organization_without_secrets(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, ana="member")
    other, other_subs = org_with(client, superuser)
    _with_invitation(client, org, subs["owner"])
    _with_invitation(client, other, other_subs["owner"])
    response = client.get(f"/api/v1/orgs/{org}/export", headers=auth(subs["owner"]))
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["format"] == "atesta-organization-export/1"
    assert data["organization"]["id"] == org
    tables = data["tables"]
    assert {row["organization_id"] for rows in tables.values() for row in rows} == {org}
    assert len(tables["memberships"]) == 2
    assert len(tables["invitations"]) == 1
    assert "token_sha256" not in tables["invitations"][0]
    assert all("credential_ref" not in row for row in tables.get("connections", []))
    assert {m["email"] for m in data["members"]} == {
        m["email"]
        for m in client.get(f"/api/v1/orgs/{org}/members", headers=auth(subs["owner"])).json()
    }
    assert events(superuser, org, "organization.exported") == 1


@pytest.mark.parametrize("role", ["admin", "member", "auditor"])
def test_only_the_owner_exports(client: TestClient, superuser: Engine, role: str) -> None:
    from .test_rbac import _add, _future

    org, subs = org_with(client, superuser)
    someone = (
        _add(superuser, client, org, role, _future())
        if role == "auditor"
        else _add(superuser, client, org, role, None)
    )
    assert client.get(f"/api/v1/orgs/{org}/export", headers=auth(someone)).status_code == 403
    _ = subs


# --- closure request -----------------------------------------------------------------------


def test_closure_needs_the_exact_name_and_can_be_cancelled(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, ana="admin")
    owner = auth(subs["owner"])
    url = f"/api/v1/orgs/{org}/closure"
    wrong = client.post(url, json={"confirm_name": "not it"}, headers=owner)
    assert wrong.status_code == 422
    assert wrong.json()["detail"]["code"] == "identity.closure_name_mismatch"
    name = _name(client, org, subs["owner"])
    assert (
        client.post(url, json={"confirm_name": name}, headers=auth(subs["ana"])).status_code == 403
    )
    requested = client.post(url, json={"confirm_name": name}, headers=owner)
    assert requested.status_code == 202, requested.text
    erase_after = datetime.fromisoformat(requested.json()["erase_after"])
    assert timedelta(days=29) < erase_after - datetime.now(UTC) <= timedelta(days=30)
    membership = next(
        m
        for m in client.get("/api/v1/me", headers=auth(subs["ana"])).json()["memberships"]
        if m["organization_id"] == org
    )
    assert membership["closure_erase_after"] is not None
    assert client.delete(url, headers=owner).status_code == 204
    assert client.delete(url, headers=owner).status_code == 404  # nothing left to cancel
    assert events(superuser, org, "organization.closure_requested") == 1
    assert events(superuser, org, "organization.closure_cancelled") == 1


# --- erasure (operator, atesta_owner) ------------------------------------------------------


@pytest.fixture
def operator(superuser: Engine) -> Iterator[Connection]:
    with superuser.connect() as conn:
        transaction = conn.begin()
        conn.exec_driver_sql("SET LOCAL ROLE atesta_owner")
        try:
            yield conn
        finally:
            transaction.rollback()


def _request_closure(superuser: Engine, org: str, days_ago: int) -> None:
    with superuser.begin() as conn:
        conn.execute(
            text(
                "UPDATE organizations SET closure_requested_at = now() - make_interval(days => :d),"
                " closure_requested_by = (SELECT user_id FROM memberships"
                " WHERE organization_id = :o AND role = 'owner' LIMIT 1) WHERE id = :o"
            ),
            {"o": org, "d": days_ago},
        )


def _rows(conn: Connection, name: str, org: str) -> int:
    target = table(name, column("organization_id", Uuid()))
    query = (
        select(func.count()).select_from(target).where(target.c.organization_id == uuid.UUID(org))
    )
    return int(conn.execute(query).scalar_one())


def _seed_evidence(superuser: Engine, org: str) -> None:
    evidence = uuid.uuid4()
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evidence (id, organization_id, kind, title, source_type, collected_at,"
                " created_by) SELECT :e, :o, 'attestation', 'Synthetic', 'user', now(), user_id"
                " FROM memberships WHERE organization_id = :o AND role = 'owner' LIMIT 1"
            ),
            {"e": evidence, "o": org},
        )
        conn.execute(
            text(
                "INSERT INTO evidence_statements (organization_id, evidence_id, submission_id,"
                " payload_hash, statement) VALUES (:o, :e, :s, :h, 'Synthetic statement')"
            ),
            {"o": org, "e": evidence, "s": uuid.uuid4(), "h": "a" * 64},
        )
        conn.execute(
            text(
                "INSERT INTO evidence_controls (organization_id, evidence_id, control_key)"
                " VALUES (:o, :e, 'ctl.synthetic')"
            ),
            {"o": org, "e": evidence},
        )


def test_erasure_refuses_an_organization_that_did_not_ask_or_is_not_due(
    client: TestClient, superuser: Engine, operator: Connection
) -> None:
    from atesta_api.modules.identity.erasure import ErasureRefusedError, erase_organization

    org, _ = org_with(client, superuser)
    with pytest.raises(ErasureRefusedError, match="no closure request"):
        erase_organization(operator, uuid.UUID(org), note="test", execute=True)
    _request_closure(superuser, org, days_ago=10)
    with pytest.raises(ErasureRefusedError, match="not due"):
        erase_organization(operator, uuid.UUID(org), note="test", execute=True)


def test_erasure_deletes_one_organization_and_its_orphaned_users_with_a_receipt(
    client: TestClient, superuser: Engine, operator: Connection
) -> None:
    from atesta_api.modules.identity.erasure import erase_organization

    org, subs = org_with(client, superuser, ana="member", shared="member")
    other, other_subs = org_with(client, superuser)
    shared = uid(client, subs["shared"])
    ana = uid(client, subs["ana"])
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO memberships (organization_id, user_id, role) VALUES (:o, :u, 'member')"
            ),
            {"o": other, "u": shared},
        )
    _with_invitation(client, org, subs["owner"])
    _seed_evidence(superuser, org)  # child rows prove the foreign-key order of the deletion
    _seed_evidence(superuser, other)
    _request_closure(superuser, org, days_ago=31)

    planned = erase_organization(operator, uuid.UUID(org), note="contract ended", execute=False)
    assert planned["memberships"] == 3 and planned["organizations"] == 1
    assert (
        operator.scalar(text("SELECT count(*) FROM organizations WHERE id = :o"), {"o": org}) == 1
    )

    erased = erase_organization(operator, uuid.UUID(org), note="contract ended", execute=True)
    assert erased == planned
    assert erased["evidence"] == erased["evidence_statements"] == erased["evidence_controls"] == 1
    for name in ("memberships", "invitations", "audit_events", "evidence", "evidence_statements"):
        assert _rows(operator, name, org) == 0, name
    assert (
        operator.scalar(text("SELECT count(*) FROM organizations WHERE id = :o"), {"o": org}) == 0
    )
    assert operator.scalar(text("SELECT count(*) FROM users WHERE id = :u"), {"u": ana}) == 0
    assert operator.scalar(text("SELECT count(*) FROM users WHERE id = :u"), {"u": shared}) == 1
    for name, expected in (("memberships", 2), ("evidence", 1), ("evidence_statements", 1)):
        assert _rows(operator, name, other) == expected, name
    receipt = operator.execute(
        text("SELECT note, row_counts FROM erasure_receipts WHERE organization_id = :o"), {"o": org}
    ).one()
    assert receipt.note == "contract ended"
    assert receipt.row_counts["memberships"] == 3
    assert "name" not in json.dumps(receipt.row_counts)
    _ = other_subs


def test_the_app_role_cannot_read_erasure_receipts(app_engine: Engine) -> None:
    with app_engine.connect() as conn, pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text("SELECT count(*) FROM erasure_receipts"))
