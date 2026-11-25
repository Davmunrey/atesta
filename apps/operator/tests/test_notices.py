"""Service notices through the outbox (operator-portal spec, "Service notices"; ADR-012
amendment 12, owner choice "Bandeja de salida", 2026-11-24): the operator's action queues the
notice in its own transaction, and the worker's job sends it once, to the right people, in the
organization's language, even while it is suspended. Real Postgres: the operator API as
atesta_operator, the worker job as atesta_app.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from atesta_api.modules.notifications.api import MailConfig, MemoryMailer, configure_mail
from atesta_api.platform import db
from atesta_worker import context
from atesta_worker.jobs import make_blueprint, send_service_notices
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.engine import URL

from . import seed
from .conftest import APP_PASSWORD, Issuer, MakeStaff, bearer
from .test_billing import customer_events
from .test_organizations import operator_rows


@pytest.fixture
def mailer(database: URL) -> Iterator[MemoryMailer]:
    sent = MemoryMailer()
    configure_mail(
        MailConfig(
            mailer=sent,
            sender_address="avisos@example.com",
            web_base_url="https://app.example.com",
            tokens=None,  # service notices need no unsubscribe key
        )
    )
    engine = db.make_engine(
        database.set(username="atesta_app", password=APP_PASSWORD), sslmode="disable"
    )
    context.configure(engine)
    yield sent
    configure_mail(None)
    context._factory = None
    engine.dispose()


@pytest.fixture
def admin(staff_pool: Issuer, make_staff: MakeStaff) -> dict[str, str]:
    return bearer(staff_pool.token(make_staff("admin")))


def team(superuser: Engine, prefix: str, **org: Any) -> tuple[seed.Org, dict[str, str]]:
    """An organization with an owner, an admin and a member; returns their emails by role."""
    o = seed.org(superuser, prefix, **org)
    emails = {"admin": f"admin-{o.id.hex[:6]}@customer.test"}
    emails["member"] = f"member-{o.id.hex[:6]}@customer.test"
    for role, email in emails.items():
        seed.add_user(superuser, o, role, email=email)
    owner = seed.run(superuser, "SELECT email FROM users WHERE id = :u", u=o.owner).scalar_one()
    return o, {"owner": owner, **emails}


def outbox(superuser: Engine, org_id: uuid.UUID) -> list[Any]:
    return seed.run(
        superuser,
        "SELECT kind, sent_at FROM service_notices WHERE organization_id = :o ORDER BY created_at",
        o=org_id,
    ).all()


def to(mailer: MemoryMailer, org: seed.Org) -> list[Any]:
    return [m for m in mailer.sent if org.name in m.subject]


def test_suspension_queues_a_notice_the_worker_sends_once_to_owners_and_admins(
    client: TestClient, superuser: Engine, admin: dict[str, str], mailer: MemoryMailer
) -> None:
    o, people = team(superuser, "Notice")
    body = {"reason_code": "non_payment", "confirm_name": o.name, "reason": "Invoice 9"}
    assert (
        client.post(
            f"/api/v1/organizations/{o.id}/suspension", json=body, headers=admin
        ).status_code
        == 200
    )
    assert [(k, sent) for k, sent in outbox(superuser, o.id)] == [("organization_suspended", None)]
    send_service_notices(0)
    send_service_notices(0)  # a second run sends nothing more
    mails = to(mailer, o)
    assert sorted(m.to for m in mails) == sorted([people["owner"], people["admin"]])
    assert mails[0].subject == f"Atesta: {o.name} está suspendida"
    assert "hello@atesta.cloud" in mails[0].body and "no se puede desactivar" in mails[0].body
    assert "List-Unsubscribe" not in mails[0].headers  # nobody can turn it off
    assert outbox(superuser, o.id)[0].sent_at is not None
    kinds = seed.run(
        superuser,
        "SELECT kind, status FROM notification_deliveries WHERE organization_id = :o",
        o=o.id,
    ).all()
    assert sorted(map(tuple, kinds)) == [("service_notice", "sent")] * 2


def test_reactivation_and_closure_notices(
    client: TestClient, superuser: Engine, admin: dict[str, str], mailer: MemoryMailer
) -> None:
    o, people = team(superuser, "Cycle", suspended_at=seed.NOW, suspension_reason="other")
    seed.run(superuser, "UPDATE organizations SET locale = 'en' WHERE id = :o", o=o.id)
    url = f"/api/v1/organizations/{o.id}"
    client.request("DELETE", f"{url}/suspension", json={"reason": "Paid"}, headers=admin)
    client.post(f"{url}/closure", json={"confirm_name": o.name, "reason": "Left"}, headers=admin)
    send_service_notices(0)
    mails = to(mailer, o)
    assert {m.subject for m in mails} == {
        f"Atesta: the closure of {o.name} has started",
        f"Atesta: {o.name} is active again",
    }
    closure = [m for m in mails if "closure" in m.subject]
    assert [m.to for m in closure] == [people["owner"]]  # owners only
    assert people["member"] not in {m.to for m in mails}


def test_the_export_request_asks_the_owners_and_shows_in_activity(
    client: TestClient, superuser: Engine, admin: dict[str, str], mailer: MemoryMailer
) -> None:
    o, people = team(superuser, "Export")
    response = client.post(
        f"/api/v1/organizations/{o.id}/export-request",
        json={"reason": "Offboarding"},
        headers=admin,
    )
    assert response.status_code == 204 and response.content == b""  # no data reaches staff
    assert [e.action for e in customer_events(superuser, o.id)] == ["operator.export_requested"]
    assert operator_rows(superuser, "operator.export_requested", o.id)[0].reason == "Offboarding"
    send_service_notices(0)
    mails = to(mailer, o)
    assert [m.to for m in mails] == [people["owner"]]
    assert mails[0].subject == f"Atesta te pide que exportes los datos de {o.name}"
    assert "Ajustes, Exportar los datos" in mails[0].body


def test_a_refused_action_queues_nothing(
    client: TestClient, superuser: Engine, admin: dict[str, str]
) -> None:
    o, _ = team(superuser, "Refused", suspended_at=seed.NOW, suspension_reason="other")
    body = {"reason_code": "other", "confirm_name": o.name, "reason": "x"}
    response = client.post(f"/api/v1/organizations/{o.id}/suspension", json=body, headers=admin)
    assert response.status_code == 409 and outbox(superuser, o.id) == []


def test_a_notice_for_an_erased_organization_is_dropped(
    superuser: Engine, mailer: MemoryMailer
) -> None:
    gone = uuid.uuid4()
    seed.run(
        superuser,
        "INSERT INTO service_notices (id, organization_id, kind)"
        " VALUES (gen_random_uuid(), :o, 'export_requested')",
        o=gone,
    )
    send_service_notices(0)
    assert outbox(superuser, gone)[0].sent_at is not None


def test_the_worker_sends_them_every_minute() -> None:
    blueprint = make_blueprint()
    assert "send_service_notices" in blueprint.tasks
    periodic = [p for p in blueprint.periodic_registry.periodic_tasks.values()]
    assert any(p.task.name == "send_service_notices" and p.cron == "* * * * *" for p in periodic)


def test_a_notice_whose_news_no_longer_holds_is_not_sent(
    client: TestClient, superuser: Engine, admin: dict[str, str], mailer: MemoryMailer
) -> None:
    """Suspended and reactivated before the worker ran: only "active again" goes out."""
    o, _ = team(superuser, "Blink")
    url = f"/api/v1/organizations/{o.id}/suspension"
    body = {"reason_code": "other", "confirm_name": o.name, "reason": "Mistake"}
    client.post(url, json=body, headers=admin)
    client.request("DELETE", url, json={"reason": "Mistake undone"}, headers=admin)
    send_service_notices(0)
    assert {m.subject for m in to(mailer, o)} == {f"Atesta: {o.name} vuelve a estar activa"}
    assert all(sent is not None for _, sent in outbox(superuser, o.id))
