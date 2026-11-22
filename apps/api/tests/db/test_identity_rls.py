"""Identity policies: read branches never grant writes (identity-auth spec, ADR-012)."""

import uuid

import pytest
from atesta_api.modules.identity.api import (
    ContextReason,
    enter_invitation_context,
    enter_org_context,
    enter_user_context,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .conftest import ORG_A, ORG_B

U1 = uuid.UUID("11111111-0000-4000-8000-000000000001")  # owner of A, member of B
U2 = uuid.UUID("22222222-0000-4000-8000-000000000002")  # owner of B
TOKEN = "f" * 64


@pytest.fixture(scope="module", autouse=True)
def seed(superuser: Engine, probe: object) -> None:
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, cognito_sub, email, email_verified) VALUES"
                " (:u1, 'sub-u1', 'u1@example.com', true), (:u2, 'sub-u2', 'u2@example.com', true)"
            ),
            {"u1": U1, "u2": U2},
        )
        conn.execute(
            text(
                "INSERT INTO memberships VALUES (:a, :u1, 'owner'), (:b, :u1, 'member'),"
                " (:b, :u2, 'owner')"
            ),
            {"a": ORG_A, "b": ORG_B, "u1": U1, "u2": U2},
        )
        conn.execute(
            text(
                "INSERT INTO invitations (id, organization_id, email, role, token_sha256,"
                " invited_by, expires_at) VALUES"
                " (:i, :b, 'new@example.com', 'member', :t, :u2, now() + interval '7 days'),"
                # decoys: same org with another token, and another org, so the token test
                # cannot pass just because only one invitation exists
                " (:j, :b, 'other@example.com', 'member', :same_org, :u2,"
                "  now() + interval '7 days'),"
                " (:k, :a, 'third@example.com', 'member', :other_org, :u1,"
                "  now() + interval '7 days')"
            ),
            {
                "i": uuid.uuid4(),
                "j": uuid.uuid4(),
                "k": uuid.uuid4(),
                "a": ORG_A,
                "b": ORG_B,
                "t": TOKEN,
                "same_org": "d" * 64,
                "other_org": "e" * 64,
                "u1": U1,
                "u2": U2,
            },
        )


def counts(session: Session, *tables: str) -> list[int]:
    return [
        int(session.execute(text(f"SELECT count(*) FROM {t}")).scalar_one())  # noqa: S608  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text - fixed table names, no user input
        for t in tables
    ]


def test_me_without_org_context_sees_own_rows(db_rollback: Session) -> None:
    enter_user_context(db_rollback, "sub-u1", U1)
    assert counts(db_rollback, "memberships", "organizations", "users") == [2, 2, 1]


def test_no_org_context_grants_no_membership_write(db_rollback: Session) -> None:
    enter_user_context(db_rollback, "sub-u1", U1)
    update = text("UPDATE memberships SET role = 'owner' WHERE user_id = :u")
    assert db_rollback.execute(update, {"u": U1}).rowcount == 0  # type: ignore[attr-defined]
    with pytest.raises(DBAPIError, match="row-level security"):
        db_rollback.execute(
            text("INSERT INTO memberships VALUES (:a, :u, 'owner')"), {"a": ORG_A, "u": U2}
        )


def test_users_self_upsert_only(db_rollback: Session) -> None:
    enter_user_context(db_rollback, "sub-u1", U1)
    upsert = text(
        "INSERT INTO users (id, cognito_sub, email, email_verified) VALUES (:u, 'sub-u1',"
        " 'new@example.com', true) ON CONFLICT (cognito_sub) DO UPDATE SET email = excluded.email"
        " RETURNING email"
    )
    assert db_rollback.execute(upsert, {"u": U1}).scalar_one() == "new@example.com"
    enter_org_context(db_rollback, ORG_B, ContextReason.MEMBERSHIP)  # u2 is a visible co-member
    assert counts(db_rollback, "users") == [2]
    other = text("UPDATE users SET email = 'evil' WHERE cognito_sub = 'sub-u2'")
    assert db_rollback.execute(other).rowcount == 0  # type: ignore[attr-defined]


def test_org_context_scopes_unfiltered_queries(db_rollback: Session) -> None:
    enter_user_context(db_rollback, "sub-u1", U1)
    enter_org_context(db_rollback, ORG_A, ContextReason.MEMBERSHIP)
    assert counts(db_rollback, "memberships", "users", "organizations") == [1, 1, 1]
    rename = db_rollback.execute(text("UPDATE organizations SET name = name"))
    assert rename.rowcount == 1  # type: ignore[attr-defined]
    with pytest.raises(DBAPIError, match="row-level security"):
        db_rollback.execute(
            text("INSERT INTO memberships VALUES (:b, :u, 'owner')"), {"b": ORG_B, "u": U1}
        )


def test_org_creation_inserts_org_and_owner(db_rollback: Session) -> None:
    new_org = uuid.uuid4()
    enter_user_context(db_rollback, "sub-u2", U2)
    enter_org_context(db_rollback, new_org, ContextReason.ORG_CREATION)
    created = db_rollback.execute(
        text("INSERT INTO organizations (id, name) VALUES (:o, 'C') RETURNING created_at"),
        {"o": new_org},
    )
    assert created.scalar_one() is not None
    db_rollback.execute(
        text("INSERT INTO memberships VALUES (:o, :u, 'owner')"), {"o": new_org, "u": U2}
    )
    assert counts(db_rollback, "memberships") == [1]


def test_invitation_token_reads_one_row_and_writes_nothing(db_rollback: Session) -> None:
    enter_invitation_context(db_rollback, TOKEN)
    visible = db_rollback.execute(text("SELECT token_sha256 FROM invitations")).scalars().all()
    assert visible == [TOKEN]
    escalate = text("UPDATE invitations SET role = 'owner', organization_id = :a")
    assert db_rollback.execute(escalate, {"a": ORG_A}).rowcount == 0  # type: ignore[attr-defined]
    enter_org_context(db_rollback, ORG_B, ContextReason.INVITATION)
    claim = text(
        "UPDATE invitations SET accepted_at = now() WHERE token_sha256 = :t"
        " AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at > now() RETURNING role"
    )
    assert db_rollback.execute(claim, {"t": TOKEN}).scalar_one() == "member"


def test_last_owner_rows_can_be_locked(db_rollback: Session) -> None:
    enter_org_context(db_rollback, ORG_B, ContextReason.MEMBERSHIP)
    owners = db_rollback.execute(
        text("SELECT user_id FROM memberships WHERE role = 'owner' FOR UPDATE")
    ).scalars()
    assert list(owners) == [U2]


def test_switching_org_mid_transaction_is_refused(db_rollback: Session) -> None:
    enter_org_context(db_rollback, ORG_A, ContextReason.MEMBERSHIP)
    enter_org_context(db_rollback, ORG_A, ContextReason.MEMBERSHIP)  # same org is fine
    with pytest.raises(RuntimeError, match="another org context"):
        enter_org_context(db_rollback, ORG_B, ContextReason.MEMBERSHIP)
