"""Data rules of the operator-portal columns and tables (operator-portal spec, #445).

Trial end, suspension and closure origin on organizations; billing details; erasure requests with
the two-admin rule, the 72-hour cooling-off and the 7-day window. Run as superuser in a rolled
back transaction: these are constraints, so they hold for every role.
"""

import os
import secrets
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from atesta_api.platform.db import make_engine
from sqlalchemy import Connection, Engine, column, insert, table, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError

API_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def su(superuser: Engine, probe: object) -> Iterator[Connection]:
    with superuser.connect() as conn:
        tx = conn.begin()
        try:
            yield conn
        finally:
            tx.rollback()


def _org(conn: Connection, **columns: object) -> uuid.UUID:
    org = uuid.uuid4()
    values = {"id": org, "name": "org", **columns}
    conn.execute(insert(table("organizations", *(column(c) for c in values))).values(values))
    return org


def _refused(conn: Connection, constraint: str, statement: str, **params: object) -> None:
    with pytest.raises(IntegrityError, match=constraint), conn.begin_nested():
        conn.execute(text(statement), params)


def test_a_new_organization_has_a_14_day_trial(su: Connection) -> None:
    org = _org(su)
    created, ends = su.execute(
        text("SELECT created_at, trial_ends_at FROM organizations WHERE id = :o"), {"o": org}
    ).one()
    assert ends - created == timedelta(days=14)


def test_suspension_needs_a_known_reason_and_both_columns(su: Connection) -> None:
    org = _org(su)
    update = "UPDATE organizations SET suspended_at = :at, suspension_reason = :r WHERE id = :o"
    _refused(su, "suspension_together", update, at=None, r="non_payment", o=org)
    _refused(
        su,
        "suspension_together",
        "UPDATE organizations SET suspended_at = now() WHERE id = :o",
        o=org,
    )
    _refused(su, "suspension_reason", update.replace(":at", "now()"), r="angry", o=org)
    for reason in ("non_payment", "contract_ended", "customer_request", "security_review", "other"):
        su.execute(text(update.replace(":at", "now()")), {"r": reason, "o": org})


def test_closure_origin_follows_who_asked(su: Connection) -> None:
    def origin(org: uuid.UUID) -> str | None:
        return su.scalar(text("SELECT closure_origin FROM organizations WHERE id = :o"), {"o": org})

    assert origin(_org(su)) is None
    assert origin(_org(su, closure_requested_at="2026-01-01T00:00:00Z")) == "operator"
    owner = _org(su, closure_requested_at="2026-01-01T00:00:00Z", closure_requested_by=uuid.uuid4())
    assert origin(owner) == "owner"
    su.execute(
        text(
            "UPDATE organizations SET closure_requested_at = NULL, closure_requested_by = NULL"
            " WHERE id = :o"
        ),
        {"o": owner},
    )
    assert origin(owner) is None
    _refused(
        su,
        "closure_by_needs_at",
        "INSERT INTO organizations (id, name, closure_requested_by) VALUES (:o, 'x', :u)",
        o=uuid.uuid4(),
        u=uuid.uuid4(),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("legal_name", ""),
        ("tax_id", "   "),
        ("country", "es"),
        ("country", "ESP"),
        ("city", "x" * 201),
    ],
)
def test_billing_details_refuse_blank_and_malformed_values(
    su: Connection, field: str, value: str
) -> None:
    org = _org(su)
    with pytest.raises(IntegrityError, match="ck_billing_profiles"), su.begin_nested():
        values = {"organization_id": org, field: value}
        su.execute(insert(table("billing_profiles", *(column(c) for c in values))).values(values))


def _staff(conn: Connection, role: str = "admin") -> uuid.UUID:
    staff = uuid.uuid4()
    conn.execute(
        text("INSERT INTO operator_staff (id, cognito_sub, email, role) VALUES (:i, :s, :e, :r)"),
        {"i": staff, "s": f"sub-{staff}", "e": f"{staff}@atesta.test", "r": role},
    )
    return staff


def _request(conn: Connection, by: uuid.UUID, ago: str = "0 hours") -> uuid.UUID:
    request = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO erasure_requests (id, organization_id, requested_by, requested_at)"
            " VALUES (:i, :o, :b, now() - CAST(:ago AS interval))"
        ),
        {"i": request, "o": uuid.uuid4(), "b": by, "ago": ago},
    )
    return request


APPROVE = "UPDATE erasure_requests SET approved_by = :a, approved_at = now() WHERE id = :i"


def test_staff_roles_are_a_closed_list(su: Connection) -> None:
    for role in ("admin", "billing", "support"):
        _staff(su, role)
    with pytest.raises(IntegrityError, match="ck_operator_staff_role"), su.begin_nested():
        _staff(su, "owner")


def test_a_second_admin_approves_at_once(su: Connection) -> None:
    request = _request(su, _staff(su))
    su.execute(text(APPROVE), {"a": _staff(su), "i": request})


def test_the_requester_cannot_approve_within_72_hours(su: Connection) -> None:
    admin = _staff(su)
    request = _request(su, admin, "71 hours")
    _refused(su, "second_admin_or_cooling_off", APPROVE, a=admin, i=request)


def test_the_requester_approves_after_the_72_hour_cooling_off(su: Connection) -> None:
    admin = _staff(su)
    su.execute(text(APPROVE), {"a": admin, "i": _request(su, admin, "73 hours")})


def test_approval_after_7_days_is_refused(su: Connection) -> None:
    request = _request(su, _staff(su), "8 days")
    _refused(su, "approval_window", APPROVE, a=_staff(su), i=request)


def test_approval_and_cancellation_record_a_person_and_a_time(su: Connection) -> None:
    request = _request(su, _staff(su))
    _refused(
        su,
        "approved_together",
        "UPDATE erasure_requests SET approved_at = now() WHERE id = :i",
        i=request,
    )
    _refused(
        su,
        "cancelled_together",
        "UPDATE erasure_requests SET cancelled_by = requested_by WHERE id = :i",
        i=request,
    )


def test_a_cancelled_request_cannot_be_approved(su: Connection) -> None:
    request = _request(su, _staff(su))
    su.execute(
        text(
            "UPDATE erasure_requests SET cancelled_by = requested_by,"
            " cancelled_at = now() - interval '1 minute' WHERE id = :i"
        ),
        {"i": request},
    )
    _refused(su, "not_approved_after_cancel", APPROVE, a=_staff(su), i=request)


def test_only_an_approved_live_request_is_executed_with_its_receipt(su: Connection) -> None:
    request = _request(su, _staff(su))
    receipt = uuid.uuid4()
    su.execute(
        text(
            "INSERT INTO erasure_receipts (id, organization_id, closure_requested_at, note,"
            " row_counts) VALUES (:r, gen_random_uuid(), now(), '', '{}')"
        ),
        {"r": receipt},
    )
    execute = "UPDATE erasure_requests SET executed_at = now(), receipt_id = :r WHERE id = :i"
    _refused(su, "executed_only_approved", execute, r=receipt, i=request)
    su.execute(text(APPROVE), {"a": _staff(su), "i": request})
    _refused(
        su,
        "executed_together",
        "UPDATE erasure_requests SET executed_at = now() WHERE id = :i",
        i=request,
    )
    su.execute(text(execute), {"r": receipt, "i": request})


def test_one_open_request_per_organization(su: Connection) -> None:
    admin = _staff(su)
    first = _request(su, admin)
    org = su.scalar(
        text("SELECT organization_id FROM erasure_requests WHERE id = :i"), {"i": first}
    )
    insert = (
        "INSERT INTO erasure_requests (id, organization_id, requested_by)"
        " VALUES (gen_random_uuid(), :o, :b)"
    )
    _refused(su, "ux_erasure_requests_open", insert, o=org, b=admin)
    su.execute(
        text(
            "UPDATE erasure_requests SET cancelled_by = requested_by, cancelled_at = now()"
            " WHERE id = :i"
        ),
        {"i": first},
    )
    su.execute(text(insert), {"o": org, "b": admin})


def test_the_operator_trail_names_staff_except_for_the_erasure_runner(su: Connection) -> None:
    insert = (
        "INSERT INTO operator_audit_events (id, staff_id, staff_role, action)"
        " VALUES (gen_random_uuid(), :s, :r, :a)"
    )
    su.execute(text(insert), {"s": None, "r": None, "a": "erasure.executed"})
    _refused(su, "staff_unless_runner", insert, s=None, r=None, a="operator.suspended")
    _refused(su, "staff_together", insert, s=_staff(su), r=None, a="operator.suspended")
    _refused(
        su,
        "ck_operator_audit_events_reason",
        insert.replace("action)", "action, reason)").replace(":a)", ":a, :x)"),
        s=None,
        r=None,
        a="erasure.executed",
        x="x" * 501,
    )


def test_existing_organizations_get_a_trial_from_the_migration_and_keep_their_closure(
    superuser: Engine,
) -> None:
    """Upgrade from 0032 with an old organization and an owner closure already in place."""
    admin_url = os.environ["ATESTA_TEST_DATABASE_URL"]
    name = f"atesta_mig_{secrets.token_hex(4)}"
    server = make_engine(make_url(admin_url), sslmode="disable", null_pool=True)
    with server.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    url: URL = make_url(admin_url).set(database=name)
    engine = make_engine(url, sslmode="disable", null_pool=True)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql((API_DIR / "migrations" / "bootstrap.sql").read_text())
        config = Config(str(API_DIR / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
        config.attributes["role"] = "atesta_owner"
        command.upgrade(config, "0032")
        old, closing = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, created_at, closure_requested_at,"
                    " closure_requested_by) VALUES (:a, 'old', now() - interval '1 year', NULL,"
                    " NULL), (:b, 'closing', now() - interval '1 year', now(), gen_random_uuid())"
                ),
                {"a": old, "b": closing},
            )
        command.upgrade(config, "head")
        with engine.connect() as conn:
            rows = dict(
                conn.execute(
                    text(
                        "SELECT id, (trial_ends_at - now() BETWEEN interval '13 days 23 hours'"
                        " AND interval '14 days') AND closure_origin IS NOT DISTINCT FROM"
                        " CASE WHEN id = :b THEN 'owner' END FROM organizations"
                    ),
                    {"b": closing},
                ).all()
            )
        assert rows == {old: True, closing: True}
    finally:
        engine.dispose()
        with server.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
