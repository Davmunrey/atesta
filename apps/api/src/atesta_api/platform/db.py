"""Engine, sessions and declarative base (tenant-data-layer spec)."""

import uuid
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import ForeignKey, MetaData, create_engine, pool
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TenantMixin:
    """Every tenant table: organization_id NOT NULL, FK to the tenant root, indexed."""

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )


def make_engine(
    url: str | URL,
    *,
    sslmode: str = "verify-full",
    sslrootcert: str | None = None,
    pool_size: int = 5,
    max_overflow: int = 5,
    null_pool: bool = False,
) -> Engine:
    """The only Engine factory. TLS settings never come from the URL.

    hide_parameters keeps bound values (document text, emails) out of errors and logs (rule 2).
    """
    clean = make_url(url).difference_update_query(["sslmode", "sslrootcert"])
    connect_args: dict[str, Any] = {"sslmode": sslmode}
    if sslrootcert:
        connect_args["sslrootcert"] = sslrootcert
    if null_pool:
        return create_engine(
            clean, hide_parameters=True, poolclass=pool.NullPool, connect_args=connect_args
        )
    return create_engine(
        clean,
        hide_parameters=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        connect_args=connect_args,
    )


_factory: sessionmaker[Session] | None = None


def configure(engine: Engine) -> None:
    global _factory
    _factory = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """One session and transaction per request; commit on success, rollback on any error."""
    if _factory is None:
        raise RuntimeError("database not configured")
    session = _factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


# Function scope commits before the response is sent. Handlers depend on DbSession only.
DbSession = Annotated[Session, Depends(get_db, scope="function")]
