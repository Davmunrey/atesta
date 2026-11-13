"""Scan ingest against a real Postgres with RLS (scanner-connectors spec, Ingest and Coverage)."""

import copy
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_api.modules.scanning.api import (
    SNAPSHOT_TASK,
    FixtureRunner,
    LocalScanStore,
    ScanJob,
    ScanNotFoundError,
    ingest_scan,
    output_prefix,
)
from atesta_api.platform.context import TenantContext
from atesta_api.platform.tenancy import set_tenant_context
from atesta_core.manifest import build_manifest
from sqlalchemy import text
from sqlalchemy.orm import Session

from .conftest import ORG_A, ORG_B

FIXTURES = Path(__file__).resolve().parents[4] / "scanner" / "fixtures" / "synthetic"
TENANT = {"m365": "11111111-1111-4111-8111-111111111111", "google_workspace": "C0fixture1"}
LISTED = {
    "m365": [
        "entra_admin_consent_workflow_enabled",
        "entra_admin_users_cloud_only",
        "entra_admin_users_mfa_enabled",
        "exchange_external_email_tagging_enabled",
        "exchange_mailbox_audit_bypass_disabled",
        "exchange_transport_rules_whitelist_disabled",
        "teams_external_users_cannot_start_conversations",
    ],
    "google_workspace": [
        "calendar_external_invitations_warning",
        "calendar_external_sharing_primary_calendar",
        "chat_apps_installation_disabled",
        "chat_external_file_sharing_disabled",
    ],
}
EXCLUDED = {"m365": {"teams_external_users_cannot_start_conversations": "not_granted"}}
SCAN = text(
    "INSERT INTO scans (id, organization_id, connection_id, provider, trigger, status, engine,"
    " engine_version, output_prefix, attempts) VALUES (:id, :org, gen_random_uuid(), :provider,"
    " 'user', :status, 'prowler', '5.49.0', :prefix, 1)"
)


@pytest.fixture(autouse=True)
def dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATESTA_ENV", "test")


@pytest.fixture
def tx(db_rollback: Session) -> Session:
    enter_org_context(db_rollback, ORG_A, ContextReason.JOB)
    return db_rollback


@pytest.fixture
def store(tmp_path: Path) -> LocalScanStore:
    return LocalScanStore(tmp_path / "scans")


def collected(
    session: Session,
    store: LocalScanStore,
    provider: str = "m365",
    fixture: str = "scan.ocsf.json",
    status: str = "collected",
) -> uuid.UUID:
    scan_id = uuid.uuid4()
    FixtureRunner(store, FIXTURES, fixture).run(ScanJob(ORG_A, scan_id, 1, provider))
    prefix = output_prefix(ORG_A, scan_id, 1)
    session.execute(
        SCAN,
        {"id": scan_id, "org": ORG_A, "provider": provider, "status": status, "prefix": prefix},
    )
    return scan_id


def ingest(session: Session, store: LocalScanStore, scan_id: uuid.UUID, **kw: Any) -> str:
    provider = kw.pop("provider", "m365")
    return ingest_scan(
        session,
        scan_id,
        store=store,
        tenant=kw.pop("tenant", TENANT[provider]),
        listed=LISTED[provider],
        excluded=EXCLUDED.get(provider, {}),
        **kw,
    )


def scan_row(session: Session, scan_id: uuid.UUID) -> dict[str, Any]:
    row = session.execute(
        text(
            "SELECT status, error_code, expected_checks, evaluated_checks, manifest_sha256,"
            " ingested_at IS NOT NULL AS ingested, finished_at IS NOT NULL AS finished"
            " FROM scans WHERE id = :id"
        ),
        {"id": scan_id},
    ).one()
    return dict(row._mapping)


ROWS = {
    "scan_check_results": text(
        "SELECT check_id, status, reason, pass_count, fail_count, manual_count"
        " FROM scan_check_results WHERE scan_id = :id ORDER BY check_id"
    ),
    "findings": text(
        "SELECT check_id, status, muted, severity, service, resource_uid, region"
        " FROM findings WHERE scan_id = :id ORDER BY check_id, resource_uid"
    ),
}


def rows(session: Session, table: str, scan_id: uuid.UUID) -> list[tuple[Any, ...]]:
    return [tuple(r) for r in session.execute(ROWS[table], {"id": scan_id})]


def audit(session: Session, scan_id: uuid.UUID) -> list[tuple[Any, ...]]:
    query = text(
        "SELECT action, metadata FROM audit_events WHERE target_type = 'scan'"
        " AND target_id = :id ORDER BY occurred_at"
    )
    return [tuple(r) for r in session.execute(query, {"id": str(scan_id)})]


JOBS = text(
    "SELECT task_name, queue_name, args FROM procrastinate_jobs"
    " WHERE args->>'scan_id' = :id ORDER BY id"
)


def jobs(session: Session, scan_id: uuid.UUID) -> list[tuple[Any, ...]]:
    """Jobs deferred in this transaction: they commit or roll back with the ingest."""
    return [tuple(r) for r in session.execute(JOBS, {"id": str(scan_id)})]


def test_a_collected_m365_scan_is_ingested(tx: Session, store: LocalScanStore) -> None:
    scan_id = collected(tx, store)
    assert ingest(tx, store, scan_id) == "succeeded"
    manifest = store.read(output_prefix(ORG_A, scan_id, 1) + "manifest.json")
    assert scan_row(tx, scan_id) == {
        "status": "succeeded",
        "error_code": None,
        "expected_checks": 6,
        "evaluated_checks": 5,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "ingested": True,
        "finished": True,
    }
    assert rows(tx, "scan_check_results", scan_id) == [
        ("entra_admin_consent_workflow_enabled", "manual", None, 0, 1, 0),
        ("entra_admin_users_cloud_only", "fail", None, 0, 1, 0),
        ("entra_admin_users_mfa_enabled", "pass", None, 1, 0, 0),
        ("exchange_external_email_tagging_enabled", "pass", None, 1, 0, 0),
        ("exchange_mailbox_audit_bypass_disabled", "manual", None, 0, 0, 1),
        ("exchange_transport_rules_whitelist_disabled", "not_evaluated", "no_findings", 0, 0, 0),
        (
            "teams_external_users_cannot_start_conversations",
            "not_evaluated",
            "not_granted",
            0,
            0,
            0,
        ),
    ]
    findings = rows(tx, "findings", scan_id)
    detail = text(
        "SELECT resource_type, resource_uid, resource_name, region, message FROM findings"
        " WHERE scan_id = :id AND check_id = 'entra_admin_users_mfa_enabled'"
    )
    assert tuple(tx.execute(detail, {"id": scan_id}).one()) == (
        "NotDefined",
        "admin-1",
        "Admin One",
        "global",
        "Synthetic PASS for Admin One.",
    )
    assert [(f[0], f[1], f[2], f[3], f[4]) for f in findings] == [
        ("entra_admin_consent_workflow_enabled", "fail", True, "high", "entra"),
        ("entra_admin_users_cloud_only", "fail", False, "high", "entra"),
        ("entra_admin_users_mfa_enabled", "pass", False, "high", "entra"),
        ("exchange_external_email_tagging_enabled", "pass", False, "medium", "exchange"),
        ("exchange_mailbox_audit_bypass_disabled", "manual", False, "high", "exchange"),
    ]
    assert audit(tx, scan_id) == [
        ("scan.succeeded", {"provider": "m365", "expected_checks": 6, "evaluated_checks": 5})
    ]
    ids = {"organization_id": str(ORG_A), "scan_id": str(scan_id)}
    assert jobs(tx, scan_id) == [(SNAPSHOT_TASK, "scans", ids)]


def test_a_service_with_no_finding_at_all_makes_the_scan_partial(
    tx: Session, store: LocalScanStore
) -> None:
    scan_id = collected(tx, store, "google_workspace")
    listed = [*LISTED["google_workspace"], "gmail_mail_delegation_disabled"]
    status = ingest_scan(
        tx, scan_id, store=store, tenant=TENANT["google_workspace"], listed=listed, excluded={}
    )
    assert status == "partial"
    assert scan_row(tx, scan_id)["evaluated_checks"] == 4
    assert ("gmail_mail_delegation_disabled", "not_evaluated", "no_findings", 0, 0, 0) in rows(
        tx, "scan_check_results", scan_id
    )
    assert [a[0] for a in audit(tx, scan_id)] == ["scan.partial"]
    assert len(jobs(tx, scan_id)) == 1  # a partial scan is ingested and scored


def test_ingest_is_idempotent(tx: Session, store: LocalScanStore) -> None:
    scan_id = collected(tx, store)
    ingest(tx, store, scan_id)
    assert ingest(tx, store, scan_id) == "succeeded"
    assert len(rows(tx, "scan_check_results", scan_id)) == 7
    assert len(rows(tx, "findings", scan_id)) == 5
    assert len(audit(tx, scan_id)) == 1
    assert len(jobs(tx, scan_id)) == 1


@pytest.mark.parametrize("provider", ["m365", "google_workspace"])
def test_a_finding_from_another_tenant_rejects_the_whole_scan(
    tx: Session, store: LocalScanStore, provider: str
) -> None:
    scan_id = collected(tx, store, provider, "wrong-tenant.ocsf.json")
    assert ingest(tx, store, scan_id, provider=provider) == "failed"
    assert_rejected(tx, store, scan_id, "scanning.tenant_mismatch", provider)


def test_an_unexpected_check_rejects_the_whole_scan(tx: Session, store: LocalScanStore) -> None:
    scan_id = collected(tx, store, fixture="unexpected-check.ocsf.json")
    assert ingest(tx, store, scan_id) == "failed"
    assert_rejected(tx, store, scan_id, "scanning.output_invalid")


def test_output_changed_after_the_manifest_rejects_the_scan(
    tx: Session, store: LocalScanStore, tmp_path: Path
) -> None:
    scan_id = collected(tx, store)
    ocsf = tmp_path / "scans" / output_prefix(ORG_A, scan_id, 1) / "prowler.ocsf.json"
    ocsf.write_bytes(ocsf.read_bytes().replace(b'"PASS"', b'"FAIL"'))
    assert ingest(tx, store, scan_id) == "failed"
    assert_rejected(tx, store, scan_id, "scanning.output_invalid")


def test_output_over_the_size_limit_rejects_the_scan(tx: Session, store: LocalScanStore) -> None:
    scan_id = collected(tx, store)
    assert ingest(tx, store, scan_id, max_bytes=1000) == "failed"
    assert_rejected(tx, store, scan_id, "scanning.output_invalid")


def test_a_missing_manifest_rejects_the_scan(
    tx: Session, store: LocalScanStore, tmp_path: Path
) -> None:
    scan_id = collected(tx, store)
    (tmp_path / "scans" / output_prefix(ORG_A, scan_id, 1) / "manifest.json").unlink()
    assert ingest(tx, store, scan_id) == "failed"
    assert_rejected(tx, store, scan_id, "scanning.output_invalid")


def written(
    session: Session, store: LocalScanStore, files: dict[str, bytes], manifest: bytes | None = None
) -> uuid.UUID:
    """A collected scan whose output is exactly these files and manifest."""
    scan_id = uuid.uuid4()
    prefix = output_prefix(ORG_A, scan_id, 1)
    for name, data in files.items():
        store.write(prefix + name, data)
    store.write(prefix + "manifest.json", build_manifest(files) if manifest is None else manifest)
    row = {"id": scan_id, "org": ORG_A, "provider": "m365", "status": "collected"}
    session.execute(SCAN, {**row, "prefix": prefix})
    return scan_id


def test_a_check_with_two_resources_is_one_result(tx: Session, store: LocalScanStore) -> None:
    findings = json.loads((FIXTURES / "m365" / "scan.ocsf.json").read_bytes())
    second = copy.deepcopy(findings[0])  # entra_admin_users_mfa_enabled, PASS
    second["resources"][0]["uid"] = "admin-2"
    scan_id = written(tx, store, {"prowler.ocsf.json": json.dumps([*findings, second]).encode()})
    assert ingest(tx, store, scan_id) == "succeeded"
    assert len(rows(tx, "findings", scan_id)) == 6
    assert ("entra_admin_users_mfa_enabled", "pass", None, 2, 0, 0) in rows(
        tx, "scan_check_results", scan_id
    )
    assert scan_row(tx, scan_id)["evaluated_checks"] == 5


def test_a_manifest_without_the_ocsf_output_rejects_the_scan(
    tx: Session, store: LocalScanStore
) -> None:
    scan_id = written(tx, store, {"notes.txt": b"x"})
    assert ingest(tx, store, scan_id) == "failed"
    assert_rejected(tx, store, scan_id, "scanning.output_invalid")


def test_a_manifest_over_the_size_limit_is_rejected_before_it_is_read(
    tx: Session, store: LocalScanStore
) -> None:
    files = {"prowler.ocsf.json": b"[]"}
    scan_id = written(tx, store, files, build_manifest(files) + b" " * 200)
    assert ingest(tx, store, scan_id, max_bytes=100) == "failed"
    assert_rejected(tx, store, scan_id, "scanning.output_invalid")


def test_a_collected_scan_without_an_output_prefix_is_rejected(tx: Session) -> None:
    scan_id = uuid.uuid4()
    row = {"id": scan_id, "org": ORG_A, "provider": "m365", "status": "collected"}
    tx.execute(SCAN, {**row, "prefix": None})
    store = DictStore()
    assert ingest(tx, store, scan_id) == "failed"  # type: ignore[arg-type]
    assert store.reads == []
    assert scan_row(tx, scan_id)["error_code"] == "scanning.output_invalid"


class DictStore:
    def __init__(self) -> None:
        self.reads: list[str] = []

    def read(self, key: str) -> bytes:
        self.reads.append(key)
        raise FileNotFoundError(key)


def assert_rejected(
    session: Session, store: LocalScanStore, scan_id: uuid.UUID, code: str, provider: str = "m365"
) -> None:
    row = scan_row(session, scan_id)
    assert row == {
        "status": "failed",
        "error_code": code,
        "expected_checks": 0,
        "evaluated_checks": 0,
        "manifest_sha256": None,
        "ingested": False,
        "finished": True,
    }
    assert rows(session, "scan_check_results", scan_id) == []
    assert rows(session, "findings", scan_id) == []
    events = [("scan.failed", {"provider": provider, "error_code": code})]
    assert audit(session, scan_id) == events
    assert jobs(session, scan_id) == []  # nothing to score
    # A retried ingest of a rejected scan changes nothing.
    assert ingest(session, store, scan_id, provider=provider) == "failed"
    assert audit(session, scan_id) == events


@pytest.mark.parametrize("status", ["queued", "running", "blocked"])
def test_a_scan_that_was_not_collected_is_left_alone(
    tx: Session, store: LocalScanStore, status: str
) -> None:
    scan_id = collected(tx, store, status=status)
    assert ingest(tx, store, scan_id) == status
    assert scan_row(tx, scan_id)["ingested"] is False
    assert rows(tx, "findings", scan_id) == []


def test_another_orgs_scan_is_not_found(db_rollback: Session, store: LocalScanStore) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_B))
    scan_id = uuid.uuid4()
    db_rollback.execute(
        SCAN,
        {
            "id": scan_id,
            "org": ORG_B,
            "provider": "m365",
            "status": "collected",
            "prefix": output_prefix(ORG_B, scan_id, 1),
        },
    )
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    with pytest.raises(ScanNotFoundError):
        ingest(db_rollback, store, scan_id)
    with pytest.raises(ScanNotFoundError):
        ingest(db_rollback, store, uuid.uuid4())
