"""Scans to controls to scores, and scan evidence (scanner-connectors spec). Synthetic catalog."""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from atesta_api.modules.connections.api import create_connection, disconnect_connection
from atesta_api.modules.evidence.api import ScanOutputFile, register_scan_output
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_api.modules.scanning.api import (
    FixtureRunner,
    LocalScanStore,
    ScanJob,
    ingest_scan,
    latest_check_results,
    output_prefix,
    rescore_reviews,
    snapshot_scores,
)
from atesta_core.manifest import build_manifest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from .conftest import ORG_A

FIXTURES = Path(__file__).resolve().parents[4] / "scanner" / "fixtures" / "synthetic"
P = "prowler"
TENANT = {"m365": "11111111-1111-4111-8111-111111111111", "google_workspace": "C0fixture1"}
LISTED = {
    "m365": [
        "entra_admin_consent_workflow_enabled",
        "entra_admin_users_cloud_only",
        "entra_admin_users_mfa_enabled",
        "exchange_external_email_tagging_enabled",
        "exchange_mailbox_audit_bypass_disabled",
        "exchange_transport_rules_whitelist_disabled",
    ],
    "google_workspace": [
        "calendar_external_invitations_warning",
        "calendar_external_sharing_primary_calendar",
        "chat_apps_installation_disabled",
        "chat_external_file_sharing_disabled",
    ],
}
# Controls and the m365 fixture: mfa PASS, cloud_only FAIL, consent only a muted FAIL (manual),
# audit_bypass MANUAL, tagging PASS, transport_rules no finding (not evaluated).
CATALOG = """
INSERT INTO frameworks (key, name, version, jurisdiction, source, license_notes, status,
  catalog_version) VALUES ('fw_scan', 'S', '1', 'EU', 'src', 'test', 'released', 'r1');
INSERT INTO controls (key, title_es, title_en, description_es, description_en, manual,
  retired_at) VALUES
 ('scan.mfa', 't', 't', 'd', 'd', false, NULL), ('scan.cloud', 't', 't', 'd', 'd', false, NULL),
 ('scan.mixed', 't', 't', 'd', 'd', false, NULL),
 ('scan.reviews', 't', 't', 'd', 'd', false, NULL),
 ('scan.google', 't', 't', 'd', 'd', false, NULL),
 ('scan.paper', 't', 't', 'd', 'd', true, NULL),
 ('scan.retired', 't', 't', 'd', 'd', false, now());
INSERT INTO checks (engine, check_id, engine_version, retired_at) VALUES
 ('prowler', 'entra_admin_users_mfa_enabled', '5.49.0', NULL),
 ('prowler', 'entra_admin_users_cloud_only', '5.49.0', NULL),
 ('prowler', 'exchange_transport_rules_whitelist_disabled', '5.49.0', NULL),
 ('prowler', 'exchange_mailbox_audit_bypass_disabled', '5.49.0', NULL),
 ('prowler', 'exchange_external_email_tagging_enabled', '5.49.0', NULL),
 ('prowler', 'entra_admin_consent_workflow_enabled', '5.49.0', now()),
 ('prowler', 'calendar_external_sharing_primary_calendar', '5.49.0', NULL);
INSERT INTO control_checks (control_key, engine, check_id, retired_at) VALUES
 ('scan.mfa', 'prowler', 'entra_admin_users_mfa_enabled', NULL),
 ('scan.mfa', 'prowler', 'exchange_transport_rules_whitelist_disabled', now()),
 ('scan.mfa', 'prowler', 'entra_admin_consent_workflow_enabled', NULL),
 ('scan.cloud', 'prowler', 'entra_admin_users_cloud_only', NULL),
 ('scan.mixed', 'prowler', 'entra_admin_users_mfa_enabled', NULL),
 ('scan.mixed', 'prowler', 'exchange_transport_rules_whitelist_disabled', NULL),
 ('scan.reviews', 'prowler', 'exchange_mailbox_audit_bypass_disabled', NULL),
 ('scan.reviews', 'prowler', 'exchange_external_email_tagging_enabled', NULL),
 ('scan.google', 'prowler', 'calendar_external_sharing_primary_calendar', NULL),
 ('scan.paper', 'prowler', 'entra_admin_users_mfa_enabled', NULL),
 ('scan.retired', 'prowler', 'entra_admin_users_mfa_enabled', NULL);
INSERT INTO requirements (framework_key, code, title_es, source) VALUES
 ('fw_scan', 'S-1', 't', 's'), ('fw_scan', 'S-2', 't', 's'), ('fw_scan', 'S-3', 't', 's'),
 ('fw_scan', 'S-4', 't', 's'), ('fw_scan', 'S-5', 't', 's'), ('fw_scan', 'S-6', 't', 's');
INSERT INTO mappings (framework_key, requirement_code, control_key, rationale, source) VALUES
 ('fw_scan', 'S-1', 'scan.mfa', 'r', 's'), ('fw_scan', 'S-2', 'scan.cloud', 'r', 's'),
 ('fw_scan', 'S-3', 'scan.mixed', 'r', 's'), ('fw_scan', 'S-4', 'scan.reviews', 'r', 's'),
 ('fw_scan', 'S-5', 'scan.google', 'r', 's'), ('fw_scan', 'S-6', 'scan.paper', 'r', 's');
"""
SCAN = text(
    "INSERT INTO scans (id, organization_id, connection_id, provider, trigger, status, engine,"
    " engine_version, output_prefix, attempts) VALUES (:id, :org, :conn, :provider, 'user',"
    " 'collected', 'prowler', '5.49.0', :prefix, 1)"
)
M365_CONNECTION = uuid.UUID("cccccccc-0000-4000-8000-000000000365")
GOOGLE_CONNECTION = uuid.UUID("cccccccc-0000-4000-8000-0000000000aa")


@pytest.fixture(scope="module", autouse=True)
def catalog(superuser: Engine, probe: object) -> None:
    with superuser.begin() as conn:
        conn.exec_driver_sql(CATALOG)


@pytest.fixture(autouse=True)
def dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATESTA_ENV", "test")


@pytest.fixture
def tx(app_engine: Engine, probe: object) -> Iterator[Session]:
    """REPEATABLE READ transaction in org A's context, rolled back at the end."""
    with app_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        enter_org_context(session, ORG_A, ContextReason.JOB)
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


@pytest.fixture
def store(tmp_path: Path) -> LocalScanStore:
    return LocalScanStore(tmp_path / "scans")


def ingested(
    session: Session,
    store: LocalScanStore,
    provider: str,
    connection: uuid.UUID,
    at: datetime,
    ocsf: bytes | None = None,
    scan_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """An ingested scan; at is its ingested_at, since one test transaction has one now()."""
    scan_id = scan_id or uuid.uuid4()
    prefix = output_prefix(ORG_A, scan_id, 1)
    if ocsf is None:
        FixtureRunner(store, FIXTURES).run(ScanJob(ORG_A, scan_id, 1, provider))
    else:
        store.write(prefix + "prowler.ocsf.json", ocsf)
        store.write(prefix + "manifest.json", build_manifest({"prowler.ocsf.json": ocsf}))
    session.execute(
        SCAN,
        {"id": scan_id, "org": ORG_A, "conn": connection, "provider": provider, "prefix": prefix},
    )
    status = ingest_scan(
        session,
        scan_id,
        store=store,
        tenant=TENANT[provider],
        listed=LISTED[provider],
        excluded={},
    )
    assert status in ("succeeded", "partial")
    session.execute(
        text("UPDATE scans SET ingested_at = :at WHERE id = :id"), {"at": at, "id": scan_id}
    )
    return scan_id


def mfa_failing() -> bytes:
    findings = json.loads((FIXTURES / "m365" / "scan.ocsf.json").read_bytes())
    assert findings[0]["metadata"]["event_code"] == "entra_admin_users_mfa_enabled"
    findings[0]["status_code"] = "FAIL"
    return json.dumps(findings).encode()


def snapshot(session: Session, scan_id: uuid.UUID) -> dict[str, Any]:
    query = text(
        "SELECT score, requirement_results FROM score_snapshots"
        " WHERE framework_key = 'fw_scan' AND scan_id = :s"
    )
    row = session.execute(query, {"s": scan_id}).one()
    return {"score": float(row.score), "requirements": row.requirement_results}


T0 = datetime(2026, 11, 1, tzinfo=UTC)
M365_ONLY = {"S-1": "pass", "S-2": "fail", "S-3": "manual", "S-4": "manual", "S-5": "manual"}


def test_a_scan_scores_every_released_framework(tx: Session, store: LocalScanStore) -> None:
    scan_id = ingested(tx, store, "m365", M365_CONNECTION, T0)
    created = snapshot_scores(tx, scan_id)
    assert snapshot(tx, scan_id) == {"score": 50.0, "requirements": {**M365_ONLY, "S-6": "manual"}}
    # Retried job: same snapshots, nothing new.
    assert snapshot_scores(tx, scan_id) == created
    count = text("SELECT count(*) FROM score_snapshots WHERE scan_id = :s")
    assert tx.execute(count, {"s": scan_id}).scalar_one() == len(created)


def test_one_connections_scan_never_erases_anothers(tx: Session, store: LocalScanStore) -> None:
    ingested(tx, store, "m365", M365_CONNECTION, T0)
    google = ingested(tx, store, "google_workspace", GOOGLE_CONNECTION, T0 + timedelta(hours=1))
    snapshot_scores(tx, google)
    assert snapshot(tx, google) == {
        "score": 66.7,
        "requirements": {**M365_ONLY, "S-5": "pass", "S-6": "manual"},
    }


def test_scores_are_as_of_the_scan_so_a_retry_gives_the_same_snapshot(
    tx: Session, store: LocalScanStore
) -> None:
    first = ingested(tx, store, "m365", M365_CONNECTION, T0)
    google = ingested(tx, store, "google_workspace", GOOGLE_CONNECTION, T0 + timedelta(hours=1))
    later = ingested(tx, store, "m365", M365_CONNECTION, T0 + timedelta(hours=2), mfa_failing())
    snapshot_scores(tx, later)
    snapshot_scores(tx, google)  # runs after the later scan, still sees the first m365 scan
    snapshot_scores(tx, first)  # the google scan came after it: not seen
    assert snapshot(tx, later)["requirements"]["S-1"] == "fail"
    assert snapshot(tx, google)["requirements"] == {**M365_ONLY, "S-5": "pass", "S-6": "manual"}
    assert snapshot(tx, first)["requirements"]["S-5"] == "manual"
    # Another connection's latest scan is the newest one before this scan, not the oldest.
    google_next = ingested(
        tx, store, "google_workspace", GOOGLE_CONNECTION, T0 + timedelta(hours=3)
    )
    snapshot_scores(tx, google_next)
    assert snapshot(tx, google_next)["requirements"]["S-1"] == "fail"


def test_a_scans_own_connection_is_that_scan_even_on_a_timestamp_tie(
    tx: Session, store: LocalScanStore
) -> None:
    scan_id = uuid.UUID("00000000-0000-4000-8000-000000000001")
    tie = uuid.UUID("ffffffff-0000-4000-8000-000000000001")  # sorts after scan_id
    ingested(tx, store, "m365", M365_CONNECTION, T0, scan_id=scan_id)
    ingested(tx, store, "m365", M365_CONNECTION, T0, mfa_failing(), scan_id=tie)
    assert (P, "entra_admin_users_mfa_enabled", "fail") not in latest_check_results(tx, scan_id)


def test_latest_results_are_one_scan_per_connection(tx: Session, store: LocalScanStore) -> None:
    ingested(tx, store, "m365", M365_CONNECTION, T0)
    later = ingested(tx, store, "m365", M365_CONNECTION, T0 + timedelta(hours=1), mfa_failing())
    results = latest_check_results(tx, later)
    assert len(results) == len(LISTED["m365"])
    assert (P, "entra_admin_users_mfa_enabled", "fail") in results


def test_an_unfinished_or_rejected_scan_is_not_scored(tx: Session) -> None:
    scan_id = uuid.uuid4()
    tx.execute(
        SCAN,
        {"id": scan_id, "org": ORG_A, "conn": M365_CONNECTION, "provider": "m365", "prefix": None},
    )
    assert snapshot_scores(tx, scan_id) == {}


EVIDENCE = text(
    "SELECT e.storage_key, e.kind, e.source_type, e.source_id, e.sha256, e.size_bytes,"
    " e.media_type, e.title, array_agg(l.control_key ORDER BY l.control_key) AS controls"
    " FROM evidence e LEFT JOIN evidence_controls l ON l.evidence_id = e.id"
    " WHERE e.source_id = :s GROUP BY e.id ORDER BY e.storage_key"
)


def test_ingest_registers_the_output_as_evidence_of_every_control_with_a_result(
    tx: Session, store: LocalScanStore
) -> None:
    scan_id = ingested(tx, store, "m365", M365_CONNECTION, T0)
    prefix = output_prefix(ORG_A, scan_id, 1)
    manifest = json.loads(store.read(prefix + "manifest.json"))["files"][0]
    rows = [tuple(r) for r in tx.execute(EVIDENCE, {"s": scan_id})]
    # scan.mixed (a check not evaluated), scan.google (out of scope), scan.paper (manual
    # control) and scan.retired have no result from this scan: no link.
    controls = ["scan.cloud", "scan.mfa", "scan.reviews"]
    assert [r[0] for r in rows] == [prefix + "manifest.json", prefix + "prowler.ocsf.json"]
    assert all(r[1:4] == ("scan_output", "scan", scan_id) for r in rows)
    assert all(r[6:] == ("application/json", r[0].rsplit("/", 1)[1], controls) for r in rows)
    assert rows[1][4:6] == (manifest["sha256"], manifest["size"])
    assert len(rows[0][4]) == 64


def test_a_rejected_scan_registers_no_evidence(tx: Session, store: LocalScanStore) -> None:
    scan_id = uuid.uuid4()
    FixtureRunner(store, FIXTURES, "wrong-tenant.ocsf.json").run(ScanJob(ORG_A, scan_id, 1, "m365"))
    prefix = output_prefix(ORG_A, scan_id, 1)
    row = {"id": scan_id, "org": ORG_A, "conn": M365_CONNECTION, "provider": "m365"}
    tx.execute(SCAN, {**row, "prefix": prefix})
    status = ingest_scan(
        tx, scan_id, store=store, tenant=TENANT["m365"], listed=LISTED["m365"], excluded={}
    )
    assert status == "failed"
    assert tx.execute(EVIDENCE, {"s": scan_id}).all() == []
    assert snapshot_scores(tx, scan_id) == {}


@pytest.mark.parametrize("control", ["scan.retired", "scan.unknown"])
def test_scan_evidence_links_only_active_controls(tx: Session, control: str) -> None:
    scan_id = uuid.uuid4()
    key = f"{output_prefix(ORG_A, scan_id, 1)}manifest.json"
    with pytest.raises(ValueError, match="unknown or retired controls"):
        register_scan_output(
            tx,
            organization_id=ORG_A,
            scan_id=scan_id,
            files=[ScanOutputFile(key, "0" * 64, 1, "application/json")],
            control_keys=["scan.mfa", control],
            collected_at=T0,
        )


# --- human reviews of manual controls (manual-control-review spec, PR 2) -------------------

REVIEW = text(
    "INSERT INTO control_reviews (organization_id, id, control_key, status, rationale,"
    " valid_until, reviewed_by, reviewed_at) VALUES (:org, gen_random_uuid(), :control, :status,"
    " 'acta', :until, gen_random_uuid(), :at)"
)


def review(
    session: Session,
    status: str,
    at: datetime,
    until: datetime | None = None,
    control: str = "scan.paper",
) -> None:
    valid_until = (until or at + timedelta(days=365)).date()
    session.execute(
        REVIEW,
        {"org": ORG_A, "control": control, "status": status, "until": valid_until, "at": at},
    )


@pytest.mark.parametrize(("status", "score"), [("pass", 66.7), ("fail", 33.3)])
def test_a_current_review_decides_its_manual_control(
    tx: Session, store: LocalScanStore, status: str, score: float
) -> None:
    review(tx, status, T0 - timedelta(days=1))
    scan_id = ingested(tx, store, "m365", M365_CONNECTION, T0)
    snapshot_scores(tx, scan_id)
    assert snapshot(tx, scan_id) == {"score": score, "requirements": {**M365_ONLY, "S-6": status}}


def test_the_latest_review_as_of_the_scan_wins(tx: Session, store: LocalScanStore) -> None:
    review(tx, "fail", T0 - timedelta(days=2))
    review(tx, "pass", T0 - timedelta(days=1))
    review(tx, "fail", T0 + timedelta(days=1))  # after the scan: not part of its snapshot
    scan_id = ingested(tx, store, "m365", M365_CONNECTION, T0)
    snapshot_scores(tx, scan_id)
    assert snapshot(tx, scan_id)["requirements"]["S-6"] == "pass"


def test_an_expired_review_leaves_the_control_manual(tx: Session, store: LocalScanStore) -> None:
    review(tx, "fail", T0 - timedelta(days=400), until=T0 - timedelta(days=300))
    review(tx, "pass", T0 - timedelta(days=30), until=T0 - timedelta(days=1))  # latest, expired
    scan_id = ingested(tx, store, "m365", M365_CONNECTION, T0)
    snapshot_scores(tx, scan_id)
    assert snapshot(tx, scan_id)["requirements"]["S-6"] == "manual"


def test_a_review_never_decides_an_automated_control(tx: Session, store: LocalScanStore) -> None:
    review(tx, "pass", T0 - timedelta(days=1), control="scan.cloud")
    scan_id = ingested(tx, store, "m365", M365_CONNECTION, T0)
    snapshot_scores(tx, scan_id)
    assert snapshot(tx, scan_id)["requirements"]["S-2"] == "fail"


def chain(session: Session, scan_id: uuid.UUID) -> list[tuple[uuid.UUID, uuid.UUID | None, str]]:
    """Every fw_scan snapshot of the scan, oldest first: (id, supersedes_id, S-6 result)."""
    rows = session.execute(
        text(
            "SELECT id, supersedes_id, requirement_results ->> 'S-6' FROM score_snapshots"
            " WHERE framework_key = 'fw_scan' AND scan_id = :s ORDER BY computed_at, supersedes_id"
            " NULLS FIRST"
        ),
        {"s": scan_id},
    )
    return [(i, s, r) for i, s, r in rows]


def test_rescoring_after_a_review_corrects_the_latest_scans_snapshot(
    tx: Session, store: LocalScanStore
) -> None:
    older = ingested(tx, store, "m365", M365_CONNECTION, T0 - timedelta(days=7))
    latest = ingested(tx, store, "m365", M365_CONNECTION, T0)
    snapshot_scores(tx, older)
    snapshot_scores(tx, latest)
    review(tx, "pass", T0 + timedelta(hours=1))
    created = rescore_reviews(tx, ORG_A, as_of=T0 + timedelta(hours=2))
    assert set(created) == {"fw_scan"}
    (original, _, before), (correction, supersedes, after) = chain(tx, latest)
    assert (before, after, supersedes, correction) == (
        "manual",
        "pass",
        original,
        created["fw_scan"],
    )
    assert len(chain(tx, older)) == 1  # history stays as it was recorded

    review(tx, "fail", T0 + timedelta(hours=3))
    again = rescore_reviews(tx, ORG_A, as_of=T0 + timedelta(hours=4))
    tip = tx.execute(
        text(
            "SELECT supersedes_id, requirement_results ->> 'S-6' FROM score_snapshots WHERE id = :i"
        ),
        {"i": again["fw_scan"]},
    ).one()
    assert tuple(tip) == (correction, "fail")  # one linear chain: the new tip supersedes the last


def test_rescoring_without_an_ingested_scan_does_nothing(tx: Session) -> None:
    review(tx, "pass", T0)
    assert rescore_reviews(tx, ORG_A, as_of=T0 + timedelta(hours=1)) == {}


# --- ended connections (scanner-connectors spec: results of active connections only) -------


def _connection(session: Session, provider: str) -> uuid.UUID:
    created = create_connection(
        session,
        organization_id=ORG_A,
        provider=provider,
        display_name=provider,
        created_by=uuid.uuid4(),
    )
    return created.id


def test_a_disconnected_connections_results_leave_the_score(
    tx: Session, store: LocalScanStore
) -> None:
    m365, google = _connection(tx, "m365"), _connection(tx, "google_workspace")
    ingested(tx, store, "m365", m365, T0)
    disconnect_connection(tx, m365)
    later = ingested(tx, store, "google_workspace", google, T0 + timedelta(days=30))
    assert not any(
        c.startswith(("entra", "exchange")) for _, c, _ in latest_check_results(tx, later)
    )
    snapshot_scores(tx, later)
    assert snapshot(tx, later)["requirements"]["S-1"] == "manual"  # was 'pass' from the old tenant


def test_a_stale_fail_from_a_disconnected_connection_clears_after_reconnecting(
    tx: Session, store: LocalScanStore
) -> None:
    old = _connection(tx, "m365")
    ingested(tx, store, "m365", old, T0, mfa_failing())
    disconnect_connection(tx, old)
    fixed = ingested(tx, store, "m365", _connection(tx, "m365"), T0 + timedelta(days=1))
    snapshot_scores(tx, fixed)
    assert snapshot(tx, fixed)["requirements"]["S-1"] == "pass"  # was 'fail' forever


def test_a_connection_not_yet_active_still_counts(tx: Session, store: LocalScanStore) -> None:
    m365, google = _connection(tx, "m365"), _connection(tx, "google_workspace")  # pending setup
    ingested(tx, store, "m365", m365, T0)
    later = ingested(tx, store, "google_workspace", google, T0 + timedelta(hours=1))
    snapshot_scores(tx, later)
    assert snapshot(tx, later)["requirements"]["S-1"] == "pass"
