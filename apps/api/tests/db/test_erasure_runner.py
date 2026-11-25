"""The erasure runner (operator-portal spec, "Erasure"; ADR-017, "Erase"; #502).

As atesta_owner, it executes an approved, uncancelled request once its closure date has passed,
through the one erasure implementation; it marks the request executed with its receipt and writes
`erasure.executed` to the operator trail, in the same transaction. Anything else is refused.
"""

import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import URL, Connection, Engine, text

from .test_members import org_with
from .test_org_closure import _request_closure


@pytest.fixture
def owner(superuser: Engine) -> Iterator[Connection]:
    with superuser.connect() as conn:
        transaction = conn.begin()
        conn.exec_driver_sql("SET LOCAL ROLE atesta_owner")
        try:
            yield conn
        finally:
            transaction.rollback()


def _staff(superuser: Engine) -> uuid.UUID:
    staff = uuid.uuid4()
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO operator_staff (id, cognito_sub, email, role)"
                " VALUES (:i, :s, :e, 'admin')"
            ),
            {"i": staff, "s": f"sub-{staff}", "e": f"{staff}@atesta.test"},
        )
    return staff


def _closed_org(client: TestClient, superuser: Engine, days_ago: int) -> uuid.UUID:
    org, _ = org_with(client, superuser)
    _request_closure(superuser, org, days_ago=days_ago)
    return uuid.UUID(org)


def _request(
    superuser: Engine, org: uuid.UUID, *, approved: bool = True, cancelled: bool = False
) -> uuid.UUID:
    request, by, second = uuid.uuid4(), _staff(superuser), _staff(superuser)
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO erasure_requests (id, organization_id, requested_by)"
                " VALUES (:i, :o, :b)"
            ),
            {"i": request, "o": org, "b": by},
        )
        if approved:
            conn.execute(
                text(
                    "UPDATE erasure_requests SET approved_by = :a, approved_at = now()"
                    " WHERE id = :i"
                ),
                {"a": second, "i": request},
            )
        if cancelled:
            conn.execute(
                text(
                    "UPDATE erasure_requests SET cancelled_by = requested_by,"
                    " cancelled_at = now() WHERE id = :i"
                ),
                {"i": request},
            )
    return request


def test_a_request_that_is_unknown_unapproved_or_cancelled_is_refused(
    client: TestClient, superuser: Engine, owner: Connection
) -> None:
    from atesta_api.modules.identity.api import ErasureRefusedError, run_erasure_request

    org = _closed_org(client, superuser, days_ago=31)  # due: only the request can refuse
    cancelled = _request(superuser, org, approved=False, cancelled=True)
    for request, refusal in (
        (uuid.uuid4(), "no erasure request"),
        (cancelled, "cancelled"),
        (_request(superuser, org, approved=False), "not approved"),  # one open per organization
    ):
        with pytest.raises(ErasureRefusedError, match=refusal), owner.begin_nested():
            run_erasure_request(owner, request, execute=True)
    assert owner.scalar(text("SELECT count(*) FROM organizations WHERE id = :o"), {"o": org}) == 1


def test_an_approved_request_waits_for_the_closure_date(
    client: TestClient, superuser: Engine, owner: Connection
) -> None:
    from atesta_api.modules.identity.api import (
        ErasureRefusedError,
        due_erasure_requests,
        run_erasure_request,
    )

    request = _request(superuser, _closed_org(client, superuser, days_ago=10))
    assert request not in due_erasure_requests(owner)
    with pytest.raises(ErasureRefusedError, match="not due"):
        run_erasure_request(owner, request, execute=True)


def test_an_approved_due_request_erases_once_with_a_receipt_and_a_trail_row(
    client: TestClient, superuser: Engine, owner: Connection
) -> None:
    from atesta_api.modules.identity.api import (
        ErasureRefusedError,
        due_erasure_requests,
        run_erasure_request,
    )

    org = _closed_org(client, superuser, days_ago=31)
    request = _request(superuser, org)
    assert request in due_erasure_requests(owner)

    dry = run_erasure_request(owner, request, execute=False)
    assert dry.receipt_id is None and dry.rows["organizations"] == 1
    executed = owner.scalar(
        text("SELECT executed_at FROM erasure_requests WHERE id = :i"), {"i": request}
    )
    assert executed is None  # a dry run changes nothing

    done = run_erasure_request(owner, request, execute=True)
    assert done.organization_id == org and done.rows == dry.rows
    assert owner.scalar(text("SELECT count(*) FROM organizations WHERE id = :o"), {"o": org}) == 0
    row = owner.execute(
        text("SELECT executed_at, receipt_id FROM erasure_requests WHERE id = :i"), {"i": request}
    ).one()
    assert row.executed_at is not None and row.receipt_id == done.receipt_id
    receipt = owner.execute(
        text("SELECT organization_id, note FROM erasure_receipts WHERE id = :r"),
        {"r": done.receipt_id},
    ).one()
    assert receipt.organization_id == org and str(request) in receipt.note
    trail = owner.execute(
        text(
            "SELECT staff_id, staff_role, organization_id, target_id, reason, metadata"
            " FROM operator_audit_events WHERE action = 'erasure.executed' AND target_id = :t"
        ),
        {"t": str(request)},
    ).one()
    assert (trail.staff_id, trail.staff_role, trail.reason) == (None, None, None)
    assert trail.organization_id == org
    assert trail.metadata == {"receipt_id": str(done.receipt_id)}
    assert request not in due_erasure_requests(owner)
    with pytest.raises(ErasureRefusedError, match="already executed"):
        run_erasure_request(owner, request, execute=True)


def _run(monkeypatch: pytest.MonkeyPatch, database: URL, *args: str) -> int:
    from atesta_api.ops import erase

    url = database.render_as_string(hide_password=False)
    monkeypatch.setenv("ATESTA_MIGRATION_DATABASE_URL", url)
    monkeypatch.setenv("ATESTA_DB_SSLMODE", "disable")
    monkeypatch.setattr("sys.argv", ["erase", *args])
    with pytest.raises(SystemExit) as exited:
        erase.main()
    return int(exited.value.code or 0)


def _events(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


def test_the_scheduled_run_executes_only_due_approved_requests(
    client: TestClient,
    superuser: Engine,
    database: URL,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    due = _request(superuser, _closed_org(client, superuser, days_ago=31))
    undue = _request(superuser, _closed_org(client, superuser, days_ago=5))
    unapproved = _request(superuser, _closed_org(client, superuser, days_ago=31), approved=False)

    assert _run(monkeypatch, database, "--pending", "--execute") == 0
    events = _events(capsys.readouterr().out)
    executed = [e["request"] for e in events if e["event"] == "erasure.executed"]
    assert str(due) in executed
    assert str(undue) not in executed and str(unapproved) not in executed
    assert events[-1]["event"] == "erasure.run" and events[-1]["status"] == "finished"
    with superuser.connect() as conn:
        done = conn.execute(
            text("SELECT id FROM erasure_requests WHERE executed_at IS NOT NULL")
        ).scalars()
        assert due in set(done) and undue not in set(done)


def test_a_command_without_an_approved_request_refuses_and_reports_the_failure(
    client: TestClient,
    superuser: Engine,
    database: URL,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    org = _closed_org(client, superuser, days_ago=31)
    unapproved = _request(superuser, org, approved=False)
    assert _run(monkeypatch, database, "--request", str(unapproved), "--execute") == 2
    captured = capsys.readouterr()
    assert "not approved" in captured.err
    assert _events(captured.out)[-1] == {"event": "erasure.run", "status": "failed"}
    with superuser.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM organizations WHERE id = :o"), {"o": org})
