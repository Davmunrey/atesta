"""Suspension, the ended trial, the owners' billing view and the Atesta actor, customer side
(operator-portal spec; owner answer 1). Real Postgres with RLS, over every route of the API.

The operator writes arrive in build step 4; here the superuser sets the same columns.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from atesta_api.modules.notifications.api import MemoryMailer, handle_event
from atesta_api.modules.scanning.api import (
    SCHEDULE_TASK,
    LocalScanStore,
    queue_scan,
    scheduled_scan,
    start_attempt,
)
from atesta_api.platform.audit import record
from atesta_api.platform.context import TenantContext
from atesta_api.platform.tenancy import set_tenant_context
from fastapi.testclient import TestClient
from sqlalchemy import Engine, column, func, select, table, text
from sqlalchemy.orm import Session

from .conftest import auth
from .test_api_keys_v2 import READ, WRITE, bearer, make_key
from .test_members import org_with
from .test_notify_events import mailer
from .test_rbac import _add
from .test_route_sweep import ORG_ROUTES, TOKEN_ROUTES, WRITES, _call, _url
from .test_scan_attempts import EXPECTED
from .test_scan_queue import connection

__all__ = ["mailer"]  # the fixture

CLOSURE = "/api/v1/orgs/{org_id}/closure"
OWNER_WHILE_SUSPENDED = {
    ("GET", "/api/v1/orgs/{org_id}/export"),
    ("POST", CLOSURE),
    ("DELETE", CLOSURE),
    ("GET", "/api/v1/orgs/{org_id}/billing-profile"),
}
WRITES_AFTER_TRIAL = {
    ("POST", CLOSURE),
    ("DELETE", CLOSURE),
    ("PUT", "/api/v1/orgs/{org_id}/notifications/preferences"),
}
SUSPENDED = (403, "identity.organization_suspended")
TRIAL_ENDED = (403, "billing.trial_ended")


def _sql(superuser: Engine, statement: str, **params: object) -> None:
    with superuser.begin() as conn:
        conn.execute(text(statement), params)


def suspend(superuser: Engine, org: str, reason: str = "non_payment") -> None:
    _sql(
        superuser,
        "UPDATE organizations SET suspended_at = now(), suspension_reason = :r WHERE id = :o",
        o=org,
        r=reason,
    )


def end_trial(superuser: Engine, org: str) -> None:
    _sql(
        superuser,
        "UPDATE organizations SET created_at = now() - interval '20 days',"
        " trial_ends_at = now() - interval '6 days' WHERE id = :o",
        o=org,
    )


def membership(client: TestClient, sub: str, org: str) -> dict[str, object]:
    memberships = client.get("/api/v1/me", headers=auth(sub)).json()["memberships"]
    found: dict[str, object] = next(m for m in memberships if m["organization_id"] == org)
    return found


# --- suspension ------------------------------------------------------------------------------


def test_every_org_route_refuses_a_suspended_organization_but_the_owners_allowlist(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    suspend(superuser, org)
    owner, admin = auth(subs["owner"]), auth(subs["adm"])
    wrong = {
        (method, path): _call(client, method, _url(path, org), owner)
        for method, path in ORG_ROUTES
        if (method, path) not in OWNER_WHILE_SUSPENDED
    }
    assert {k: v for k, v in wrong.items() if v != SUSPENDED} == {}
    for method, path in OWNER_WHILE_SUSPENDED:  # an admin is refused even there
        assert _call(client, method, _url(path, org), admin) == SUSPENDED, path


def test_owners_of_a_suspended_organization_export_close_and_read_billing(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    suspend(superuser, org)
    owner = auth(subs["owner"])
    exported = client.get(f"/api/v1/orgs/{org}/export", headers=owner)
    assert exported.status_code == 200, exported.text
    profile = client.get(f"/api/v1/orgs/{org}/billing-profile", headers=owner)
    assert (profile.status_code, profile.json()["detail"]["code"]) == (404, "billing.no_profile")
    closing = client.post(
        f"/api/v1/orgs/{org}/closure", json={"confirm_name": "Org"}, headers=owner
    )
    assert closing.status_code == 202, closing.text
    assert client.delete(f"/api/v1/orgs/{org}/closure", headers=owner).status_code == 204


def test_api_keys_of_a_suspended_organization_are_refused(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], READ + WRITE)["token"]
    suspend(superuser, org)
    for method, path in sorted(TOKEN_ROUTES):
        response = client.request(
            method,
            _url(path, org),
            json={} if method in WRITES else None,
            headers=bearer(key, "en"),
        )
        detail = response.json()["detail"]
        assert (response.status_code, detail["code"]) == SUSPENDED, path
        assert detail["message"] == "This organization is suspended."


def test_me_carries_the_suspension_and_only_owners_read_the_reason(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    before = membership(client, subs["mem"], org)
    assert (before["suspended"], before["suspended_at"], before["closure_origin"]) == (
        False,
        None,
        None,
    )
    suspend(superuser, org, "contract_ended")
    owner, member = membership(client, subs["owner"], org), membership(client, subs["mem"], org)
    assert (owner["suspended"], owner["suspension_reason"]) == (True, "contract_ended")
    assert (member["suspended"], member["suspension_reason"]) == (True, None)
    assert owner["suspended_at"] is not None and member["suspended_at"] is not None


def test_reactivation_leaves_every_row_unchanged(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, mem="member")
    client.post(
        f"/api/v1/orgs/{org}/invitations",
        json={"email": f"{uuid.uuid4().hex}@example.com", "role": "member"},
        headers=auth(subs["owner"]),
    )

    def counts() -> dict[str, int]:
        with superuser.connect() as conn:
            tables = conn.execute(
                text(
                    "SELECT c.relname FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid"
                    " WHERE c.relkind = 'r' AND a.attname = 'organization_id'"
                    " AND c.relnamespace = 'public'::regnamespace"
                )
            ).scalars()
            owned = column("organization_id") == uuid.UUID(org)
            return {
                name: conn.execute(
                    select(func.count())
                    .select_from(table(name, column("organization_id")))
                    .where(owned)
                ).scalar_one()
                for name in tables
            }

    before = counts()
    suspend(superuser, org)
    _sql(
        superuser,
        "UPDATE organizations SET suspended_at = NULL, suspension_reason = NULL WHERE id = :o",
        o=org,
    )
    assert counts() == before
    assert client.get(f"/api/v1/orgs/{org}/members", headers=auth(subs["mem"])).status_code == 200


# --- the ended trial (owner answer 1) --------------------------------------------------------


def test_after_the_trial_every_write_is_refused_and_reads_stay(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    end_trial(superuser, org)
    owner = auth(subs["owner"])
    results = {
        (method, path): _call(client, method, _url(path, org), owner)
        for method, path in ORG_ROUTES
        if method in WRITES and (method, path) not in WRITES_AFTER_TRIAL
    }
    assert {k: v for k, v in results.items() if v != TRIAL_ENDED} == {}
    assert client.get(f"/api/v1/orgs/{org}/members", headers=owner).status_code == 200
    assert client.get(f"/api/v1/orgs/{org}/export", headers=owner).status_code == 200
    choice = {"kind": "weekly_summary", "enabled": False}  # a person's choice stays theirs
    saved = client.put(f"/api/v1/orgs/{org}/notifications/preferences", json=choice, headers=owner)
    assert saved.status_code == 200, saved.text


def test_a_plan_set_by_the_operator_ends_the_read_only_state(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    end_trial(superuser, org)
    owner = auth(subs["owner"])
    trial = client.get(f"/api/v1/orgs/{org}/trial", headers=owner).json()
    assert trial["ended"] is True and trial["ends_at"] is not None
    locale = f"/api/v1/orgs/{org}/locale"
    assert _call(client, "PUT", locale, owner) == TRIAL_ENDED
    _sql(superuser, "INSERT INTO subscriptions (organization_id, plan) VALUES (:o, 'pro')", o=org)
    assert client.put(locale, json={"locale": "en"}, headers=owner).status_code == 200
    assert client.get(f"/api/v1/orgs/{org}/trial", headers=owner).json() == {
        "ends_at": None,
        "ended": False,
    }


def test_the_trial_state_is_readable_by_every_member_while_it_runs(
    client: TestClient, superuser: Engine
) -> None:
    org, _ = org_with(client, superuser)
    auditor = _add(superuser, client, org, "auditor", datetime.now(UTC) + timedelta(days=5))
    trial = client.get(f"/api/v1/orgs/{org}/trial", headers=auth(auditor)).json()
    ends = datetime.fromisoformat(trial["ends_at"])
    assert trial["ended"] is False
    assert timedelta(days=13) < ends - datetime.now(UTC) <= timedelta(days=14)


def test_after_the_trial_key_writes_are_refused_and_key_reads_stay(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], READ + WRITE)["token"]
    end_trial(superuser, org)
    for method, path in sorted(TOKEN_ROUTES):
        response = client.request(
            method,
            _url(path, org),
            json={} if method in WRITES else None,
            headers=bearer(key, "es"),
        )
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        code = detail.get("code") if isinstance(detail, dict) else None
        if method in WRITES:
            assert (response.status_code, code) == TRIAL_ENDED, path
            assert isinstance(detail, dict) and "prueba" in detail["message"]
        else:
            assert code != "billing.trial_ended", path


# --- the owners' billing view ------------------------------------------------------------


def test_only_owners_read_their_billing_details(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, adm="admin")
    _sql(
        superuser,
        "INSERT INTO billing_profiles (organization_id, legal_name, tax_id, country)"
        " VALUES (:o, 'Ejemplo S.L.', 'B00000000', 'ES')",
        o=org,
    )
    url = f"/api/v1/orgs/{org}/billing-profile"
    assert client.get(url, headers=auth(subs["adm"])).status_code == 403
    body = client.get(url, headers=auth(subs["owner"])).json()
    assert (body["legal_name"], body["tax_id"], body["country"]) == (
        "Ejemplo S.L.",
        "B00000000",
        "ES",
    )
    assert body["complete"] is False and body["city"] is None


# --- closure origin and activity -----------------------------------------------------------


def test_an_owner_cannot_cancel_an_operator_closure(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser)
    _sql(superuser, "UPDATE organizations SET closure_requested_at = now() WHERE id = :o", o=org)
    assert membership(client, subs["owner"], org)["closure_origin"] == "operator"
    refused = client.delete(f"/api/v1/orgs/{org}/closure", headers=auth(subs["owner"]))
    assert (refused.status_code, refused.json()["detail"]["code"]) == (
        409,
        "identity.closure_by_operator",
    )


def test_operator_events_show_as_the_atesta_team(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser)
    _sql(
        superuser,
        "INSERT INTO audit_events (id, organization_id, action, target_type, target_id)"
        " VALUES (gen_random_uuid(), :o, 'operator.plan_changed', 'organization', :t)",
        o=org,
        t=org,
    )
    events = client.get(f"/api/v1/orgs/{org}/activity", headers=auth(subs["owner"])).json()
    kinds = {e["action"]: (e["actor_kind"], e["actor_email"]) for e in events["events"]}
    assert kinds["operator.plan_changed"] == ("atesta", None)
    assert kinds["org.created"][0] == "member"


@pytest.mark.parametrize("state", ["suspended", "trial_ended"])
def test_a_training_link_of_a_suspended_organization_is_closed(
    client: TestClient, superuser: Engine, state: str
) -> None:
    org, subs = org_with(client, superuser)
    created = client.post(
        f"/api/v1/orgs/{org}/training-campaigns",
        json={
            "title": "Phishing",
            "material_url": "https://example.test/curso",
            "closes_on": (datetime.now(UTC).date() + timedelta(days=30)).isoformat(),
        },
        headers=auth(subs["owner"]),
    )
    assert created.status_code == 201, created.text
    token = created.json()["link"].split("#token=")[1]
    if state == "suspended":
        suspend(superuser, org)
        expected = (410, "compliance.training_closed")
    else:  # an ended trial does not stop the people confirming their training
        end_trial(superuser, org)
        expected = (200, None)
    response = client.post("/api/v1/training/link", json={"token": token})
    code = response.json().get("detail", {}).get("code") if response.status_code != 200 else None
    assert (response.status_code, code) == expected


# --- the worker: no scan and no notice for a suspended organization --------------------------


@pytest.fixture
def as_app(superuser: Engine, probe: object) -> Iterator[tuple[Session, uuid.UUID]]:
    """A new organization with an owner, then the app role in its context; rolled back."""
    org = uuid.uuid4()
    with superuser.connect() as conn:
        tx = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        user = uuid.uuid4()
        session.execute(text("INSERT INTO organizations (id, name) VALUES (:o, 'W')"), {"o": org})
        session.execute(
            text(
                "INSERT INTO users (id, cognito_sub, email, email_verified)"
                " VALUES (:u, :s, 'owner@example.com', true)"
            ),
            {"u": user, "s": f"sub-{user}"},
        )
        session.execute(
            text(
                "INSERT INTO memberships (organization_id, user_id, role) VALUES (:o, :u, 'owner')"
            ),
            {"o": org, "u": user},
        )
        session.execute(text("SET LOCAL ROLE atesta_app"))
        set_tenant_context(session, TenantContext(organization_id=org))
        try:
            yield session, org
        finally:
            session.close()
            tx.rollback()


def suspend_here(session: Session, org: uuid.UUID) -> None:
    session.execute(text("RESET ROLE"))
    session.execute(
        text(
            "UPDATE organizations SET suspended_at = now(), suspension_reason = 'other'"
            " WHERE id = :o"
        ),
        {"o": org},
    )
    session.execute(text("SET LOCAL ROLE atesta_app"))


def test_a_suspended_organization_gets_no_scheduled_scan_but_keeps_its_schedule(
    as_app: tuple[Session, uuid.UUID],
) -> None:
    session, org = as_app
    connection_id = connection(session, "active", org=org)
    suspend_here(session, org)
    assert scheduled_scan(session, org, connection_id) is None
    assert (
        session.scalar(text("SELECT count(*) FROM scans WHERE organization_id = :o"), {"o": org})
        == 0
    )
    deferred = session.scalar(
        text(
            "SELECT count(*) FROM procrastinate_jobs WHERE task_name = :t"
            " AND args->>'connection_id' = :c"
        ),
        {"t": SCHEDULE_TASK, "c": str(connection_id)},
    )
    assert deferred == 1  # the chain goes on, so scans resume after reactivation


def test_a_scan_that_starts_for_a_suspended_organization_ends_without_running(
    as_app: tuple[Session, uuid.UUID], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATESTA_ENV", "test")  # the local scan store is dev-only
    session, org = as_app
    scan = queue_scan(session, org, connection(session, "active", org=org), trigger="user")
    suspend_here(session, org)
    started = start_attempt(
        session, org, scan.id, attempt=1, store=LocalScanStore(tmp_path), expected_root=EXPECTED
    )
    assert started.job is None
    row = session.execute(
        text("SELECT status, error_code FROM scans WHERE id = :s"), {"s": scan.id}
    ).one()
    assert tuple(row) == ("blocked", "scanning.organization_suspended")


def test_no_notice_goes_to_a_suspended_organization(
    as_app: tuple[Session, uuid.UUID], mailer: MemoryMailer
) -> None:
    session, org = as_app
    suspend_here(session, org)
    event_id = record(
        session,
        organization_id=org,
        action="connection.revoked",
        target_type="connection",
        target_id=str(uuid.uuid4()),
        metadata={"provider": "m365"},
    )
    handle_event(session, org, event_id, now=datetime.now(UTC))
    assert mailer.sent == []
    claimed = session.scalar(
        text("SELECT count(*) FROM notification_deliveries WHERE organization_id = :o"), {"o": org}
    )
    assert claimed == 0  # nothing claimed: a notice still due after reactivation can go
