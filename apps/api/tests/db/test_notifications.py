"""Notification preferences, one-click unsubscribe and the delivery log against Postgres
(notifications spec, PR 1; #379; ADR-012 amendment 7)."""

import logging
import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from atesta_api.main import app
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_api.modules.notifications.api import (
    Kind,
    UnsubscribeTokens,
    claim_delivery,
)
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from .conftest import ORG_A, auth
from .test_members import events, org_with, uid

KEY = bytes(range(32))
PREFS = "/api/v1/orgs/{org}/notifications/preferences"


@pytest.fixture
def tokens(client: TestClient) -> Iterator[UnsubscribeTokens]:
    issued = UnsubscribeTokens(KEY)
    app.state.notification_tokens = issued
    yield issued
    app.state.notification_tokens = None


def prefs(client: TestClient, org: str, sub: str) -> dict[str, tuple[bool, bool]]:
    response = client.get(PREFS.format(org=org), headers=auth(sub))
    assert response.status_code == 200, response.text
    return {p["kind"]: (p["enabled"], p["can_disable"]) for p in response.json()}


def put(client: TestClient, org: str, sub: str, kind: str, enabled: bool) -> tuple[int, str]:
    response = client.put(
        PREFS.format(org=org), json={"kind": kind, "enabled": enabled}, headers=auth(sub)
    )
    body = response.json()
    return response.status_code, body.get("detail", {}).get(
        "code", ""
    ) if not response.is_success else ""


def code_of(response: object) -> tuple[int, str]:
    return response.status_code, response.json()["detail"]["code"]  # type: ignore[attr-defined]


def test_owners_and_admins_get_every_type_on_and_only_optional_ones_can_be_turned_off(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    expected = {
        "connection_alert": (True, False),
        "evidence_malware": (True, False),  # evidence-malware-scanning spec: critical
        "incident_clock": (True, False),
        "scan_problem": (True, True),
        "due_digest": (True, True),
        "weekly_summary": (True, True),
    }
    assert prefs(client, org, subs["owner"]) == expected
    assert prefs(client, org, subs["adm"]) == expected


def test_members_get_only_the_due_digest_and_auditors_nothing(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, mem="member", aud="member")
    with superuser.begin() as conn:  # an auditor needs an access end date (rbac spec)
        conn.execute(
            text(
                "UPDATE memberships SET role = 'auditor', access_expires_at = :d"
                " WHERE organization_id = :o AND user_id = :u"
            ),
            {"d": date.today() + timedelta(days=30), "o": org, "u": uid(client, subs["aud"])},
        )
    assert prefs(client, org, subs["mem"]) == {"due_digest": (True, True)}
    denied = client.get(PREFS.format(org=org), headers=auth(subs["aud"]))
    assert code_of(denied) == (403, "identity.forbidden")


def test_a_person_turns_an_optional_type_off_and_on_with_an_audit_event(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    assert put(client, org, subs["adm"], "weekly_summary", False) == (200, "")
    assert prefs(client, org, subs["adm"])["weekly_summary"] == (False, True)
    assert prefs(client, org, subs["owner"])["weekly_summary"] == (True, True)  # per person
    assert put(client, org, subs["adm"], "weekly_summary", True) == (200, "")
    assert prefs(client, org, subs["adm"])["weekly_summary"] == (True, True)
    assert events(superuser, org, "notification.preferences_changed") == 2


def test_a_critical_type_or_one_the_role_cannot_receive_is_refused(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    assert put(client, org, subs["owner"], "connection_alert", False) == (
        409,
        "notifications.not_optional",
    )
    assert put(client, org, subs["owner"], "incident_clock", False) == (
        409,
        "notifications.not_optional",
    )
    assert put(client, org, subs["mem"], "weekly_summary", False) == (
        409,
        "notifications.not_available",
    )
    assert (
        client.put(
            PREFS.format(org=org),
            json={"kind": "spam", "enabled": False},
            headers=auth(subs["owner"]),
        ).status_code
        == 422
    )
    assert events(superuser, org, "notification.preferences_changed") == 0


def test_one_click_unsubscribe_turns_off_exactly_one_preference_without_a_session(
    client: TestClient, superuser: Engine, tokens: UnsubscribeTokens
) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    admin = uuid.UUID(uid(client, subs["adm"]))
    token = tokens.issue(uuid.UUID(org), admin, Kind.DUE_DIGEST, today=date.today())
    for _ in range(2):  # a second POST (a mail provider retrying) is still 200
        response = client.post(
            "/api/v1/unsubscribe",
            params={"token": token},
            data={"List-Unsubscribe": "One-Click"},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"kind": "due_digest"}
    assert prefs(client, org, subs["adm"])["due_digest"] == (False, True)
    assert prefs(client, org, subs["adm"])["weekly_summary"] == (True, True)
    assert prefs(client, org, subs["owner"])["due_digest"] == (True, True)
    assert events(superuser, org, "notification.unsubscribed") == 2


def test_an_invalid_or_expired_link_is_refused_and_changes_nothing(
    client: TestClient, superuser: Engine, tokens: UnsubscribeTokens
) -> None:
    org, subs = org_with(client, superuser)
    owner = uuid.UUID(uid(client, subs["owner"]))
    old = tokens.issue(uuid.UUID(org), owner, Kind.DUE_DIGEST, today=date.today() - timedelta(61))
    forged = UnsubscribeTokens(bytes(32)).issue(
        uuid.UUID(org), owner, Kind.DUE_DIGEST, today=date.today()
    )
    for token in (old, forged, "x", ""):
        response = client.post("/api/v1/unsubscribe", params={"token": token})
        assert code_of(response) == (400, "notifications.link_invalid")
    assert prefs(client, org, subs["owner"])["due_digest"] == (True, True)
    assert events(superuser, org, "notification.unsubscribed") == 0


def test_a_link_for_someone_no_longer_a_member_is_refused(
    client: TestClient, superuser: Engine, tokens: UnsubscribeTokens
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    member = uuid.UUID(uid(client, subs["mem"]))
    token = tokens.issue(uuid.UUID(org), member, Kind.DUE_DIGEST, today=date.today())
    with superuser.begin() as conn:
        conn.execute(
            text("DELETE FROM memberships WHERE organization_id = :o AND user_id = :u"),
            {"o": org, "u": member},
        )
    response = client.post("/api/v1/unsubscribe", params={"token": token})
    assert code_of(response) == (400, "notifications.link_invalid")
    with superuser.connect() as conn:
        rows = conn.execute(
            text("SELECT count(*) FROM notification_preferences WHERE organization_id = :o"),
            {"o": org},
        ).scalar_one()
    assert rows == 0


def test_without_a_key_the_link_answers_unavailable(client: TestClient) -> None:
    app.state.notification_tokens = None
    response = client.post("/api/v1/unsubscribe", params={"token": "anything"})
    assert code_of(response) == (503, "notifications.unavailable")


def test_the_token_never_reaches_a_log_record(
    client: TestClient,
    superuser: Engine,
    tokens: UnsubscribeTokens,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    org, subs = org_with(client, superuser)
    owner = uuid.UUID(uid(client, subs["owner"]))
    token = tokens.issue(uuid.UUID(org), owner, Kind.WEEKLY_SUMMARY, today=date.today())
    client.post("/api/v1/unsubscribe", params={"token": token})
    # The test client logs the URLs it sends (httpx); in production the mail provider sends them.
    server = [
        r.getMessage()
        for r in caplog.records
        if not (r.name.startswith("httpx") and "https://testserver/" in r.getMessage())
    ]
    assert token not in "\n".join(server)


def test_a_delivery_is_claimed_once_per_person_type_and_key(db_rollback: Session) -> None:
    enter_org_context(db_rollback, ORG_A, ContextReason.JOB)
    user = uuid.uuid4()
    first = claim_delivery(db_rollback, ORG_A, user, Kind.DUE_DIGEST, "2026-11-23")
    again = claim_delivery(db_rollback, ORG_A, user, Kind.DUE_DIGEST, "2026-11-23")
    other_day = claim_delivery(db_rollback, ORG_A, user, Kind.DUE_DIGEST, "2026-11-24")
    other_kind = claim_delivery(db_rollback, ORG_A, user, Kind.WEEKLY_SUMMARY, "2026-11-23")
    assert first is not None and again is None
    assert other_day is not None and other_kind is not None
    status = db_rollback.execute(
        text("SELECT status FROM notification_deliveries WHERE id = :i"), {"i": first}
    ).scalar_one()
    assert status == "queued"


def test_only_a_deliverys_status_may_change(db_rollback: Session) -> None:
    enter_org_context(db_rollback, ORG_A, ContextReason.JOB)
    delivery = claim_delivery(db_rollback, ORG_A, uuid.uuid4(), Kind.SCAN_PROBLEM, "event-1")
    db_rollback.execute(
        text(
            "UPDATE notification_deliveries SET status = 'sent', sent_at = now(),"
            " provider_message_id = 'm-1' WHERE id = :i"
        ),
        {"i": delivery},
    )
    fixed = pytest.raises(Exception, match="only the delivery status may change")
    with fixed, db_rollback.begin_nested():
        db_rollback.execute(
            text("UPDATE notification_deliveries SET dedupe_key = 'other' WHERE id = :i"),
            {"i": delivery},
        )
