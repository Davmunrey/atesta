"""Connections (scanner-connectors spec, Connections): create, read, disconnect.

Every query runs in the caller's org context (RLS). A connection starts waiting for its
onboarding: an M365 one for the admin's Microsoft sign-in and consent, a Google one for its two
service accounts. A removed connection becomes `disconnected`, never deleted.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from atesta_core.connectors.google import (
    email_domain,
    is_domain,
    is_service_account_id,
    is_subject_email,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atesta_api.modules.connections.models import Connection
from atesta_api.platform.audit import record

ALLOWLIST_VERSION = {"m365": "m365-v1", "google_workspace": "google-v1"}
# Still onboarding: a sign-in, a consent and a verification may (re)start here (#314, #331).
ONBOARDING = frozenset({"pending_setup", "incomplete", "over_privileged", "revoked"})
FIRST_STATUS = {"m365": "pending_setup", "google_workspace": "pending_provisioning"}
# Google says a delegation change can take up to 24 hours to reach every user (issue 398).
GOOGLE_PROPAGATION = timedelta(hours=24)


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
    primary_domain: str | None = None  # Google: the pin before the first `ok` (issue 398)
    google_unique_id: str | None = None  # the scan service account's IAM uniqueId
    google_verifier_unique_id: str | None = None
    verified_at: datetime | None = None  # the last `ok`: Google re-reads the audit log from it

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
        primary_domain=connection.primary_domain,
        google_unique_id=connection.google_unique_id,
        google_verifier_unique_id=connection.google_verifier_unique_id,
        verified_at=connection.verified_at,
    )


def _locked(
    session: Session, organization_id: uuid.UUID, connection_id: uuid.UUID
) -> Connection | None:
    return session.scalars(
        select(Connection)
        .where(Connection.id == connection_id, Connection.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()


def _ready_to_verify(connection: Connection) -> bool:
    if connection.status not in ONBOARDING:
        return False
    if connection.provider == "m365":  # signed in and consented (#314)
        return connection.ms_tenant_id is not None and connection.consented_by_oid is not None
    return None not in (  # provisioned by the owner and named by the customer (issue 398)
        connection.credential_ref,
        connection.verifier_credential_ref,
        connection.google_client_id,
        connection.google_verifier_client_id,
        connection.google_unique_id,
        connection.google_verifier_unique_id,
        connection.google_subject_email,
        connection.primary_domain,
    )


def begin_verification(
    session: Session, organization_id: uuid.UUID, connection_id: uuid.UUID, user_id: uuid.UUID
) -> Connection | None:
    """Onboarding: a connection ready to verify and still onboarding starts verifying.

    M365 is ready once signed in and consented (#314); Google once the owner provisioned its
    service accounts and the customer named the super admin (issue 398). None when the
    connection is unknown; ConnectionStateError when it is not ready, or once it is verifying,
    active or disconnected. The caller then queues the activation scan, which verifies (#331).
    """
    connection = _locked(session, organization_id, connection_id)
    if connection is None:
        return None
    if not _ready_to_verify(connection):
        raise ConnectionStateError("not a connection ready to verify")
    connection.status = "verifying"
    connection.verifying_since = func.now()
    record(
        session,
        organization_id=organization_id,
        action="connection.verification_requested",
        target_type="connection",
        target_id=str(connection.id),
        actor_user_id=user_id,
        metadata={"provider": connection.provider},
    )
    session.flush()
    return connection


@dataclass(frozen=True, slots=True)
class GoogleServiceAccounts:
    """What the owner's runbook created for one org (D7, D8): ids and references only."""

    client_id: str
    verifier_client_id: str
    unique_id: str
    verifier_unique_id: str
    credential_ref: str
    verifier_credential_ref: str

    def __post_init__(self) -> None:
        ids = (self.client_id, self.verifier_client_id, self.unique_id, self.verifier_unique_id)
        if not all(is_service_account_id(i) for i in ids) or len(set(ids[:2])) != 2:
            raise ValueError("service account ids must be numeric, one client per account")


def register_google_client(
    session: Session,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    accounts: GoogleServiceAccounts,
) -> Connection | None:
    """The owner's runbook result (D8): a provisioned Google connection waits for its setup.

    The database CHECKs refuse a reference to another org's secret. Runs in a `job` context.
    """
    connection = _locked(session, organization_id, connection_id)
    if connection is None:
        return None
    if connection.provider != "google_workspace" or connection.status != "pending_provisioning":
        raise ConnectionStateError("not a Google connection waiting for provisioning")
    connection.google_client_id = accounts.client_id
    connection.google_verifier_client_id = accounts.verifier_client_id
    connection.google_unique_id = accounts.unique_id
    connection.google_verifier_unique_id = accounts.verifier_unique_id
    connection.credential_ref = accounts.credential_ref
    connection.verifier_credential_ref = accounts.verifier_credential_ref
    connection.status = "pending_setup"
    record(
        session,
        organization_id=organization_id,
        action="connection.provisioned",
        target_type="connection",
        target_id=str(connection.id),
        metadata={"provider": connection.provider},
    )
    session.flush()
    return connection


class GoogleSubjectError(ValueError):
    """The email or domain is not one a Google super admin can have."""


def set_google_subject(
    session: Session,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    *,
    email: str,
    primary_domain: str | None,
    user_id: uuid.UUID,
) -> Connection | None:
    """The super admin Atesta reads as, and the customer's primary domain (onboarding step 3).

    The domain is the email's unless the admin sits on a secondary domain (owner, 2026-11-24).
    The email is never logged or put in the audit metadata (rule 2).
    """
    if not is_subject_email(email):
        raise GoogleSubjectError("not a Google user email")
    domain = email_domain(email) if primary_domain is None else primary_domain.lower()
    if not is_domain(domain):
        raise GoogleSubjectError("not a domain")
    connection = _locked(session, organization_id, connection_id)
    if connection is None:
        return None
    if connection.provider != "google_workspace" or connection.status not in (
        ONBOARDING | {"pending_provisioning"}
    ):
        raise ConnectionStateError("not a Google connection still onboarding")
    connection.google_subject_email = email
    connection.primary_domain = domain
    record(
        session,
        organization_id=organization_id,
        action="connection.google_subject_set",
        target_type="connection",
        target_id=str(connection.id),
        actor_user_id=user_id,
        metadata={"provider": connection.provider},
    )
    session.flush()
    return connection


def google_propagation_open(
    session: Session, organization_id: uuid.UUID, connection_id: uuid.UUID
) -> bool:
    """A verifying Google connection still inside Google's 24 h propagation window."""
    connection = _locked(session, organization_id, connection_id)
    if connection is None or connection.provider != "google_workspace":
        return False
    if connection.status != "verifying" or connection.verifying_since is None:
        return False
    now = session.execute(select(func.now())).scalar_one()
    return bool(now - connection.verifying_since < GOOGLE_PROPAGATION)


ENDED_STATUSES = ("disconnected", "revoked")


def ended_connection_ids(session: Session, organization_id: uuid.UUID) -> set[uuid.UUID]:
    """Connections whose results no longer count: disconnected, or access revoked."""
    query = select(Connection.id).where(
        Connection.organization_id == organization_id, Connection.status.in_(ENDED_STATUSES)
    )
    return set(session.scalars(query))
