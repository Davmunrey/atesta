"""Google Workspace onboarding backend (scanner-connectors spec, Google onboarding; issue 398).

The owner's runbook records the org's two service accounts; the customer names the super admin
Atesta reads as; verification is the activation scan, a verify run then a scan run. While Google
propagates the delegation (up to 24 h), an activation that only waits for it runs again an hour
later and records nothing.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from atesta_api.modules.connections.api import (
    ConnectionStateError,
    GoogleServiceAccounts,
    begin_verification,
    create_connection,
    register_google_client,
)
from atesta_api.modules.connections.models import Connection
from atesta_api.modules.connections.service import GoogleSubjectError, set_google_subject
from atesta_api.modules.scanning.api import (
    LocalScanStore,
    finish_attempt,
    queue_scan,
    start_attempt,
)
from atesta_scanner.job import load_job
from atesta_worker import context
from atesta_worker.register_google import register
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .conftest import ORG_A, ORG_B, auth
from .test_connections_http import create
from .test_members import events, org_with
from .test_scan_queue import USER, as_org

REPO = Path(__file__).resolve().parents[4]
EXPECTED = REPO / "scanner" / "expected"
CUSTOMER = "C0fixture1"  # the synthetic Google fixtures' customer
SUBJECT = "admin@example.es"


@pytest.fixture(autouse=True)
def dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATESTA_ENV", "test")


@pytest.fixture
def store(tmp_path: Path) -> LocalScanStore:
    return LocalScanStore(tmp_path / "scans")


def accounts(org: uuid.UUID | str = ORG_A, **changes: str) -> GoogleServiceAccounts:
    base = {
        "client_id": "111111111111111111111",
        "verifier_client_id": "222222222222222222222",
        "unique_id": "333333333333333333333",
        "verifier_unique_id": "444444444444444444444",
        "credential_ref": f"local:google-{org}",
        "verifier_credential_ref": f"local:google-verifier-{org}",
    }
    return GoogleServiceAccounts(**{**base, **changes})


def google(session: Session, org: uuid.UUID = ORG_A) -> uuid.UUID:
    as_org(session, org)
    made = create_connection(
        session,
        organization_id=org,
        provider="google_workspace",
        display_name="Google",
        created_by=USER,
    )
    return made.id


def ready(session: Session) -> uuid.UUID:
    """Provisioned by the owner and named by the customer: ready to verify."""
    connection_id = google(session)
    register_google_client(session, ORG_A, connection_id, accounts())
    set_google_subject(
        session, ORG_A, connection_id, email=SUBJECT, primary_domain=None, user_id=USER
    )
    return connection_id


def row(session: Session, connection_id: uuid.UUID, *columns: str) -> tuple[Any, ...]:
    table = Connection.__table__
    query = select(*(table.c[name] for name in columns)).where(table.c.id == connection_id)
    return tuple(session.execute(query).one())


def audit_metadata(session: Session, action: str) -> list[dict[str, Any]]:
    query = text("SELECT metadata FROM audit_events WHERE action = :a ORDER BY occurred_at")
    return [dict(m) for (m,) in session.execute(query, {"a": action})]


def activation(session: Session, store: LocalScanStore) -> tuple[uuid.UUID, Any]:
    connection_id = ready(session)
    begin_verification(session, ORG_A, connection_id, USER)
    scan = queue_scan(session, ORG_A, connection_id, trigger="activation", requested_by=USER)
    started = start_attempt(session, ORG_A, scan.id, attempt=1, store=store, expected_root=EXPECTED)
    assert started.job is not None, started.finished
    return connection_id, started.job


def report(
    store: LocalScanStore, job: Any, verdict: str, name: str = "verification.json", **extra: Any
) -> None:
    body = {
        "verdict": verdict,
        "tenant_id": CUSTOMER,
        "granted": {"scan_scopes": []},
        "missing": [],
        "extra": [],
        "limits": ["roles_through_groups_not_read"],
        **extra,
    }
    store.write(f"{ORG_A}/scans/{job.scan_id}/attempt-1/out/{name}", json.dumps(body).encode())


def activation_scans(session: Session, connection_id: uuid.UUID) -> list[tuple[Any, ...]]:
    query = text(
        "SELECT status, error_code FROM scans WHERE connection_id = :c AND trigger = 'activation'"
        " ORDER BY queued_at, id"
    )
    return [tuple(r) for r in session.execute(query, {"c": connection_id})]


# --- provisioning (the owner's runbook) ----------------------------------------------------------


def test_provisioning_records_both_service_accounts_then_waits_for_setup(
    db_rollback: Session,
) -> None:
    connection_id = google(db_rollback)
    assert row(db_rollback, connection_id, "status") == ("pending_provisioning",)
    register_google_client(db_rollback, ORG_A, connection_id, accounts())
    assert row(
        db_rollback,
        connection_id,
        "status",
        "google_client_id",
        "google_verifier_client_id",
        "google_unique_id",
        "google_verifier_unique_id",
        "credential_ref",
        "verifier_credential_ref",
    ) == (
        "pending_setup",
        "111111111111111111111",
        "222222222222222222222",
        "333333333333333333333",
        "444444444444444444444",
        f"local:google-{ORG_A}",
        f"local:google-verifier-{ORG_A}",
    )
    assert audit_metadata(db_rollback, "connection.provisioned")[-1] == {
        "provider": "google_workspace"
    }


def test_provisioning_happens_once_and_only_for_a_google_connection(db_rollback: Session) -> None:
    connection_id = google(db_rollback)
    register_google_client(db_rollback, ORG_A, connection_id, accounts())
    with pytest.raises(ConnectionStateError):
        register_google_client(db_rollback, ORG_A, connection_id, accounts())
    as_org(db_rollback, ORG_A)
    m365 = create_connection(
        db_rollback, organization_id=ORG_A, provider="m365", display_name="M", created_by=USER
    )
    with pytest.raises(ConnectionStateError):
        register_google_client(db_rollback, ORG_A, m365.id, accounts())
    assert register_google_client(db_rollback, ORG_A, uuid.uuid4(), accounts()) is None


def test_provisioning_never_points_at_another_orgs_secret(db_rollback: Session) -> None:
    connection_id = google(db_rollback)
    with pytest.raises(IntegrityError, match="google_ref_in_tenant"), db_rollback.begin_nested():
        register_google_client(db_rollback, ORG_A, connection_id, accounts(org=ORG_B))


@pytest.mark.parametrize(
    "changes",
    [
        {"client_id": "not-a-number"},
        {"unique_id": "12"},
        {"verifier_client_id": "111111111111111111111"},  # one client per account
    ],
)
def test_service_account_ids_are_numeric_and_distinct(changes: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="service account ids"):
        accounts(**changes)


def test_the_database_refuses_google_ids_on_an_m365_row_or_not_numeric(
    db_rollback: Session,
) -> None:
    as_org(db_rollback, ORG_A)
    m365 = create_connection(
        db_rollback, organization_id=ORG_A, provider="m365", display_name="M", created_by=USER
    )
    for column, value, constraint in (
        ("google_unique_id", "333333333333333333333", "m365_no_google"),
        ("google_client_id", "abc", "google_ids_numeric"),
    ):
        with pytest.raises(IntegrityError, match=constraint), db_rollback.begin_nested():
            db_rollback.execute(
                update(Connection.__table__)
                .where(Connection.__table__.c.id == m365.id)
                .values({column: value})
            )


# --- the super admin Atesta reads as -------------------------------------------------------------


def test_the_primary_domain_is_the_emails_unless_given(db_rollback: Session) -> None:
    connection_id = google(db_rollback)
    set_google_subject(
        db_rollback, ORG_A, connection_id, email="Ana@Example.ES", primary_domain=None, user_id=USER
    )
    assert row(db_rollback, connection_id, "google_subject_email", "primary_domain") == (
        "Ana@Example.ES",
        "example.es",
    )
    set_google_subject(
        db_rollback,
        ORG_A,
        connection_id,
        email="it@second.es",
        primary_domain="Example.ES",  # a super admin on a secondary domain
        user_id=USER,
    )
    assert row(db_rollback, connection_id, "primary_domain") == ("example.es",)
    for metadata in audit_metadata(db_rollback, "connection.google_subject_set"):
        assert metadata == {"provider": "google_workspace"}  # never the email (rule 2)


@pytest.mark.parametrize(
    ("email", "domain"),
    [("admin", None), ("admin@localhost", None), ("../x@example.es", None), (SUBJECT, "nope")],
)
def test_an_email_or_domain_google_cannot_have_is_refused(
    db_rollback: Session, email: str, domain: str | None
) -> None:
    connection_id = google(db_rollback)
    with pytest.raises(GoogleSubjectError):
        set_google_subject(
            db_rollback, ORG_A, connection_id, email=email, primary_domain=domain, user_id=USER
        )


def test_the_subject_changes_only_while_onboarding(db_rollback: Session) -> None:
    connection_id = ready(db_rollback)
    begin_verification(db_rollback, ORG_A, connection_id, USER)
    with pytest.raises(ConnectionStateError):
        set_google_subject(
            db_rollback, ORG_A, connection_id, email=SUBJECT, primary_domain=None, user_id=USER
        )


# --- verification: the activation scan -----------------------------------------------------------


def test_verification_needs_provisioning_and_a_subject(db_rollback: Session) -> None:
    provisioned_only = google(db_rollback)
    register_google_client(db_rollback, ORG_A, provisioned_only, accounts())
    subject_only = google(db_rollback)
    set_google_subject(
        db_rollback, ORG_A, subject_only, email=SUBJECT, primary_domain=None, user_id=USER
    )
    for connection_id in (provisioned_only, subject_only):
        with pytest.raises(ConnectionStateError):
            begin_verification(db_rollback, ORG_A, connection_id, USER)
    connection_id = ready(db_rollback)
    begin_verification(db_rollback, ORG_A, connection_id, USER)
    status, since = row(db_rollback, connection_id, "status", "verifying_since")
    assert status == "verifying" and since is not None


def test_the_activation_job_pins_the_primary_domain_and_names_the_subject(
    db_rollback: Session, store: LocalScanStore
) -> None:
    _, job = activation(db_rollback, store)
    assert (job.credential_ref, job.verifier_credential_ref) == (
        f"local:google-{ORG_A}",
        f"local:google-verifier-{ORG_A}",
    )
    raw = store.read(f"{ORG_A}/scans/{job.scan_id}/attempt-1/job.json")
    data = json.loads(raw)
    assert data["tenant"] == "example.es"
    assert data["google_subject"] == SUBJECT
    assert data["google_service_accounts"] == ["333333333333333333333", "444444444444444444444"]
    assert "verified_since" not in data and "admin_oid" not in data
    assert load_job(raw).google_subject == SUBJECT  # the wrapper accepts it


def test_an_ok_activates_pins_the_customer_and_later_jobs_reread_from_it(
    db_rollback: Session, store: LocalScanStore
) -> None:
    connection_id, job = activation(db_rollback, store)
    report(store, job, "ok")
    assert finish_attempt(db_rollback, job, 0, final=False, store=store).status == "collected"
    status, tenant, verified_at = row(
        db_rollback, connection_id, "status", "external_tenant_id", "verified_at"
    )
    assert (status, tenant) == ("active", CUSTOMER)
    scan = queue_scan(db_rollback, ORG_A, connection_id, trigger="user", requested_by=USER)
    started = start_attempt(
        db_rollback, ORG_A, scan.id, attempt=1, store=store, expected_root=EXPECTED
    )
    assert started.job is not None
    data = json.loads(store.read(f"{ORG_A}/scans/{scan.id}/attempt-1/job.json"))
    assert data["tenant"] == CUSTOMER
    assert data["verified_since"] == verified_at.isoformat()


def test_on_exit_10_the_scan_runs_own_refusal_is_recorded(
    db_rollback: Session, store: LocalScanStore
) -> None:
    connection_id, job = activation(db_rollback, store)
    report(store, job, "ok")  # the verify run passed
    report(store, job, "incomplete", "scan-verification.json", missing=["delegated_user"])
    assert finish_attempt(db_rollback, job, 10, final=False, store=store).status == "blocked"
    status, granted = row(db_rollback, connection_id, "status", "granted")
    assert status == "incomplete" and granted["missing"] == ["delegated_user"]


def test_while_google_propagates_activation_runs_again_in_an_hour(
    db_rollback: Session, store: LocalScanStore
) -> None:
    connection_id, job = activation(db_rollback, store)
    report(store, job, "incomplete", missing=["scan_client_not_authorized"])
    outcome = finish_attempt(db_rollback, job, 10, final=False, store=store)
    assert outcome.status == "blocked"
    assert row(db_rollback, connection_id, "status", "granted") == ("verifying", {})  # unrecorded
    assert sorted(activation_scans(db_rollback, connection_id)) == [  # one transaction: same now()
        ("blocked", "connections.incomplete_permissions"),
        ("queued", None),
    ]
    delay = db_rollback.execute(
        text(
            "SELECT extract(epoch FROM scheduled_at - now()) FROM procrastinate_jobs"
            " WHERE task_name = 'atesta:run_scan' AND args->>'organization_id' = :o"
            " ORDER BY id DESC LIMIT 1"
        ),
        {"o": str(ORG_A)},
    ).scalar_one()
    assert 3500 < float(delay) < 3660  # an hour from when the job is deferred


def test_after_24_hours_or_for_anything_else_the_refusal_is_recorded(
    db_rollback: Session, store: LocalScanStore
) -> None:
    connection_id, job = activation(db_rollback, store)
    db_rollback.execute(
        text("UPDATE connections SET verifying_since = now() - interval '25 hours' WHERE id = :id"),
        {"id": connection_id},
    )
    report(store, job, "incomplete", missing=["verifier_client_authorization_event"])
    finish_attempt(db_rollback, job, 10, final=False, store=store)
    assert row(db_rollback, connection_id, "status") == ("incomplete",)
    assert activation_scans(db_rollback, connection_id) == [  # recorded, and no new scan
        ("blocked", "connections.incomplete_permissions")
    ]
    other, job2 = activation(db_rollback, store)
    report(
        store,
        job2,
        "incomplete",
        missing=["scan_client_not_authorized", "delegated_user_not_super_admin"],
    )
    finish_attempt(db_rollback, job2, 10, final=False, store=store)
    assert row(db_rollback, other, "status") == ("incomplete",)  # the customer must act


# --- HTTP ----------------------------------------------------------------------------------------


def test_an_admin_names_the_super_admin_and_starts_verification(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    connection = create(client, org, subs["owner"], provider="google_workspace")
    url = f"/api/v1/orgs/{org}/connections/{connection['id']}"
    body = {"email": SUBJECT}
    assert client.put(url + "/google", json=body, headers=auth(subs["mem"])).status_code == 403
    bad = client.put(url + "/google", json={"email": "admin"}, headers=auth(subs["owner"]))
    assert (bad.status_code, bad.json()["detail"]["code"]) == (
        422,
        "connections.google_subject_invalid",
    )
    done = client.put(url + "/google", json=body, headers=auth(subs["owner"]))
    assert done.status_code == 200 and done.json()["status"] == "pending_provisioning"
    assert SUBJECT not in done.text  # the list and detail never echo the email
    assert events(superuser, org, "connection.google_subject_set") == 1
    early = client.post(url + "/verify", headers=auth(subs["owner"]))
    assert (early.status_code, early.json()["detail"]["code"]) == (
        409,
        "connections.state_invalid",
    )
    missing = client.put(
        f"/api/v1/orgs/{org}/connections/{uuid.uuid4()}/google",
        json=body,
        headers=auth(subs["owner"]),
    )
    assert missing.status_code == 404
    m365 = create(client, org, subs["owner"])
    other = client.put(
        f"/api/v1/orgs/{org}/connections/{m365['id']}/google",
        json=body,
        headers=auth(subs["owner"]),
    )
    assert other.status_code == 409


def test_the_owners_command_provisions_then_verification_can_start(
    client: TestClient, superuser: Engine, app_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    org, subs = org_with(client, superuser)
    connection = create(client, org, subs["owner"], provider="google_workspace")
    context.configure(app_engine)
    argv = [
        *("--organization-id", org, "--connection-id", str(connection["id"])),
        *("--client-id", "111111111111111111111", "--verifier-client-id", "222222222222222222222"),
        *("--unique-id", "333333333333333333333", "--verifier-unique-id", "444444444444444444444"),
        *("--credential-ref", f"local:google-{org}"),
        *("--verifier-credential-ref", f"local:google-verifier-{org}"),
    ]
    with pytest.raises(SystemExit, match="not this org's Google secret"):
        register([*argv[:-2], "--verifier-credential-ref", f"local:google-verifier-{ORG_B}"])
    assert register(argv) == {
        "event": "connection.provisioned",
        "organization_id": org,
        "connection_id": str(connection["id"]),
    }
    with pytest.raises(SystemExit, match="waiting for provisioning"):
        register(argv)
    url = f"/api/v1/orgs/{org}/connections/{connection['id']}"
    client.put(url + "/google", json={"email": SUBJECT}, headers=auth(subs["owner"]))
    started = client.post(url + "/verify", headers=auth(subs["owner"]))
    assert started.status_code == 202, started.text
    assert started.json()["trigger"] == "activation"
    assert events(superuser, org, "connection.provisioned") == 1
