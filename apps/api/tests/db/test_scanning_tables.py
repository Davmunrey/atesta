"""Scanning tables: one active scan per connection, checked values, append-only results."""

import uuid
from typing import Any

import pytest
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .conftest import ORG_A, ORG_B

CONNECTION = uuid.UUID("cccccccc-0000-4000-8000-000000000001")
SCAN = text(
    "INSERT INTO scans (id, organization_id, connection_id, provider, trigger, status, engine,"
    " engine_version, output_prefix, manifest_sha256, expected_checks, evaluated_checks)"
    " VALUES (:id, :org, :conn, :provider, :trigger, :status, 'prowler', '5.49.0', :prefix,"
    " :sha, :expected, :evaluated)"
)
RESULT = text(
    "INSERT INTO scan_check_results (organization_id, scan_id, engine, check_id, status, reason)"
    " VALUES (:org, :scan, 'prowler', :check, :status, :reason)"
)
FINDING = text(
    "INSERT INTO findings (id, organization_id, scan_id, engine, check_id, status, severity,"
    " service, resource_type, resource_uid, resource_name, region, message) VALUES"
    " (gen_random_uuid(), :org, :scan, 'prowler', 'entra_check', 'fail', 'high', 'entra',"
    " 'User', 'u-1', 'n', 'global', 'm')"
)


def scan(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": uuid.uuid4(),
        "org": ORG_A,
        "conn": CONNECTION,
        "provider": "m365",
        "trigger": "user",
        "status": "queued",
        "prefix": None,
        "sha": None,
        "expected": 149,
        "evaluated": 0,
    }
    return {**base, **overrides}


@pytest.fixture
def tx(db_rollback: Session) -> Session:
    enter_org_context(db_rollback, ORG_A, ContextReason.JOB)
    return db_rollback


def test_a_connection_has_one_queued_or_running_scan(tx: Session) -> None:
    tx.execute(SCAN, scan(status="running"))
    with pytest.raises(DBAPIError, match="uq_scans_one_active_per_connection"):
        tx.execute(SCAN, scan(status="queued"))


def test_finished_scans_free_the_connection(tx: Session) -> None:
    tx.execute(SCAN, scan(status="succeeded"))
    tx.execute(SCAN, scan(status="failed"))
    tx.execute(SCAN, scan(status="queued"))
    tx.execute(SCAN, scan(status="queued", conn=uuid.uuid4()))


def _prefix(org: uuid.UUID, scan_id: uuid.UUID, attempt: str = "1") -> str:
    return f"{org}/scans/{scan_id}/attempt-{attempt}/out/"


def test_output_prefix_belongs_to_its_own_scan(tx: Session) -> None:
    mine = scan(status="collected")
    mine["prefix"] = _prefix(ORG_A, mine["id"], "2")
    tx.execute(SCAN, mine)


REJECTED_SCANS = {
    "unknown provider": ({"provider": "aws"}, "ck_scans_provider"),
    "unknown trigger": ({"trigger": "cron"}, "ck_scans_trigger"),
    "unknown status": ({"status": "done"}, "ck_scans_status"),
    "other org's prefix": ({"prefix": "other-org"}, "ck_scans_output_prefix_in_tenant"),
    "other scan's prefix": ({"prefix": "other-scan"}, "ck_scans_output_prefix_in_tenant"),
    "prefix outside out/": ({"prefix": "escape"}, "ck_scans_output_prefix_in_tenant"),
    "attempt zero": ({"prefix": "attempt-0"}, "ck_scans_output_prefix_in_tenant"),
    "uppercase manifest hash": ({"sha": "A" * 64}, "ck_scans_manifest_sha256_format"),
    "more evaluated than expected": ({"evaluated": 150}, "ck_scans_coverage_bounded"),
    "negative evaluated": ({"evaluated": -1}, "ck_scans_coverage_bounded"),
}


@pytest.mark.parametrize("name", sorted(REJECTED_SCANS))
def test_invalid_scans_are_rejected(tx: Session, name: str) -> None:
    overrides, constraint = REJECTED_SCANS[name]
    row = scan(**overrides)
    prefixes = {
        "other-org": _prefix(ORG_B, row["id"]),
        "other-scan": _prefix(ORG_A, uuid.uuid4()),
        "escape": f"{ORG_A}/scans/{row['id']}/attempt-1/out/../../",
        "attempt-0": _prefix(ORG_A, row["id"], "0"),
    }
    row["prefix"] = prefixes.get(row["prefix"], row["prefix"])
    with pytest.raises(DBAPIError, match=constraint):
        tx.execute(SCAN, row)


RESULTS = {
    "pass without reason": ("pass", None, None),
    "not evaluated, no findings": ("not_evaluated", "no_findings", None),
    "not evaluated, excluded": ("not_evaluated", "excluded", None),
    "fail with a reason": ("fail", "no_findings", "ck_scan_check_results_reason_iff_not_evaluated"),
    "not evaluated without reason": (
        "not_evaluated",
        None,
        "ck_scan_check_results_reason_iff_not_evaluated",
    ),
    "unknown reason": ("not_evaluated", "lost", "ck_scan_check_results_reason"),
    "unknown status": ("skipped", None, "ck_scan_check_results_status"),
}


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_check_results_carry_a_reason_only_when_not_evaluated(tx: Session, name: str) -> None:
    status, reason, constraint = RESULTS[name]
    row = scan(status="running")
    tx.execute(SCAN, row)
    params = {"org": ORG_A, "scan": row["id"], "check": "entra_x", "status": status}
    if constraint is None:
        tx.execute(RESULT, {**params, "reason": reason})
    else:
        with pytest.raises(DBAPIError, match=constraint):
            tx.execute(RESULT, {**params, "reason": reason})


@pytest.mark.parametrize("statement", ["UPDATE {t} SET engine = engine", "DELETE FROM {t}"])
@pytest.mark.parametrize("table", ["scan_check_results", "findings"])
def test_results_and_findings_are_append_only(tx: Session, table: str, statement: str) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        tx.execute(text(statement.format(t=table)))


def test_scans_change_status_but_are_never_deleted(tx: Session) -> None:
    row = scan()
    tx.execute(SCAN, row)
    tx.execute(text("UPDATE scans SET status = 'running' WHERE id = :i"), {"i": row["id"]})
    with pytest.raises(DBAPIError, match="permission denied"), tx.begin_nested():
        tx.execute(text("DELETE FROM scans"))


def test_results_and_findings_name_a_scan_of_the_same_org(tx: Session, superuser: Engine) -> None:
    theirs = scan(org=ORG_B)
    with superuser.begin() as conn:
        conn.execute(SCAN, theirs)
    errors = []
    for statement in (RESULT, FINDING):
        for scan_id in (theirs["id"], uuid.uuid4()):  # B's real id must look like a random one
            params = {"org": ORG_A, "scan": scan_id, "check": "c", "status": "pass"}
            with pytest.raises(DBAPIError) as exc, tx.begin_nested():
                tx.execute(statement, {**params, "reason": None})
            errors.append(str(exc.value.orig).splitlines()[0])
    assert errors[0] == errors[1] and errors[2] == errors[3]
    assert all("foreign key" in e for e in errors)
