"""Defer jobs inside the caller's transaction (scanner-connectors spec, Scan lifecycle).

The job row is inserted on the session's own psycopg connection, so it commits or rolls back
with the work that asked for it. Arguments are ids only: queue tables have no RLS (ADR-012
amendment 2).
"""

import functools
import re

from procrastinate import App, SyncPsycopgConnector
from sqlalchemy.orm import Session

_ID_ARGUMENT = re.compile(r"[a-z]+(_[a-z]+)*_id")


@functools.cache
def _app() -> App:
    # Never opened: every defer passes the session's connection, so no pool is ever created.
    return App(connector=SyncPsycopgConnector())


def defer(session: Session, task_name: str, *, queue: str, **ids: str) -> None:
    bad = sorted(
        k for k, v in ids.items() if not _ID_ARGUMENT.fullmatch(k) or not isinstance(v, str)
    )
    if bad:
        raise ValueError(f"job arguments must be <name>_id strings: {', '.join(bad)}")
    connection = session.connection().connection.driver_connection
    _app().configure_task(task_name, queue=queue, connection=connection).defer(**ids)
