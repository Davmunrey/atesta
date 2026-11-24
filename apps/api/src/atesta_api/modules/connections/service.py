"""Connections (scanner-connectors spec, Connections): create, read, disconnect.

Every query runs in the caller's org context (RLS). A connection starts waiting for its
onboarding: an M365 one for the admin's Microsoft sign-in and consent, a Google one for its two
service accounts. A removed connection becomes `disconnected`, never deleted.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atesta_api.modules.connections.models import Connection
from atesta_api.platform.audit import record

ALLOWLIST_VERSION = {"m365": "m365-v1", "google_workspace": "google-v1"}
# Still onboarding: a sign-in, a consent and a verification may (re)start here (#314, #331).
ONBOARDING = frozenset({"pending_setup", "incomplete", "over_privileged", "revoked"})
FIRST_STATUS = {"m365": "pending_setup", "google_workspace": "pending_provisioning"}


class ConnectionStateError(ValueError):
    """The connection cannot make this transition."""


@dataclass(frozen=True, slots=True)
class ScanTarget:
    """What a scan or a verification of a connection needs: ids and references, never a secret.

    The scanner container resolves the references itself (ADR-004); no API or worker process
    ever holds the secret they name.
    """

    connection_id: uuid.UUID
    provider: str
    status: str
    external_tenant_id: str | None
    allowlist_version: str | None
    credential_ref: str | None
    verifier_credential_ref: str | None
    google_client_id: str | None
    google_verifier_client_id: str | None
    google_subject_email: str | None
    ms_tenant_id: str | None = None  # the tenant bound at sign-in (#314)
    consented_by_oid: str | None = None  # the consenting admin's object id: an id, not a secret

    @property
    def active(self) -> bool:
        return self.status == "active"

    @property
    def verifying(self) -> bool:
        """Only the activation scan runs now: it verifies, then activates (#331)."""
        return self.status == "verifying"


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


def inactive_connection_count(session: Session) -> int:
    """Connections that need attention: neither active nor disconnected (weekly summary)."""
    query = select(func.count()).where(Connection.status.not_in(("active", "disconnected")))
    return int(session.scalar(query.select_from(Connection)) or 0)


def active_connection_ids(session: Session) -> list[uuid.UUID]:
    query = select(Connection.id).where(Connection.status == "active").order_by(Connection.id)
    return list(session.scalars(query))


def scan_target(
    session: Session, organization_id: uuid.UUID, connection_id: uuid.UUID
) -> ScanTarget | None:
    """None for an unknown connection, another org's (RLS) or ids that do not match."""
    connection = session.scalars(
        select(Connection).where(
            Connection.id == connection_id, Connection.organization_id == organization_id
        )
    ).one_or_none()
    if connection is None:
        return None
    return ScanTarget(
        connection_id=connection.id,
        provider=connection.provider,
        status=connection.status,
        external_tenant_id=connection.external_tenant_id,
        allowlist_version=connection.allowlist_version,
        credential_ref=connection.credential_ref,
        verifier_credential_ref=connection.verifier_credential_ref,
        google_client_id=connection.google_client_id,
        google_verifier_client_id=connection.google_verifier_client_id,
        google_subject_email=connection.google_subject_email,
        ms_tenant_id=connection.ms_tenant_id,
        consented_by_oid=connection.consented_by_oid,
    )


def begin_verification(
    session: Session, organization_id: uuid.UUID, connection_id: uuid.UUID, user_id: uuid.UUID
) -> Connection | None:
    """Onboarding step 6: an M365 connection, consented and still onboarding, starts verifying.

    None when the connection is unknown; ConnectionStateError before the sign-in and consent
    (#314), for Google, or once it is verifying, active or disconnected. The caller then queues
    the activation scan, which verifies at step 0 (#331).
    """
    connection = session.scalars(
        select(Connection)
        .where(Connection.id == connection_id, Connection.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if connection is None:
        return None
    if (
        connection.provider != "m365"
        or connection.status not in ONBOARDING
        or connection.ms_tenant_id is None
        or connection.consented_by_oid is None
    ):
        raise ConnectionStateError("not an M365 connection ready to verify")
    connection.status = "verifying"
    record(
        session,
        organization_id=organization_id,
        action="connection.verification_requested",
        target_type="connection",
        target_id=str(connection.id),
        actor_user_id=user_id,
        metadata={"provider": "m365"},
    )
    session.flush()
    return connection


ENDED_STATUSES = ("disconnected", "revoked")


def ended_connection_ids(session: Session, organization_id: uuid.UUID) -> set[uuid.UUID]:
    """Connections whose results no longer count: disconnected, or access revoked."""
    query = select(Connection.id).where(
        Connection.organization_id == organization_id, Connection.status.in_(ENDED_STATUSES)
    )
    return set(session.scalars(query))
