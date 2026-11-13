"""Database sessions for jobs: one transaction in one org context, reason `job` (ADR-012)."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from atesta_api.modules.identity.api import ContextReason, enter_org_context
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

_factory: sessionmaker[Session] | None = None


def configure(engine: Engine) -> None:
    global _factory
    _factory = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def org_session(organization_id: str, isolation_level: str | None = None) -> Iterator[Session]:
    """Commit on success, roll back on any error. A malformed id is refused before any query."""
    if _factory is None:
        raise RuntimeError("worker database not configured")
    org_id = uuid.UUID(organization_id)
    session = _factory()
    try:
        if isolation_level is not None:  # before the first statement of the transaction
            session.connection(execution_options={"isolation_level": isolation_level})
        enter_org_context(session, org_id, ContextReason.JOB)
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
