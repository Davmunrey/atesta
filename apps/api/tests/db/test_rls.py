"""Tenant isolation under RLS (tenant-data-layer spec, test plan)."""

import uuid

import pytest
from atesta_api.platform.context import TenantContext
from atesta_api.platform.tenancy import set_tenant_context
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from .conftest import ORG_A, ORG_B

SETTINGS = ("app.subject", "app.user_id", "app.organization_id", "app.invitation_token_sha256")


def rls_tables(session: Session) -> list[str]:
    rows = session.execute(
        text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity"
        )
    )
    return sorted(r[0] for r in rows)


def count(session: Session, table: str) -> int:
    assert table.isidentifier()
    return int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())  # noqa: S608


def test_context_sees_only_its_tenant(db_rollback: Session) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    assert db_rollback.execute(text("SELECT v FROM probe")).scalars().all() == ["a"]
    assert db_rollback.execute(text("SELECT id FROM organizations")).scalars().all() == [ORG_A]


def test_insert_for_other_tenant_fails_with_check(db_rollback: Session) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    with pytest.raises(DBAPIError, match="row-level security"):
        db_rollback.execute(
            text("INSERT INTO probe VALUES (:i, :o, 'x')"), {"i": uuid.uuid4(), "o": ORG_B}
        )


def test_update_delete_of_other_tenant_touch_nothing(db_rollback: Session) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    upd = db_rollback.execute(
        text("UPDATE probe SET v = 'z' WHERE organization_id = :o"), {"o": ORG_B}
    )
    dele = db_rollback.execute(text("DELETE FROM probe WHERE organization_id = :o"), {"o": ORG_B})
    assert (upd.rowcount, dele.rowcount) == (0, 0)  # type: ignore[attr-defined]


def test_truncate_is_denied(db_rollback: Session) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    with pytest.raises(DBAPIError, match="permission denied"):
        db_rollback.execute(text("TRUNCATE probe"))


def test_composite_fk_rejects_other_tenant_parent_like_random_id(
    db_rollback: Session, probe: dict[uuid.UUID, uuid.UUID]
) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    errors = []
    for parent in (uuid.uuid4(), probe[ORG_B]):
        with pytest.raises(DBAPIError) as exc, db_rollback.begin_nested():
            db_rollback.execute(
                text("INSERT INTO probe_child VALUES (:o, :p)"), {"o": ORG_A, "p": parent}
            )
        errors.append(str(exc.value.orig).splitlines()[0])
    assert errors[0] == errors[1]
    assert "foreign key" in errors[0]
    db_rollback.execute(
        text("INSERT INTO probe_child VALUES (:o, :p)"), {"o": ORG_A, "p": probe[ORG_A]}
    )


def test_no_context_returns_zero_rows_everywhere(db_rollback: Session) -> None:
    tables = rls_tables(db_rollback)
    assert {"organizations", "probe", "probe_child"} <= set(tables)
    assert {t: count(db_rollback, t) for t in tables} == dict.fromkeys(tables, 0)


def test_pooled_connection_never_carries_a_tenant(db_commit: sessionmaker[Session]) -> None:
    with db_commit() as first:
        set_tenant_context(first, TenantContext(subject="s", organization_id=ORG_A))
        pid = first.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert count(first, "probe") == 1
        first.commit()
    with db_commit() as second:
        assert second.execute(text("SELECT pg_backend_pid()")).scalar_one() == pid
        values = [
            second.execute(text("SELECT current_setting(:n, true)"), {"n": n}).scalar_one()
            for n in SETTINGS
        ]
        assert all(v in (None, "") for v in values)
        assert all(count(second, t) == 0 for t in rls_tables(second))
