"""The daily due digest and the Monday weekly summary (notifications spec PR 3, issue 388).

Owner decisions: notices 30, 7 and 1 day before a date, one digest a day; members only their
own assigned measures; a weekly summary every Monday at 08:00 Madrid, even with nothing new,
with the monthly report link on the first Monday of a month.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from atesta_api.modules.compliance.api import due_items, weekly_compliance
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_api.modules.notifications.api import (
    MailConfig,
    MemoryMailer,
    UnsubscribeTokens,
    WeeklyFacts,
    configure_mail,
    defer_daily,
    next_daily_run,
    send_due_digest,
    send_weekly_summary,
)
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from .conftest import auth
from .test_members import org_with, uid

TODAY = date.today()


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


def seed(client: TestClient, superuser: Engine, org: str, subs: dict[str, str]) -> None:
    """A policy due in 30 days, an access review due in 7, a measure due tomorrow for the member."""
    owner = auth(subs["owner"])
    policy = client.post(
        f"/api/v1/orgs/{org}/policies",
        json={
            "title": "Política de copias",
            "location_url": "https://example.com/p.pdf",
            "review_months": 12,
        },
        headers=owner,
    ).json()
    approved_on = (TODAY + timedelta(days=30)).replace(year=TODAY.year - 1)
    client.post(
        f"/api/v1/orgs/{org}/policies/{policy['id']}/approvals",
        json={
            "version": "1",
            "approver_name": "Dirección",
            "approved_on": approved_on.isoformat(),
            "sha256": "a" * 64,
        },
        headers=owner,
    )
    client.post(
        f"/api/v1/orgs/{org}/access-reviews",
        json={
            "title": "Accesos Q4",
            "system": "Microsoft 365",
            "accounts": [{"account": "a@x.es"}],
            "due_on": (TODAY + timedelta(days=7)).isoformat(),
        },
        headers=owner,
    )
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO requirement_assignments (id, organization_id, framework_key,"
                " requirement_code, owner_user_id, due_on, assigned_by) VALUES (gen_random_uuid(),"
                " :o, 'fw_digest', 'r.1', :m, :d, :m)"
            ),
            {"o": org, "m": uid(client, subs["mem"]), "d": TODAY + timedelta(days=1)},
        )
        conn.execute(
            text(
                "INSERT INTO requirement_assignments (id, organization_id, framework_key,"
                " requirement_code, owner_user_id, due_on, assigned_by) VALUES (gen_random_uuid(),"
                " :o, 'fw_digest', 'r.2', :m, :d, :m)"
            ),
            {"o": org, "m": uid(client, subs["mem"]), "d": TODAY + timedelta(days=5)},
        )  # not on a notice day


def test_due_items_are_the_ones_thirty_seven_and_one_day_ahead(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session]
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    seed(client, superuser, org, subs)
    days = frozenset(TODAY + timedelta(days=d) for d in (30, 7, 1))
    with in_org(db_commit, org) as session:
        items = due_items(session, uuid.UUID(org), days)
    found = sorted((i.kind, i.title_es, i.due_on) for i in items)
    assert found == [
        ("access_review", "Accesos Q4", TODAY + timedelta(days=7)),
        ("assignment", "fw_digest r.1", TODAY + timedelta(days=1)),
        ("policy_review", "Política de copias", TODAY + timedelta(days=30)),
    ]
    [assignment] = [i for i in items if i.kind == "assignment"]
    assert str(assignment.owner_user_id) == uid(client, subs["mem"])


def test_one_digest_a_day_owners_see_everything_members_their_own(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session], mailer: MemoryMailer
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    seed(client, superuser, org, subs)
    days = frozenset(TODAY + timedelta(days=d) for d in (30, 7, 1))
    now = datetime.now(UTC)
    with in_org(db_commit, org) as session:
        items = due_items(session, uuid.UUID(org), days)
        send_due_digest(session, uuid.UUID(org), items, now=now)
        send_due_digest(session, uuid.UUID(org), items, now=now)  # a retried job: no second email
        session.commit()
    by_person = {m.to: m for m in mailer.sent}
    assert len(mailer.sent) == 2
    owner_mail = client.get("/api/v1/me", headers=auth(subs["owner"])).json()["email"]
    member_mail = client.get("/api/v1/me", headers=auth(subs["mem"])).json()["email"]
    owner_body, member_body = by_person[owner_mail].body, by_person[member_mail].body
    assert "Política de copias" in owner_body and "Accesos Q4" in owner_body
    assert "fw_digest r.1" in owner_body
    assert "fw_digest r.1" in member_body and "Política de copias" not in member_body
    assert "List-Unsubscribe" in by_person[member_mail].headers  # optional


def test_no_digest_when_nothing_is_due(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session], mailer: MemoryMailer
) -> None:
    org, _ = org_with(client, superuser)
    with in_org(db_commit, org) as session:
        send_due_digest(session, uuid.UUID(org), [], now=datetime.now(UTC))
        session.commit()
    assert mailer.sent == []


def facts(**over: object) -> WeeklyFacts:
    base: dict[str, object] = {
        "frameworks": [("ENS", 47.5), ("NIS2", None)],
        "scans": {"succeeded": 6, "failed": 1},
        "inactive_connections": 1,
        "due_soon": 2,
        "overdue": 0,
    }
    return WeeklyFacts(**{**base, **over})  # type: ignore[arg-type]


def test_the_weekly_summary_is_sent_once_a_week_and_links_the_monthly_report_on_first_monday(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session], mailer: MemoryMailer
) -> None:
    org, _ = org_with(client, superuser, adm="admin")
    first_monday = datetime(2026, 12, 7, 7, 0, tzinfo=UTC)  # 08:00 in Madrid
    second_monday = datetime(2026, 12, 14, 7, 0, tzinfo=UTC)
    with in_org(db_commit, org) as session:
        send_weekly_summary(session, uuid.UUID(org), facts(), now=first_monday)
        send_weekly_summary(session, uuid.UUID(org), facts(), now=first_monday)  # again
        send_weekly_summary(session, uuid.UUID(org), facts(), now=second_monday)
        session.commit()
    assert len(mailer.sent) == 4  # owner and admin, two weeks
    first, second = mailer.sent[0].body, mailer.sent[-1].body
    assert "47,5 %" in first and "no es una evaluación de conformidad" in first
    assert "sin resultados registrados" in first  # a framework with no score yet
    assert f"/app/report?org={org}" in first and f"/app/report?org={org}" not in second
    assert "cumple" not in first.lower().replace("cumplimiento", "")  # claims-honesty


def test_the_weekly_summary_is_sent_even_when_nothing_changed(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session], mailer: MemoryMailer
) -> None:
    org, _ = org_with(client, superuser)
    quiet = facts(frameworks=[], scans={}, inactive_connections=0, due_soon=0, overdue=0)
    with in_org(db_commit, org) as session:
        send_weekly_summary(
            session, uuid.UUID(org), quiet, now=datetime(2026, 12, 14, 7, tzinfo=UTC)
        )
        session.commit()
    assert len(mailer.sent) == 1 and "Sin cambios" in mailer.sent[0].body


def test_the_compliance_side_of_the_week_counts_due_and_overdue_items(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session]
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    seed(client, superuser, org, subs)
    with in_org(db_commit, org) as session:
        got = weekly_compliance(session, uuid.UUID(org), today=TODAY)
    assert (got.due_soon, got.overdue) == (3, 0)  # tomorrow, in 5 days and in 7 days


def test_the_daily_chain_runs_at_eight_in_madrid_and_keeps_one_waiting_job(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session]
) -> None:
    winter = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
    assert next_daily_run(winter) == datetime(2026, 12, 2, 7, 0, tzinfo=UTC)
    summer = datetime(2026, 7, 1, 5, 0, tzinfo=UTC)  # 07:00 in Madrid: today at 08:00
    assert next_daily_run(summer) == datetime(2026, 7, 1, 6, 0, tzinfo=UTC)
    org, _ = org_with(client, superuser)  # creating the organization started the chain
    with in_org(db_commit, org) as session:
        assert defer_daily(session, uuid.UUID(org), now=datetime.now(UTC)) is False  # waiting
        session.commit()
    with superuser.connect() as conn:
        jobs = conn.execute(
            text(
                "SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'notify_daily'"
                " AND args->>'organization_id' = :o AND status = 'todo'"
            ),
            {"o": org},
        ).scalar_one()
    assert jobs == 1


def test_identity_starts_the_chain_the_notifications_module_runs() -> None:
    from atesta_api.modules.identity.routes import DAILY_NOTICE_TASK
    from atesta_api.modules.notifications.api import DAILY_TASK

    assert DAILY_NOTICE_TASK == DAILY_TASK


def test_opening_the_preferences_restarts_a_missing_chain(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)

    def waiting() -> int:
        with superuser.connect() as conn:
            return int(
                conn.execute(
                    text(
                        "SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'notify_daily'"
                        " AND args->>'organization_id' = :o AND status = 'todo'"
                    ),
                    {"o": org},
                ).scalar_one()
            )

    with superuser.begin() as conn:  # an organization from before the chain existed
        conn.execute(
            text(
                "DELETE FROM procrastinate_jobs WHERE task_name = 'notify_daily'"
                " AND args->>'organization_id' = :o"
            ),
            {"o": org},
        )
    assert waiting() == 0
    client.get(f"/api/v1/orgs/{org}/notifications/preferences", headers=auth(subs["owner"]))
    client.get(f"/api/v1/orgs/{org}/notifications/preferences", headers=auth(subs["owner"]))
    assert waiting() == 1
