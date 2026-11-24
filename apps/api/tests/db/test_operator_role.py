"""The operator role reads metadata only (ADR-017, ADR-012 amendment 8, operator-portal spec).

Every check runs on real Postgres. The content-table list is generated from platform.tables, and
the schema linter refuses a table missing from it, so a new table is covered without edits here.
"""

import uuid
from collections.abc import Iterator

import pytest
from atesta_api.platform.tables import OPERATOR_READ, table_classes
from sqlalchemy import Connection, Engine, column, delete, insert, literal, select, table, text
from sqlalchemy.exc import DBAPIError

from .conftest import ORG_A, ORG_B

OP = "atesta_operator"
# Every tenant, global, catalog, queue and operator table outside the closed list.
NOT_LISTED = sorted(set(table_classes()) - set(OPERATOR_READ))
ALL_PRIVILEGES = "SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER"


@pytest.fixture
def op(operator_engine: Engine, probe: object) -> Iterator[Connection]:
    """An operator connection in a transaction that is always rolled back."""
    with operator_engine.connect() as conn:
        tx = conn.begin()
        try:
            yield conn
        finally:
            tx.rollback()


@pytest.fixture(scope="module")
def seeded(superuser: Engine, probe: object) -> Iterator[None]:
    """Metadata rows in both organizations, committed, removed afterwards."""
    users = {ORG_A: uuid.uuid4(), ORG_B: uuid.uuid4()}
    with superuser.begin() as conn:
        for org, user in users.items():
            conn.execute(
                text(
                    "INSERT INTO users (id, cognito_sub, email, email_verified)"
                    " VALUES (:u, :s, :e, true)"
                ),
                {"u": user, "s": f"sub-{user}", "e": f"{user}@example.com"},
            )
            conn.execute(
                text(
                    "INSERT INTO memberships (organization_id, user_id, role)"
                    " VALUES (:o, :u, 'owner')"
                ),
                {"o": org, "u": user},
            )
            conn.execute(
                text("INSERT INTO subscriptions (organization_id, plan) VALUES (:o, 'pro')"),
                {"o": org},
            )
            conn.execute(
                text("INSERT INTO billing_profiles (organization_id, legal_name) VALUES (:o, :n)"),
                {"o": org, "n": f"Legal {org}"},
            )
            conn.execute(
                text(
                    "INSERT INTO audit_events (id, organization_id, actor_user_id, action,"
                    " target_type, target_id) VALUES (:i, :o, :u, 'organization.created',"
                    " 'organization', :t)"
                ),
                {"i": uuid.uuid4(), "o": org, "u": user, "t": str(org)},
            )
    yield
    with superuser.begin() as conn:
        for name in ("audit_events", "billing_profiles", "subscriptions", "memberships"):
            owned = column("organization_id").in_(list(users))
            conn.execute(delete(table(name, column("organization_id"))).where(owned))
        conn.execute(text("DELETE FROM users WHERE id = ANY(:u)"), {"u": list(users.values())})


def _privileged_columns(conn: Connection, privilege: str) -> dict[str, set[str]]:
    rows = conn.execute(
        text(
            "SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0"
            " AND NOT a.attisdropped AND has_column_privilege(:r, c.oid, a.attnum, :p)"
        ),
        {"r": OP, "p": privilege},
    ).all()
    found: dict[str, set[str]] = {}
    for name, col in rows:
        found.setdefault(name, set()).add(col)
    return found


def test_the_role_is_a_plain_login_that_owns_nothing(superuser: Engine) -> None:
    with superuser.connect() as conn:
        attrs = conn.execute(
            text("SELECT rolsuper, rolbypassrls, rolcreaterole FROM pg_roles WHERE rolname = :r"),
            {"r": OP},
        ).one()
        assert tuple(attrs) == (False, False, False)
        member_of = conn.scalar(
            text(
                "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member"
                " WHERE r.rolname = :r"
            ),
            {"r": OP},
        )
        owned = conn.scalar(
            text("SELECT count(*) FROM pg_class WHERE relowner = CAST(:r AS regrole)"), {"r": OP}
        )
        assert (member_of, owned) == (0, 0)


def test_selectable_columns_are_exactly_the_closed_list(superuser: Engine) -> None:
    """Every column the role can read is on the list."""
    with superuser.connect() as conn:
        readable = _privileged_columns(conn, "SELECT")
    assert readable == {t: set(cols) for t, cols in OPERATOR_READ.items()}


def test_no_table_level_privilege_on_listed_tables(superuser: Engine) -> None:
    """Column grants only: a column added later is not readable by default."""
    with superuser.connect() as conn:
        for table in OPERATOR_READ:
            assert not conn.scalar(
                text("SELECT has_table_privilege(:r, :t, 'SELECT, DELETE, TRUNCATE')"),
                {"r": OP, "t": table},
            ), table


@pytest.mark.parametrize("table", NOT_LISTED)
def test_no_privilege_at_all_on_a_table_outside_the_list(superuser: Engine, table: str) -> None:
    with superuser.connect() as conn:
        held = conn.execute(
            text(
                "SELECT has_table_privilege(:r, :t, :all),"
                " has_any_column_privilege(:r, :t, 'SELECT, INSERT, UPDATE, REFERENCES')"
            ),
            {"r": OP, "t": table, "all": ALL_PRIVILEGES},
        ).one()
    assert tuple(held) == (False, False)


@pytest.mark.parametrize("name", NOT_LISTED)
def test_reading_a_table_outside_the_list_is_refused(op: Connection, name: str) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        op.execute(select(literal(1)).select_from(table(name)).limit(1))


@pytest.mark.parametrize("name", ["evidence", "findings", "incidents", "policies"])
def test_named_content_tables_are_refused(op: Connection, name: str) -> None:
    """The spec's named examples, kept explicit in case the generated list ever shrinks."""
    assert name in NOT_LISTED
    with pytest.raises(DBAPIError, match="permission denied"):
        op.execute(select(text("*")).select_from(table(name)))


@pytest.mark.parametrize(
    ("name", "col"),
    [
        ("organizations", "closure_requested_by"),
        ("organizations", "updated_at"),
        ("memberships", "user_id"),
        ("invitations", "email"),
        ("connections", "display_name"),
        ("connections", "external_tenant_id"),
        ("scans", "error_code"),
        ("api_tokens", "name"),
        ("api_token_usage", "route"),
        ("audit_events", "metadata"),
        ("audit_events", "actor_user_id"),
        ("erasure_receipts", "note"),
    ],
)
def test_a_column_outside_the_list_is_refused(op: Connection, name: str, col: str) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        op.execute(select(column(col)).select_from(table(name)))


@pytest.mark.parametrize("name", sorted(OPERATOR_READ))
def test_listed_columns_are_readable(op: Connection, seeded: None, name: str) -> None:
    op.execute(select(*(column(c) for c in sorted(OPERATOR_READ[name]))).select_from(table(name)))


@pytest.mark.parametrize(
    "name", ["organizations", "memberships", "subscriptions", "billing_profiles", "audit_events"]
)
def test_metadata_is_read_across_organizations(op: Connection, seeded: None, name: str) -> None:
    key = column("id" if name == "organizations" else "organization_id")
    seen = set(op.execute(select(key).select_from(table(name))).scalars())
    assert {ORG_A, ORG_B} <= seen


def _audit(op: Connection, action: str, **extra: object) -> None:
    values = {
        "id": uuid.uuid4(),
        "organization_id": ORG_A,
        "action": action,
        "target_type": "organization",
        "target_id": str(ORG_A),
        **extra,
    }
    op.execute(insert(table("audit_events", *(column(c) for c in values))).values(values))


def test_the_role_writes_only_operator_actions_to_the_customer_trail(op: Connection) -> None:
    _audit(op, "operator.plan_changed")
    with pytest.raises(DBAPIError, match="row-level security"), op.begin_nested():
        _audit(op, "organization.renamed")


def test_a_tenant_setting_does_not_widen_the_customer_trail_write(op: Connection) -> None:
    op.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(ORG_A)})
    with pytest.raises(DBAPIError, match="row-level security"):
        _audit(op, "organization.renamed")


def test_the_role_cannot_name_an_actor_in_the_customer_trail(op: Connection) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        _audit(op, "operator.plan_changed", actor_user_id=uuid.uuid4())


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET action = 'operator.x'",
        "DELETE FROM audit_events",
        "DELETE FROM subscriptions",
        "DELETE FROM billing_profiles",
        "DELETE FROM organizations",
        "UPDATE organizations SET name = 'x'",
        "UPDATE organizations SET trial_ends_at = now()",
        "UPDATE organizations SET closure_requested_by = NULL",
        "INSERT INTO erasure_receipts (id, organization_id, closure_requested_at, note, row_counts)"
        " VALUES (gen_random_uuid(), gen_random_uuid(), now(), '', '{}')",
    ],
)
def test_writes_outside_the_grants_are_refused(op: Connection, statement: str) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        op.execute(text(statement))


def test_the_role_sets_plans_billing_details_and_suspension(op: Connection, seeded: None) -> None:
    op.execute(
        text(
            "INSERT INTO subscriptions (organization_id, plan, addons, note)"
            " VALUES (:o, 'starter', '{}', 'contract') ON CONFLICT (organization_id)"
            " DO UPDATE SET plan = excluded.plan, note = excluded.note, updated_at = now()"
        ),
        {"o": ORG_B},
    )
    op.execute(
        text(
            "INSERT INTO billing_profiles (organization_id, legal_name, country)"
            " VALUES (:o, 'L', 'ES')"
            " ON CONFLICT (organization_id) DO UPDATE SET legal_name = excluded.legal_name,"
            " country = excluded.country, updated_at = now()"
        ),
        {"o": ORG_B},
    )
    suspended = op.execute(
        text(
            "UPDATE organizations SET suspended_at = now(), suspension_reason = 'non_payment'"
            " WHERE id = :o"
        ),
        {"o": ORG_B},
    )
    assert suspended.rowcount == 1  # type: ignore[attr-defined]
    row = op.execute(
        text(
            "SELECT s.plan, b.legal_name, o.suspension_reason FROM organizations o"
            " JOIN subscriptions s ON s.organization_id = o.id"
            " JOIN billing_profiles b ON b.organization_id = o.id WHERE o.id = :o"
        ),
        {"o": ORG_B},
    ).one()
    assert tuple(row) == ("starter", "L", "non_payment")


def test_an_operator_closure_has_the_operator_origin(op: Connection) -> None:
    op.execute(
        text("UPDATE organizations SET closure_requested_at = now() WHERE id = :o"), {"o": ORG_A}
    )
    origin = op.scalar(text("SELECT closure_origin FROM organizations WHERE id = :o"), {"o": ORG_A})
    assert origin == "operator"


def test_the_role_cannot_cancel_an_owner_closure(
    superuser: Engine, operator_engine: Engine
) -> None:
    org = uuid.uuid4()
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO organizations (id, name, closure_requested_at, closure_requested_by)"
                " VALUES (:o, 'closing', now(), gen_random_uuid())"
            ),
            {"o": org},
        )
    try:
        with operator_engine.connect() as conn, conn.begin():
            assert (
                conn.scalar(
                    text("SELECT closure_origin FROM organizations WHERE id = :o"), {"o": org}
                )
                == "owner"
            )
            with pytest.raises(DBAPIError, match="closure_by_needs_at"):
                conn.execute(
                    text("UPDATE organizations SET closure_requested_at = NULL WHERE id = :o"),
                    {"o": org},
                )
    finally:
        with superuser.begin() as conn:
            conn.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})


def test_the_app_role_only_reads_billing_profiles(superuser: Engine) -> None:
    with superuser.connect() as conn:
        held = conn.execute(
            text(
                "SELECT has_table_privilege('atesta_app', 'billing_profiles', 'SELECT'),"
                " has_table_privilege('atesta_app', 'billing_profiles', 'INSERT, UPDATE, DELETE'),"
                " has_any_column_privilege('atesta_app', 'billing_profiles', 'INSERT, UPDATE')"
            )
        ).one()
    assert tuple(held) == (True, False, False)


@pytest.mark.parametrize(
    ("column", "allowed"),
    [
        ("name", True),
        ("locale", True),
        ("updated_at", True),
        ("closure_requested_at", True),
        ("closure_requested_by", True),
        ("suspended_at", False),
        ("suspension_reason", False),
        ("trial_ends_at", False),
        ("closure_origin", False),
    ],
)
def test_the_app_role_updates_only_customer_columns_of_organizations(
    superuser: Engine, column: str, allowed: bool
) -> None:
    with superuser.connect() as conn:
        assert (
            conn.scalar(
                text("SELECT has_column_privilege('atesta_app', 'organizations', :c, 'UPDATE')"),
                {"c": column},
            )
            is allowed
        )
