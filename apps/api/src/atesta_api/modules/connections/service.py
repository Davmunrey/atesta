"""Connections (scanner-connectors spec, Connections): create, read, disconnect.

Every query runs in the caller's org context (RLS). A connection starts waiting for its
onboarding: an M365 one for the admin's Microsoft sign-in and consent, a Google one for its two
service accounts. A removed connection becomes `disconnected`, never deleted.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.connections.models import Connection

ALLOWLIST_VERSION = {"m365": "m365-v1", "google_workspace": "google-v1"}
FIRST_STATUS = {"m365": "pending_setup", "google_workspace": "pending_provisioning"}


class ConnectionStateError(ValueError):
    """The connection cannot make this transition."""


def create_connection(
    session: Session,
    *,
    organization_id: uuid.UUID,
    provider: str,
    display_name: str,
    created_by: uuid.UUID,
) -> Connection:
    connection = Connection(
        organization_id=organization_id,
        provider=provider,
        status=FIRST_STATUS[provider],
        display_name=display_name,
        allowlist_version=ALLOWLIST_VERSION[provider],
        created_by=created_by,
    )
    session.add(connection)
    session.flush()
    session.refresh(connection)
    return connection


def list_connections(session: Session) -> list[Connection]:
    query = select(Connection).order_by(Connection.created_at, Connection.id)
    return list(session.scalars(query))


def get_connection(session: Session, connection_id: uuid.UUID) -> Connection | None:
    return session.get(Connection, connection_id)


def disconnect_connection(session: Session, connection_id: uuid.UUID) -> Connection | None:
    """Lock, then mark disconnected; a second call is a state error, not a second event."""
    query = select(Connection).where(Connection.id == connection_id).with_for_update()
    connection = session.scalars(query.execution_options(populate_existing=True)).one_or_none()
    if connection is None:
        return None
    if connection.status == "disconnected":
        raise ConnectionStateError("already disconnected")
    connection.status = "disconnected"
    session.flush()
    session.refresh(connection)
    return connection


def active_connection_ids(session: Session) -> list[uuid.UUID]:
    query = select(Connection.id).where(Connection.status == "active").order_by(Connection.id)
    return list(session.scalars(query))


ENDED_STATUSES = ("disconnected", "revoked")


def ended_connection_ids(session: Session, organization_id: uuid.UUID) -> set[uuid.UUID]:
    """Connections whose results no longer count: disconnected, or access revoked."""
    query = select(Connection.id).where(
        Connection.organization_id == organization_id, Connection.status.in_(ENDED_STATUSES)
    )
    return set(session.scalars(query))
