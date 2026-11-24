"""Module functions the operator service calls (operator-portal spec, "Module functions").

Each runs as `atesta_operator` on real Postgres, so a column outside ADR-012 amendment 8's list,
or an ORM default the role cannot write, fails here as it would in production. Every test seeds
and acts in one superuser transaction that switches role with SET LOCAL ROLE and rolls back.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from atesta_api.modules.connections.api import health_counts
from atesta_api.modules.identity.api import (
    PAGE_SIZE,
    OperatorError,
    OrganizationFilters,
    api_key_counts,
    cancel_operator_closure,
    invitation_counts,
    last_activity,
    member_counts,
    organization_metadata,
    organization_rows,
    reactivate,
    start_operator_closure,
    suspend,
)
from atesta_api.modules.scanning.api import scan_activity
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

OP = "SET LOCAL ROLE atesta_operator"


@pytest.fixture
def seed(superuser: Engine, probe: object) -> Iterator[Session]:
    """A superuser session for seeding; `as_operator` switches it. Always rolled back."""
    with superuser.connect() as conn:
        tx = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            tx.rollback()


def as_operator(session: Session) -> Session:
    session.execute(text(OP))
    return session


def sql(session: Session, statement: str, **params: Any) -> Any:
    return session.execute(text(statement), params)


NOW = datetime.now(UTC)


def org(session: Session, name: str, **columns: Any) -> uuid.UUID:
    """An organization; `columns` may set locale, suspension and closure columns."""
    org_id = uuid.uuid4()
    values = {
        "locale": "es",
        "suspended_at": None,
        "suspension_reason": None,
        "closure_requested_at": None,
        **columns,
    }
    sql(
        session,
        "INSERT INTO organizations (id, name, locale, suspended_at, suspension_reason,"
        " closure_requested_at) VALUES (:id, :name, :locale, :suspended_at, :suspension_reason,"
        " :closure_requested_at)",
        id=org_id,
        name=name,
        **values,
    )
    return org_id


def user(session: Session, organization: uuid.UUID, role: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    sql(
        session,
        "INSERT INTO users (id, cognito_sub, email, email_verified) VALUES (:u, :s, :e, true)",
        u=user_id,
        s=f"sub-{user_id}",
        e=f"{user_id}@example.com",
    )
    sql(
        session,
        "INSERT INTO memberships (organization_id, user_id, role, access_expires_at)"
        " VALUES (:o, :u, :r, :x)",
        o=organization,
        u=user_id,
        r=role,
        x=NOW + timedelta(days=9) if role == "auditor" else None,
    )
    return user_id


def invitation(session: Session, organization: uuid.UUID, by: uuid.UUID, state: str) -> None:
    sql(
        session,
        "INSERT INTO invitations (id, organization_id, email, role, token_sha256, invited_by,"
        " expires_at, accepted_at, revoked_at) VALUES (gen_random_uuid(), :o, 'x@example.com',"
        " 'member', md5(random()::text), :u, :x, :a, :r)",
        o=organization,
        u=by,
        x=NOW + timedelta(days=-1 if state == "expired" else 7),
        a=NOW if state == "accepted" else None,
        r=NOW if state == "revoked" else None,
    )


def connection(session: Session, organization: uuid.UUID, by: uuid.UUID, status: str) -> None:
    sql(
        session,
        "INSERT INTO connections (id, organization_id, provider, status, display_name,"
        " external_tenant_id, created_by) VALUES (gen_random_uuid(), :o, 'm365', :s,"
        " 'Tenant name', gen_random_uuid()::text, :u)",
        o=organization,
        s=status,
        u=by,
    )


def scan(session: Session, organization: uuid.UUID, status: str, age_days: int) -> None:
    queued = NOW - timedelta(days=age_days)
    sql(
        session,
        "INSERT INTO scans (id, organization_id, connection_id, provider, trigger, status, engine,"
        " engine_version, queued_at, finished_at) VALUES (gen_random_uuid(), :o,"
        " gen_random_uuid(), 'm365', 'schedule', :s, 'prowler', '5.52.0', :q, :f)",
        o=organization,
        s=status,
        q=queued,
        f=None if status in ("queued", "running") else queued,
    )


def api_key(
    session: Session, organization: uuid.UUID, by: uuid.UUID, state: str, calls: int
) -> None:
    token = sql(
        session,
        "INSERT INTO api_tokens (id, organization_id, name, prefix, token_sha256, created_by,"
        " created_at, expires_at, revoked_at, revoked_by) VALUES (gen_random_uuid(), :o, 'k',"
        " 'atesta_abcde', md5(random()::text) || md5(random()::text), :u, :c, :x, :r, :rb)"
        " RETURNING id",
        o=organization,
        u=by,
        c=NOW - timedelta(days=40),
        x=NOW + timedelta(days=-1 if state == "expired" else 30),
        r=NOW if state == "revoked" else None,
        rb=by if state == "revoked" else None,
    ).scalar_one()
    for age in range(calls):  # 0, 20, 40 days ago: two of three within 30 days
        sql(
            session,
            "INSERT INTO api_token_usage (id, organization_id, token_id, at, method, route)"
            " VALUES (gen_random_uuid(), :o, :t, :at, 'GET', '/api/v1/key')",
            o=organization,
            t=token,
            at=NOW - timedelta(days=age * 20),
        )


def event(session: Session, organization: uuid.UUID, action: str, days_ago: int) -> None:
    sql(
        session,
        "INSERT INTO audit_events (id, organization_id, action, target_type, target_id,"
        " occurred_at) VALUES (gen_random_uuid(), :o, :a, 'organization', 'x', :at)",
        o=organization,
        a=action,
        at=NOW - timedelta(days=days_ago),
    )


# --- reads -----------------------------------------------------------------------------------


@pytest.fixture
def pair(seed: Session) -> tuple[uuid.UUID, uuid.UUID]:
    """Two seeded organizations with different counts, so a cross-organization mix shows."""
    a = org(seed, f"Zeta {uuid.uuid4().hex[:6]}")
    b = org(seed, f"Alpha {uuid.uuid4().hex[:6]}")
    owner_a, owner_b = user(seed, a, "owner"), user(seed, b, "owner")
    user(seed, a, "admin")
    user(seed, a, "member")
    user(seed, a, "member")
    user(seed, b, "auditor")
    for state in ("pending", "pending", "expired", "accepted", "revoked"):
        invitation(seed, a, owner_a, state)
    invitation(seed, b, owner_b, "pending")
    connection(seed, a, owner_a, "active")
    connection(seed, a, owner_a, "disconnected")
    connection(seed, b, owner_b, "active")
    connection(seed, b, owner_b, "revoked")
    scan(seed, a, "succeeded", 2)
    scan(seed, a, "failed", 1)
    scan(seed, a, "succeeded", 45)
    scan(seed, b, "queued", 0)
    api_key(seed, a, owner_a, "active", calls=3)
    api_key(seed, a, owner_a, "revoked", calls=0)
    api_key(seed, b, owner_b, "expired", calls=1)
    event(seed, a, "requirement.assessed", 3)
    event(seed, a, "operator.plan_changed", 0)  # staff activity is not customer activity
    event(seed, b, "org.created", 9)
    return a, b


def test_counts_are_per_organization_with_no_mix(
    seed: Session, pair: tuple[uuid.UUID, ...]
) -> None:
    a, b = pair
    since = datetime.now(UTC) - timedelta(days=30)
    session = as_operator(seed)
    assert member_counts(session, [a, b]) == {
        a: {"owner": 1, "admin": 1, "member": 2},
        b: {"owner": 1, "auditor": 1},
    }
    assert invitation_counts(session, [a, b]) == {a: 2, b: 1}
    keys = api_key_counts(session, [a, b], since=since)
    assert (keys[a].active, keys[a].calls, keys[b].active, keys[b].calls) == (1, 2, 0, 1)
    activity = last_activity(session, [a, b])
    assert timedelta(days=2) < datetime.now(UTC) - activity[a] < timedelta(days=4)
    assert timedelta(days=8) < datetime.now(UTC) - activity[b] < timedelta(days=10)


def test_an_organization_with_nothing_is_absent_or_zero(seed: Session) -> None:
    empty = org(seed, "Empty")
    session = as_operator(seed)
    assert member_counts(session, [empty]) == {}
    assert invitation_counts(session, [empty]) == {}
    assert last_activity(session, [empty]) == {}
    assert health_counts(session, [empty]) == {}
    assert scan_activity(session, [empty], since=datetime.now(UTC)) == {}


def test_connection_health_by_provider_and_status(
    seed: Session, pair: tuple[uuid.UUID, ...]
) -> None:
    a, b = pair
    pending = org(seed, "Pending")
    connection(seed, pending, user(seed, pending, "owner"), "verifying")
    health = health_counts(as_operator(seed), [a, b, pending])
    assert health[a].by_provider == {"m365": {"active": 1, "disconnected": 1}}
    assert (health[a].health, health[a].in_use) == ("ok", 1)
    assert (health[b].health, health[b].in_use) == ("attention", 2)
    assert health[pending].health == "pending"


def test_health_of_every_organization_feeds_the_list_filter(
    seed: Session, pair: tuple[uuid.UUID, ...]
) -> None:
    a, b = pair
    every = health_counts(as_operator(seed), None)
    assert {a, b} <= set(every)


def test_scan_activity_counts_the_window_and_the_last_finish(
    seed: Session, pair: tuple[uuid.UUID, ...]
) -> None:
    a, b = pair
    since = datetime.now(UTC) - timedelta(days=30)
    scans = scan_activity(as_operator(seed), [a, b], since=since)
    assert scans[a].by_status == {"succeeded": 1, "failed": 1}
    assert scans[a].last_finished is not None
    assert timedelta(hours=23) < datetime.now(UTC) - scans[a].last_finished < timedelta(days=2)
    assert (scans[b].by_status, scans[b].last_finished) == ({"queued": 1}, None)


def test_metadata_holds_the_listed_fields_only(seed: Session) -> None:
    target = org(seed, "Meta", locale="en")
    meta = organization_metadata(as_operator(seed), target)
    assert meta is not None
    assert (meta.id, meta.name, meta.locale, meta.state) == (target, "Meta", "en", "active")
    assert meta.trial_ends_at - meta.created_at == timedelta(days=14)
    assert (meta.suspended_at, meta.closure_origin, meta.erase_after) == (None, None, None)
    assert organization_metadata(seed, uuid.uuid4()) is None


# --- list -------------------------------------------------------------------------------------


def test_search_by_name_substring_or_exact_id(seed: Session, pair: tuple[uuid.UUID, ...]) -> None:
    a, b = pair
    marker = uuid.uuid4().hex[:8]
    named = org(seed, f"Café {marker} S.L.")
    session = as_operator(seed)
    found = organization_rows(session, marker.upper(), OrganizationFilters(), page=1)
    assert [r.id for r in found.rows] == [named]
    assert found.total == 1
    by_id = organization_rows(session, str(b), OrganizationFilters(), page=1)
    assert [r.id for r in by_id.rows] == [b]
    wildcard = organization_rows(session, "%", OrganizationFilters(), page=1)
    assert wildcard.total == 0  # LIKE metacharacters are text, not patterns
    _ = a


def test_state_filter_within_ids_and_sort(seed: Session) -> None:
    tag = uuid.uuid4().hex[:8]
    active = org(seed, f"{tag} b")
    suspended = org(seed, f"{tag} a", suspended_at=datetime.now(UTC), suspension_reason="other")
    closing = org(seed, f"{tag} c", closure_requested_at=datetime.now(UTC))
    event(seed, closing, "requirement.assessed", 0)
    event(seed, active, "requirement.assessed", 5)
    session = as_operator(seed)

    def ids(**filters: Any) -> list[uuid.UUID]:
        page = organization_rows(session, tag, OrganizationFilters(**filters), page=1)
        return [r.id for r in page.rows]

    assert ids() == [suspended, active, closing]  # by name
    assert ids(state="active") == [active]
    assert ids(state="suspended") == [suspended]
    assert ids(state="closing") == [closing]
    assert ids(sort="activity") == [closing, active, suspended]  # most recent first, none last
    assert ids(sort="created")[0] in {active, suspended, closing}
    assert ids(within=frozenset({active, closing})) == [active, closing]
    assert ids(within=frozenset()) == []
    assert ids(exclude=frozenset({active})) == [suspended, closing]


def test_pages_hold_fifty_rows(seed: Session) -> None:
    tag = uuid.uuid4().hex[:8]
    for i in range(PAGE_SIZE + 3):
        org(seed, f"{tag} {i:03}")
    session = as_operator(seed)
    first = organization_rows(session, tag, OrganizationFilters(), page=1)
    second = organization_rows(session, tag, OrganizationFilters(), page=2)
    assert (len(first.rows), len(second.rows), first.total) == (PAGE_SIZE, 3, PAGE_SIZE + 3)
    assert first.rows[-1].name < second.rows[0].name


# --- organization writes -------------------------------------------------------------------


def test_suspend_and_reactivate_change_only_the_suspension(seed: Session) -> None:
    target = org(seed, "Suspend me")
    before = sql(seed, "SELECT updated_at FROM organizations WHERE id = :o", o=target).scalar_one()
    session = as_operator(seed)
    since = suspend(session, target, "non_payment")
    meta = organization_metadata(session, target)
    assert meta is not None
    assert (meta.suspended_at, meta.suspension_reason, meta.state) == (
        since,
        "non_payment",
        "suspended",
    )
    with pytest.raises(OperatorError) as again:
        suspend(session, target, "other")
    assert again.value.code == "already_suspended"
    reactivate(session, target)
    with pytest.raises(OperatorError) as twice:
        reactivate(session, target)
    assert twice.value.code == "not_suspended"
    sql(seed, "RESET ROLE")
    after = sql(seed, "SELECT updated_at FROM organizations WHERE id = :o", o=target).scalar_one()
    assert after == before  # the role cannot write it, and nothing tried to


def test_suspension_reason_comes_from_the_closed_list(seed: Session) -> None:
    target = org(seed, "Reason")
    with pytest.raises(ValueError, match="reason"):
        suspend(as_operator(seed), target, "because")


def test_writes_to_an_unknown_organization_are_not_found(seed: Session) -> None:
    session = as_operator(seed)
    for write in (
        lambda o: suspend(session, o, "other"),
        lambda o: reactivate(session, o),
        lambda o: start_operator_closure(session, o),
        lambda o: cancel_operator_closure(session, o),
    ):
        with pytest.raises(OperatorError) as missing:
            write(uuid.uuid4())
        assert missing.value.code == "not_found"


def test_operator_closure_rules(seed: Session) -> None:
    mine = org(seed, "Operator closes")
    owners = org(seed, "Owner closes")
    sql(
        seed,
        "UPDATE organizations SET closure_requested_at = now(), closure_requested_by = :u"
        " WHERE id = :o",
        o=owners,
        u=uuid.uuid4(),
    )
    session = as_operator(seed)
    erase_after = start_operator_closure(session, mine)
    assert timedelta(days=29) < erase_after - datetime.now(UTC) <= timedelta(days=30)
    meta = organization_metadata(session, mine)
    assert meta is not None and (meta.closure_origin, meta.state) == ("operator", "closing")
    for target, code in ((mine, "closure_exists"), (owners, "closure_exists")):
        with pytest.raises(OperatorError) as exists:
            start_operator_closure(session, target)
        assert exists.value.code == code
    with pytest.raises(OperatorError) as by_owner:
        cancel_operator_closure(session, owners)
    assert by_owner.value.code == "closure_by_owner"
    cancel_operator_closure(session, mine)
    with pytest.raises(OperatorError) as none:
        cancel_operator_closure(session, mine)
    assert none.value.code == "no_closure"
