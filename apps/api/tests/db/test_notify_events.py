"""Organization language and the immediate notices (notifications spec PR 2, issue 386).

Connection alerts and incident clocks go to owners and admins and cannot be turned off; scan
problems are optional and sent at most once per connection and Madrid day. Every email is in the
organization's language, from "Atesta · <organization>", and holds no customer detail beyond
titles, dates and links.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_api.modules.notifications.api import (
    ClockTiming,
    IncidentClocks,
    MailConfig,
    MemoryMailer,
    UnsubscribeTokens,
    configure_mail,
    handle_event,
    queue_event,
    schedule_clock_notices,
    send_clock_notices,
)
from atesta_api.platform.audit import record
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from .conftest import auth
from .test_members import events, org_with
from .test_routines_b import clock_pack  # noqa: F401 - fixture

PREFS = "/api/v1/orgs/{org}/notifications/preferences"


@pytest.fixture
def mailer() -> Iterator[MemoryMailer]:
    sent = MemoryMailer()
    configure_mail(
        MailConfig(
            mailer=sent,
            sender_address="avisos@example.com",
            web_base_url="https://app.example.com",
            tokens=UnsubscribeTokens(bytes(range(32))),
        )
    )
    yield sent
    configure_mail(None)


def in_org(factory: sessionmaker[Session], org: str) -> Session:
    session = factory()
    session.begin()
    enter_org_context(session, uuid.UUID(org), ContextReason.JOB)
    return session


def event(session: Session, org: str, action: str, **metadata: str | None) -> uuid.UUID:
    return record(
        session,
        organization_id=uuid.UUID(org),
        action=action,
        target_type="connection" if action.startswith("connection.") else "scan",
        target_id=str(uuid.uuid4()),
        metadata={"provider": "m365", **metadata},
    )


# --- organization language -----------------------------------------------------------------


def test_only_the_owner_sets_the_organization_language_and_members_see_it(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    url = f"/api/v1/orgs/{org}/locale"

    def locale_seen(sub: str) -> str:
        me = client.get("/api/v1/me", headers=auth(sub)).json()
        return next(
            m["organization_locale"] for m in me["memberships"] if m["organization_id"] == org
        )

    assert locale_seen(subs["adm"]) == "es"  # the default
    denied = client.put(url, json={"locale": "en"}, headers=auth(subs["adm"]))
    assert (denied.status_code, denied.json()["detail"]["code"]) == (403, "identity.forbidden")
    done = client.put(url, json={"locale": "en"}, headers=auth(subs["owner"]))
    assert done.status_code == 200, done.text
    assert locale_seen(subs["adm"]) == "en"
    assert client.put(url, json={"locale": "fr"}, headers=auth(subs["owner"])).status_code == 422
    assert events(superuser, org, "organization.locale_changed") == 1


# --- connection alerts (critical) --------------------------------------------------------------


def test_a_revoked_connection_alerts_owners_and_admins_once_in_the_org_language(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session], mailer: MemoryMailer
) -> None:
    org, subs = org_with(client, superuser, adm="admin", mem="member")
    with in_org(db_commit, org) as session:
        event_id = event(session, org, "connection.revoked")
        handle_event(session, uuid.UUID(org), event_id, now=datetime.now(UTC))
        handle_event(session, uuid.UUID(org), event_id, now=datetime.now(UTC))  # a retried job
        session.commit()
    owner_email = client.get("/api/v1/me", headers=auth(subs["owner"])).json()["email"]
    admin_email = client.get("/api/v1/me", headers=auth(subs["adm"])).json()["email"]
    assert sorted(m.to for m in mailer.sent) == sorted([owner_email, admin_email])
    message = mailer.sent[0]
    assert message.sender == "Atesta · Org <avisos@example.com>"
    assert "List-Unsubscribe" not in message.headers  # critical: no way out
    assert f"https://app.example.com/app/connections?org={org}" in message.body
    assert message.subject.startswith("Atesta:") and "Microsoft 365" in message.body
    assert "acceso" in message.body  # Spanish, the organization's default


def test_the_alert_uses_english_when_the_organization_chose_it(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session], mailer: MemoryMailer
) -> None:
    org, subs = org_with(client, superuser)
    client.put(f"/api/v1/orgs/{org}/locale", json={"locale": "en"}, headers=auth(subs["owner"]))
    with in_org(db_commit, org) as session:
        handle_event(
            session,
            uuid.UUID(org),
            event(session, org, "connection.over_privileged"),
            now=datetime.now(UTC),
        )
        session.commit()
    assert len(mailer.sent) == 1 and "more permissions" in mailer.sent[0].body


# --- scan problems (optional) --------------------------------------------------------------


def test_a_failed_scan_is_notified_once_per_connection_and_day_and_respects_preferences(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session], mailer: MemoryMailer
) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    client.put(
        PREFS.format(org=org),
        json={"kind": "scan_problem", "enabled": False},
        headers=auth(subs["adm"]),
    )
    connection = str(uuid.uuid4())
    now = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)
    with in_org(db_commit, org) as session:
        for _ in range(2):  # the same connection fails twice the same day
            first = event(
                session, org, "scan.failed", connection_id=connection, trigger="scheduled"
            )
            handle_event(session, uuid.UUID(org), first, now=now)
        session.commit()
    owner_email = client.get("/api/v1/me", headers=auth(subs["owner"])).json()["email"]
    assert [m.to for m in mailer.sent] == [owner_email]  # the admin turned it off
    assert "List-Unsubscribe" in mailer.sent[0].headers
    with superuser.connect() as conn:
        statuses = conn.execute(
            text(
                "SELECT status, count(*) FROM notification_deliveries"
                " WHERE organization_id = :o GROUP BY status ORDER BY status"
            ),
            {"o": org},
        ).all()
    assert [tuple(r) for r in statuses] == [("sent", 1), ("suppressed", 1)]


def test_an_activation_scan_or_another_status_sends_nothing(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session], mailer: MemoryMailer
) -> None:
    org, _ = org_with(client, superuser)
    with in_org(db_commit, org) as session:
        for action, trigger in (("scan.blocked", "activation"), ("scan.succeeded", "scheduled")):
            ev = event(session, org, action, connection_id=str(uuid.uuid4()), trigger=trigger)
            handle_event(session, uuid.UUID(org), ev, now=datetime.now(UTC))
        session.commit()
    assert mailer.sent == []


def test_without_a_mailer_the_delivery_is_suppressed_and_nothing_is_sent(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session]
) -> None:
    configure_mail(None)
    org, _ = org_with(client, superuser)
    with in_org(db_commit, org) as session:
        handle_event(
            session,
            uuid.UUID(org),
            event(session, org, "connection.revoked"),
            now=datetime.now(UTC),
        )
        session.commit()
    with superuser.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT DISTINCT status FROM notification_deliveries WHERE organization_id = :o"
                ),
                {"o": org},
            )
            .scalars()
            .all()
        )
    assert rows == ["suppressed"]


def test_only_notifiable_actions_queue_a_job_with_ids_only(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session]
) -> None:
    org, _ = org_with(client, superuser)
    with in_org(db_commit, org) as session:
        revoked = event(session, org, "connection.revoked")
        succeeded = event(session, org, "scan.succeeded")
        queue_event(session, uuid.UUID(org), revoked, "connection.revoked")
        queue_event(session, uuid.UUID(org), succeeded, "scan.succeeded")
        session.commit()
    with superuser.connect() as conn:
        jobs = (
            conn.execute(
                text(
                    "SELECT args FROM procrastinate_jobs WHERE task_name = 'notify_event'"
                    " AND args->>'organization_id' = :o"
                ),
                {"o": org},
            )
            .scalars()
            .all()
        )
    assert jobs == [{"organization_id": org, "event_id": str(revoked)}]


# --- incident clocks (critical) ------------------------------------------------------------


def clocks(due: datetime, state: str, *, closed: bool = False) -> IncidentClocks:
    return IncidentClocks(
        incident_id=uuid.uuid4(),
        title="Ransomware en el servidor de ficheros",
        closed=closed,
        clocks=[
            IncidentClocks.Clock(
                timing=ClockTiming(ref="nis2:early", due_at=due, hours=24),
                state=state,
                title_es="Alerta temprana",
                title_en="Early warning",
                framework_name="NIS2",
            )
        ],
    )


def test_a_running_clock_is_announced_then_warned_six_hours_before(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session], mailer: MemoryMailer
) -> None:
    org, _ = org_with(client, superuser, adm="admin")
    due = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    view = clocks(due, "running")
    with in_org(db_commit, org) as session:
        send_clock_notices(session, uuid.UUID(org), view, now=due - timedelta(hours=20))
        send_clock_notices(session, uuid.UUID(org), view, now=due - timedelta(hours=19))  # again
        send_clock_notices(session, uuid.UUID(org), view, now=due - timedelta(hours=6))
        session.commit()
    assert len(mailer.sent) == 4  # start and 6-hour warning, each to the owner and the admin
    body = mailer.sent[0].body
    assert "Ransomware en el servidor de ficheros" in body and "Alerta temprana" in body
    assert "NIS2" in body and "25 nov 2026, 13:00" in body  # Madrid time
    assert "List-Unsubscribe" not in mailer.sent[0].headers


def test_a_closed_incident_or_a_met_clock_sends_nothing(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session], mailer: MemoryMailer
) -> None:
    org, _ = org_with(client, superuser)
    due = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    closed = clocks(due, "running", closed=True)
    with in_org(db_commit, org) as session:
        send_clock_notices(session, uuid.UUID(org), closed, now=due - timedelta(hours=6))
        send_clock_notices(session, uuid.UUID(org), clocks(due, "met"), now=due)
        session.commit()
    assert mailer.sent == []


def test_scheduling_defers_one_job_per_future_milestone_with_ids_only(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session]
) -> None:
    org, _ = org_with(client, superuser)
    now = datetime.now(UTC)
    incident = uuid.uuid4()
    timings = [ClockTiming(ref="nis2:early", due_at=now + timedelta(hours=20), hours=24)]
    with in_org(db_commit, org) as session:
        schedule_clock_notices(session, uuid.UUID(org), incident, timings, now=now)
        session.commit()
    with superuser.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT args, scheduled_at FROM procrastinate_jobs WHERE task_name = 'notify_clock'"
                " AND args->>'incident_id' = :i ORDER BY scheduled_at NULLS FIRST"
            ),
            {"i": str(incident)},
        ).all()
    assert [r.args for r in rows] == [{"organization_id": org, "incident_id": str(incident)}] * 3
    # now (start), 6 hours before, and when due
    assert rows[0].scheduled_at is None or rows[0].scheduled_at <= now + timedelta(seconds=5)
    assert abs(rows[1].scheduled_at - (now + timedelta(hours=14))) < timedelta(seconds=5)
    assert abs(rows[2].scheduled_at - (now + timedelta(hours=20))) < timedelta(seconds=5)


@pytest.mark.usefixtures("clock_pack")  # a pack with reporting clocks
def test_reporting_an_incident_schedules_its_clock_notices(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    body = {
        "title": "Ransomware en el servidor de ficheros",
        "aware_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "significant": True,
        "personal_data": False,
    }
    made = client.post(f"/api/v1/orgs/{org}/incidents", json=body, headers=auth(subs["owner"]))
    assert made.status_code == 201, made.text
    with superuser.connect() as conn:
        jobs = conn.execute(
            text(
                "SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'notify_clock'"
                " AND args->>'incident_id' = :i AND args->>'organization_id' = :o"
            ),
            {"i": made.json()["id"], "o": org},
        ).scalar_one()
    assert jobs >= 3  # now, then each future milestone of the running clocks
