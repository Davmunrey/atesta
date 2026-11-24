"""Server-side portfolio summary (consultancy-portfolio spec, issue 228), on real PostgreSQL.

ADR-012 amendment 10: one request reads the caller's organizations one at a time, each in its
own read-only transaction and tenant context. No query sees two organizations.
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from atesta_api.modules.compliance import portfolio
from atesta_api.modules.identity.api import ContextReason, enter_org_context, member_read
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from .conftest import auth, new_sub
from .test_members import uid
from .test_overview import overview_catalog as overview_catalog
from .test_requirement_register import assessment, base
from .test_requirement_register import pack as pack

PORTFOLIO = "/api/v1/portfolio"


def new_org(client: TestClient, sub: str, name: str) -> str:
    created = client.post("/api/v1/orgs", json={"name": name}, headers=auth(sub))
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def join(superuser: Engine, org: str, user: str, role: str, expires: datetime | None) -> None:
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO memberships (organization_id, user_id, role, access_expires_at)"
                " VALUES (:o, :u, :r, :e)"
            ),
            {"o": org, "u": user, "r": role, "e": expires},
        )


def expected(client: TestClient, org: str, sub: str) -> dict[str, Any]:
    """The summary, computed here from the two endpoints the page used to call."""
    frameworks = client.get(f"/api/v1/orgs/{org}/readiness", headers=auth(sub)).json()
    due = client.get(f"/api/v1/orgs/{org}/routines/due", headers=auth(sub)).json()
    started = [f for f in frameworks if f["assessed"] > 0]
    dates = sorted(f["last_assessed_at"] for f in frameworks if f["last_assessed_at"])
    return {
        "frameworks_in_progress": len(started),
        "assessed": sum(f["assessed"] for f in started),
        "total": sum(f["total"] for f in started),
        "overdue": sum(f["overdue"] for f in frameworks),
        "pending": len(due),
        "pending_overdue": len([d for d in due if d["overdue"]]),
        "last_assessed_at": dates[-1] if dates else None,
    }


def busy(client: TestClient, org: str, sub: str, pack: str) -> None:
    """One assessed measure, one overdue measure and one policy waiting for approval."""
    owner = auth(sub)
    posted = client.post(base(org, pack) + "/register/m.cat", json=assessment(), headers=owner)
    assert posted.status_code == 201, posted.text
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assigned = client.post(
        base(org, pack) + "/register/m.none/assignment",
        json={"owner_user_id": uid(client, sub), "due_on": yesterday},
        headers=owner,
    )
    assert assigned.status_code == 201, assigned.text
    policy = client.post(
        f"/api/v1/orgs/{org}/policies",
        json={
            "title": "Política de copias",
            "location_url": "https://example.com/p.pdf",
            "review_months": 12,
        },
        headers=owner,
    )
    assert policy.status_code == 201, policy.text


def rows(client: TestClient, sub: str) -> dict[str, Any]:
    response = client.get(PORTFOLIO, headers=auth(sub))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_one_request_gives_each_organization_the_numbers_of_its_own_endpoints(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    ana = new_sub()
    calm = new_org(client, ana, "Calma S.L.")
    urgent = new_org(client, ana, "Urgente S.A.")
    busy(client, urgent, ana, pack)
    stranger = new_sub()
    theirs = new_org(client, stranger, "Ajena S.L.")
    busy(client, theirs, stranger, pack)

    body = rows(client, ana)
    assert body["not_shown"] == 0
    found = body["rows"]
    assert [r["organization_id"] for r in found] == [urgent, calm]  # most urgent first
    assert [(r["organization_name"], r["role"]) for r in found] == [
        ("Urgente S.A.", "owner"),
        ("Calma S.L.", "owner"),
    ]
    assert found[0]["summary"] == expected(client, urgent, ana)
    assert found[1]["summary"] == expected(client, calm, ana)
    assert found[0]["summary"]["overdue"] == 1 and found[0]["summary"]["pending"] == 1
    assert found[0]["summary"]["frameworks_in_progress"] == 1
    assert found[1]["summary"]["frameworks_in_progress"] == 0
    assert theirs not in str(body)  # another person's organization never appears


def test_expired_access_and_a_failing_organization_cost_only_their_own_row(
    client: TestClient,
    superuser: Engine,
    pack: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ana = new_sub()
    fine = new_org(client, ana, "Bien S.L.")
    busy(client, fine, ana, pack)
    broken = new_org(client, ana, "Rota S.L.")
    other_owner = new_sub()
    audited = new_org(client, other_owner, "Auditada S.L.")
    join(superuser, audited, uid(client, ana), "auditor", datetime.now(UTC) - timedelta(days=1))

    real = portfolio.due_items

    def failing(session: Any, org: uuid.UUID) -> Any:
        if str(org) == broken:
            raise RuntimeError("Texto del cliente que no debe llegar al log")
        return real(session, org)

    monkeypatch.setattr(portfolio, "due_items", failing)
    with caplog.at_level(logging.WARNING, logger="atesta.portfolio"):
        found = {r["organization_id"]: r for r in rows(client, ana)["rows"]}
    assert found[fine]["summary"] == expected(client, fine, ana)
    assert found[broken]["summary"] is None and found[broken]["role"] == "owner"
    assert found[audited]["summary"] is None and found[audited]["role"] == "auditor"
    assert list(found)[0] == fine  # rows that could not be read go last
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert broken in logged and "RuntimeError" in logged
    assert "Texto del cliente" not in logged  # the type, never the message (rule 2)
    assert audited not in logged  # expired access is expected, not an error


def test_the_summary_writes_nothing(client: TestClient, superuser: Engine, pack: str) -> None:
    ana = new_sub()
    org = new_org(client, ana, "Org")
    busy(client, org, ana, pack)

    def state() -> tuple[int, int]:
        with superuser.connect() as conn:
            events = conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
            jobs = conn.execute(text("SELECT count(*) FROM procrastinate_jobs")).scalar_one()
        return int(events), int(jobs)

    before = state()
    rows(client, ana)
    assert state() == before


def test_the_walk_stops_at_the_limit_and_says_how_many_it_left_out(
    client: TestClient, superuser: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ana = new_sub()
    first = new_org(client, ana, "Alfa")
    for name in ("Beta", "Gamma"):
        new_org(client, ana, name)
    monkeypatch.setattr(portfolio, "MAX_ORGANIZATIONS", 1)
    body = rows(client, ana)
    assert [r["organization_id"] for r in body["rows"]] == [first]  # in name order
    assert body["not_shown"] == 2


def test_a_person_with_no_organization_gets_an_empty_portfolio(client: TestClient) -> None:
    assert rows(client, new_sub()) == {"rows": [], "not_shown": 0}


def test_each_read_is_read_only_in_one_organization_and_only_for_a_member(
    client: TestClient, superuser: Engine
) -> None:
    ana = new_sub()
    mine = uuid.UUID(new_org(client, ana, "Mía"))
    also_mine = uuid.UUID(new_org(client, ana, "También mía"))
    not_mine = uuid.UUID(new_org(client, new_sub(), "Ajena"))
    user = uuid.UUID(uid(client, ana))

    with member_read(ana, user, mine) as (session, member):
        assert (member.organization_id, member.role) == (mine, "owner")
        visible = session.execute(text("SELECT id FROM organizations")).scalars().all()
        assert visible == [mine]  # the tenant root shows this organization only
        with pytest.raises(RuntimeError, match="another org context"):
            enter_org_context(session, also_mine, ContextReason.MEMBERSHIP)
    with member_read(ana, user, mine) as (session, _), pytest.raises(DBAPIError, match="read-only"):
        session.execute(text("UPDATE organizations SET name = 'x'"))
    with pytest.raises(HTTPException) as refused, member_read(ana, user, not_mine):
        pytest.fail("a stranger must not get a session")
    assert refused.value.status_code == 404
