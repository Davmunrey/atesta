"""M365 onboarding step 6: verify, then activate (scanner-connectors spec, #331).

Verification is the connection's activation scan: it may run on a `verifying` connection, pins
the consented tenant and carries the consenting admin for the binding check. `ok` activates the
connection and starts its daily schedule; a refusal or another tenant activates nothing.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from atesta_api.modules.connections.api import ConnectionStateError, begin_verification
from atesta_api.modules.scanning.api import (
    SCHEDULE_TASK,
    ConnectionNotActiveError,
    FixtureRunner,
    LocalScanStore,
    finish_attempt,
    queue_scan,
    start_attempt,
)
from atesta_scanner.job import load_job
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from .conftest import ORG_A, auth
from .test_connections_http import create
from .test_members import events, org_with
from .test_scan_queue import USER, connection

REPO = Path(__file__).resolve().parents[4]
EXPECTED = REPO / "scanner" / "expected"
FIXTURES = REPO / "scanner" / "fixtures" / "synthetic"
TENANT = "11111111-1111-4111-8111-111111111111"  # the synthetic fixtures' tenant
ADMIN = "8e8e8e8e-0000-4000-8000-000000000005"


@pytest.fixture(autouse=True)
def dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATESTA_ENV", "test")


@pytest.fixture
def store(tmp_path: Path) -> LocalScanStore:
    return LocalScanStore(tmp_path / "scans")


def consented(session: Session, status: str = "pending_setup") -> uuid.UUID:
    """An M365 connection after sign-in and admin consent (#314): tenant and admin bound."""
    connection_id = connection(session, status=status)
    session.execute(
        text("UPDATE connections SET ms_tenant_id = :t, consented_by_oid = :o WHERE id = :id"),
        {"t": TENANT, "o": ADMIN, "id": connection_id},
    )
    return connection_id


def state(session: Session, connection_id: uuid.UUID) -> tuple[Any, ...]:
    query = text("SELECT status, external_tenant_id FROM connections WHERE id = :id")
    return tuple(session.execute(query, {"id": connection_id}).one())


def activation(session: Session, store: LocalScanStore) -> tuple[uuid.UUID, Any]:
    connection_id = consented(session)
    begin_verification(session, ORG_A, connection_id, USER)
    scan = queue_scan(session, ORG_A, connection_id, trigger="activation", requested_by=USER)
    started = start_attempt(session, ORG_A, scan.id, attempt=1, store=store, expected_root=EXPECTED)
    assert started.job is not None, started.finished
    return connection_id, started.job


def report(
    store: LocalScanStore, job: Any, verdict: str, tenant: str = TENANT, **extra: Any
) -> None:
    body = {
        "verdict": verdict,
        "tenant_id": tenant,
        "granted": {"app_roles": []},
        "missing": [],
        "extra": [],
        "limits": [],
        **extra,
    }
    key = f"{ORG_A}/scans/{job.scan_id}/attempt-1/out/verification.json"
    store.write(key, json.dumps(body).encode())


def scan_row(session: Session, scan_id: uuid.UUID) -> tuple[Any, ...]:
    query = text("SELECT status, error_code FROM scans WHERE id = :id")
    return tuple(session.execute(query, {"id": scan_id}).one())


def schedules(session: Session, connection_id: uuid.UUID) -> int:
    query = text(
        "SELECT count(*) FROM procrastinate_jobs WHERE task_name = :t"
        " AND args->>'connection_id' = :c"
    )
    return int(session.execute(query, {"t": SCHEDULE_TASK, "c": str(connection_id)}).scalar_one())


# --- domain --------------------------------------------------------------------------------


def test_verification_needs_a_consented_m365_connection_still_onboarding(
    db_rollback: Session,
) -> None:
    for connection_id in (
        connection(db_rollback, status="pending_setup"),  # no sign-in and consent yet
        consented(db_rollback, status="active"),
    ):
        with pytest.raises(ConnectionStateError):
            begin_verification(db_rollback, ORG_A, connection_id, USER)


def test_only_the_activation_scan_runs_on_a_verifying_connection(db_rollback: Session) -> None:
    connection_id = consented(db_rollback)
    begin_verification(db_rollback, ORG_A, connection_id, USER)
    assert state(db_rollback, connection_id) == ("verifying", None)
    with pytest.raises(ConnectionNotActiveError):
        queue_scan(db_rollback, ORG_A, connection_id, trigger="user", requested_by=USER)
    scan = queue_scan(db_rollback, ORG_A, connection_id, trigger="activation", requested_by=USER)
    assert scan.status == "queued"


def test_the_activation_job_pins_the_consented_tenant_and_names_the_admin(
    db_rollback: Session, store: LocalScanStore
) -> None:
    _, job = activation(db_rollback, store)
    raw = store.read(f"{ORG_A}/scans/{job.scan_id}/attempt-1/job.json")
    data = json.loads(raw)
    assert (data["tenant"], data["admin_oid"]) == (TENANT, ADMIN)
    assert load_job(raw).admin_oid == ADMIN  # the wrapper accepts it


def test_an_ok_verification_activates_pins_and_starts_the_schedule(
    db_rollback: Session, store: LocalScanStore
) -> None:
    connection_id, job = activation(db_rollback, store)
    report(store, job, "ok")
    assert FixtureRunner(store, FIXTURES).run(job) == 0
    assert finish_attempt(db_rollback, job, 0, final=False, store=store).status == "collected"
    assert state(db_rollback, connection_id) == ("active", TENANT)
    assert schedules(db_rollback, connection_id) == 1


def test_a_consent_not_tied_to_a_tenant_admin_activates_nothing(
    db_rollback: Session, store: LocalScanStore
) -> None:
    connection_id, job = activation(db_rollback, store)
    report(store, job, "incomplete", missing=["consenting_admin_role"])
    outcome = finish_attempt(db_rollback, job, 10, final=False, store=store)
    assert outcome.status == "blocked"
    assert scan_row(db_rollback, job.scan_id) == ("blocked", "connections.incomplete_permissions")
    assert state(db_rollback, connection_id) == ("incomplete", None)
    assert schedules(db_rollback, connection_id) == 0


def test_a_verified_tenant_other_than_the_consented_one_activates_nothing(
    db_rollback: Session, store: LocalScanStore
) -> None:
    connection_id, job = activation(db_rollback, store)
    report(store, job, "ok", tenant="99999999-1111-4111-8111-111111111111")
    outcome = finish_attempt(db_rollback, job, 0, final=False, store=store)
    assert outcome.status == "blocked"
    assert scan_row(db_rollback, job.scan_id) == ("blocked", "scanning.tenant_mismatch")
    assert state(db_rollback, connection_id) == ("verifying", None)
    assert schedules(db_rollback, connection_id) == 0


# --- HTTP ----------------------------------------------------------------------------------


def verify_url(org: str, connection_id: object) -> str:
    return f"/api/v1/orgs/{org}/connections/{connection_id}/verify"


def code_of(response: Any) -> tuple[int, str]:
    return response.status_code, response.json()["detail"]["code"]


def test_an_admin_verifies_a_consented_connection_once(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    made = create(client, org, subs["owner"])
    path = verify_url(org, made["id"])
    assert code_of(client.post(path, headers=auth(subs["owner"]))) == (
        409,
        "connections.state_invalid",
    )  # no sign-in and consent yet
    with superuser.begin() as conn:
        conn.execute(
            text("UPDATE connections SET ms_tenant_id = :t, consented_by_oid = :o WHERE id = :c"),
            {"t": TENANT, "o": ADMIN, "c": made["id"]},
        )
    assert code_of(client.post(path, headers=auth(subs["mem"]))) == (403, "identity.forbidden")
    response = client.post(path, headers=auth(subs["owner"]))
    assert response.status_code == 202, response.text
    assert (response.json()["trigger"], response.json()["status"]) == ("activation", "queued")
    assert events(superuser, org, "connection.verification_requested") == 1
    again = client.post(path, headers=auth(subs["owner"]))
    assert code_of(again) == (409, "connections.state_invalid")  # already verifying
