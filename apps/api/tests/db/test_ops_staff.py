"""The staff devtool (operator-portal spec, build step 7; #503): accounts in operator_staff,
with the migration credential, each change in the operator trail with the admin who made it."""

import json
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import URL, Engine, text


def _run(monkeypatch: pytest.MonkeyPatch, database: URL, *args: str) -> int:
    from atesta_api.ops import staff

    monkeypatch.setenv("ATESTA_MIGRATION_DATABASE_URL", database.render_as_string(False))
    monkeypatch.setenv("ATESTA_DB_SSLMODE", "disable")
    monkeypatch.setattr("sys.argv", ["staff", *args])
    with pytest.raises(SystemExit) as exited:
        staff.main()
    return int(exited.value.code or 0)


def _email() -> str:
    return f"Person-{uuid.uuid4().hex[:8]}@Atesta.test"


def _row(superuser: Engine, email: str) -> tuple[uuid.UUID, str, object] | None:
    with superuser.connect() as conn:
        row = conn.execute(
            text("SELECT id, role, disabled_at FROM operator_staff WHERE email = :e"),
            {"e": email.lower()},
        ).first()
    return None if row is None else (row.id, row.role, row.disabled_at)


def _trail(superuser: Engine, target: uuid.UUID) -> list[tuple[str, uuid.UUID, str, str]]:
    with superuser.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, staff_id, staff_role, reason FROM operator_audit_events"
                " WHERE target_id = :t ORDER BY occurred_at, action"
            ),
            {"t": str(target)},
        )
        return [tuple(r) for r in rows]


@pytest.fixture
def no_admins(superuser: Engine) -> Iterator[None]:
    """--first needs no enabled admin. The admins other tests left enabled are disabled for the
    test and enabled again after it, and the admins the test made are disabled, so a later
    "sole admin" test counts as before."""
    with superuser.begin() as conn:
        before = (
            conn.execute(
                text(
                    "UPDATE operator_staff SET disabled_at = now()"
                    " WHERE role = 'admin' AND disabled_at IS NULL RETURNING id"
                )
            )
            .scalars()
            .all()
        )
    yield
    with superuser.begin() as conn:
        conn.execute(text("UPDATE operator_staff SET disabled_at = now() WHERE role = 'admin'"))
        conn.execute(
            text("UPDATE operator_staff SET disabled_at = NULL WHERE id = ANY(:ids)"),
            {"ids": list(before)},
        )


def test_the_first_admin_adds_themselves_and_then_only_an_admin_adds_others(
    superuser: Engine,
    database: URL,
    monkeypatch: pytest.MonkeyPatch,
    no_admins: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first, second = _email(), _email()
    add = ["add", "--sub", f"sub-{uuid.uuid4()}", "--reason", "Ticket 1"]
    assert _run(monkeypatch, database, *add, "--email", first, "--role", "admin", "--first") == 0
    first_row = _row(superuser, first)
    assert first_row is not None and first_row[1] == "admin"
    assert _trail(superuser, first_row[0]) == [("staff.added", first_row[0], "admin", "Ticket 1")]
    event = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert event == {"event": "staff.added", "staff": str(first_row[0]), "role": "admin"}

    # A second --first is refused once an admin exists, and so is an unknown --by.
    other = ["add", "--sub", f"sub-{uuid.uuid4()}", "--email", second, "--role", "support"]
    assert _run(monkeypatch, database, *other, "--first", "--reason", "x") == 2
    assert _run(monkeypatch, database, *other, "--by", _email(), "--reason", "x") == 2
    assert _row(superuser, second) is None
    assert _run(monkeypatch, database, *other, "--by", first, "--reason", "New support") == 0
    second_row = _row(superuser, second)
    assert second_row is not None and second_row[1] == "support"
    assert _trail(superuser, second_row[0]) == [
        ("staff.added", first_row[0], "admin", "New support")
    ]


def test_an_admin_disables_and_enables_a_colleague_but_never_themselves(
    superuser: Engine, database: URL, monkeypatch: pytest.MonkeyPatch, no_admins: None
) -> None:
    admin, leaver = _email(), _email()
    for email, role, by in ((admin, "admin", ["--first"]), (leaver, "billing", ["--by", admin])):
        args = ["add", "--sub", f"sub-{uuid.uuid4()}", "--email", email, "--role", role]
        assert _run(monkeypatch, database, *args, *by, "--reason", "Setup") == 0
    change = ["--email", leaver, "--by", admin, "--reason", "Left the team"]
    assert _run(monkeypatch, database, "disable", *change) == 0
    leaver_row = _row(superuser, leaver)
    assert leaver_row is not None and leaver_row[2] is not None
    assert _run(monkeypatch, database, "enable", *change) == 0
    leaver_row = _row(superuser, leaver)
    assert leaver_row is not None and leaver_row[2] is None
    actions = [a for a, *_ in _trail(superuser, leaver_row[0])]
    assert actions == ["staff.added", "staff.disabled", "staff.enabled"]
    own = ["--email", admin, "--by", admin, "--reason", "x"]
    assert _run(monkeypatch, database, "disable", *own) == 2  # self_change
    admin_row = _row(superuser, admin)
    assert admin_row is not None and admin_row[2] is None
