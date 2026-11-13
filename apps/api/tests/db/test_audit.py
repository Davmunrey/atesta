"""Audit events: append-only, atomic with the action, scalar metadata only."""

from collections.abc import Iterator

import pytest
from atesta_api.platform.audit import record
from atesta_api.platform.context import TenantContext
from atesta_api.platform.tenancy import set_tenant_context
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from .conftest import ORG_A, ORG_B


def _record(session: Session, org: object = ORG_A) -> None:
    record(session, organization_id=org, action="org.renamed", target_type="org", target_id="x")  # type: ignore[arg-type]


def _events(factory: sessionmaker[Session]) -> int:
    with factory() as session:
        set_tenant_context(session, TenantContext(organization_id=ORG_A))
        return int(session.execute(text("SELECT count(*) FROM audit_events")).scalar_one())


@pytest.fixture
def clean_audit(superuser: Engine) -> Iterator[None]:
    yield
    with superuser.begin() as conn:
        conn.exec_driver_sql("DELETE FROM audit_events")


@pytest.mark.usefixtures("clean_audit")
def test_record_is_atomic_with_the_transaction(db_commit: sessionmaker[Session]) -> None:
    with db_commit() as session:
        set_tenant_context(session, TenantContext(organization_id=ORG_A))
        _record(session)
        session.rollback()
    assert _events(db_commit) == 0
    with db_commit() as session:
        set_tenant_context(session, TenantContext(organization_id=ORG_A))
        _record(session)
        session.commit()
    assert _events(db_commit) == 1


@pytest.mark.parametrize(
    "statement", ["UPDATE audit_events SET action = 'x.y'", "DELETE FROM audit_events"]
)
def test_audit_events_are_append_only(db_rollback: Session, statement: str) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    _record(db_rollback)
    with pytest.raises(DBAPIError, match="permission denied"):
        db_rollback.execute(text(statement))


def test_record_for_another_tenant_fails(db_rollback: Session) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    with pytest.raises(DBAPIError, match="row-level security"):
        _record(db_rollback, ORG_B)


@pytest.mark.parametrize(
    ("action", "metadata"),
    [("created", {}), ("Org.Created", {}), ("org.created", {"blob": {"token": "t"}})],
)
def test_record_rejects_free_form_input(action: str, metadata: dict[str, object]) -> None:
    with pytest.raises((ValueError, TypeError)):
        record(
            None,  # type: ignore[arg-type]  validation runs before any DB access
            organization_id=ORG_A,
            action=action,
            target_type="org",
            target_id="x",
            metadata=metadata,  # type: ignore[arg-type]
        )
