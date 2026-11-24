"""Record a read-only verification (scanner-connectors spec, Read-only verification; rule 1).

The verifier runs in the scanner container and returns a report of ids and a verdict; this
module only records it, failing closed. The first `ok` pins the tenant (M365: the tenant the
admin signed in from); after that, an `ok` from any other tenant is refused. Anything but `ok`
leaves the connection unable to scan. A disconnected connection is never revived, and a `local:`
credential reference is refused outside development.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atesta_api.modules.connections.models import Connection
from atesta_api.modules.connections.service import ConnectionStateError
from atesta_api.modules.notifications.api import queue_event
from atesta_api.platform.audit import record
from atesta_api.platform.devenv import require_dev

VERDICT_STATUS = {
    "ok": "active",
    "incomplete": "incomplete",
    "over_privileged": "over_privileged",
    "revoked": "revoked",
}
TRANSIENT = "transient"  # 429, 5xx, network: retried with the scan, nothing recorded


class TenantMismatchError(ValueError):
    """The verified identity is not the connection's tenant."""


@dataclass(frozen=True, slots=True)
class VerificationReport:
    verdict: str
    tenant_id: str | None  # the identity the verifier read (step 2)
    granted: Mapping[str, Sequence[str]]  # permission, scope and role ids held (steps 3 to 5)
    missing: Sequence[str]
    extra: Sequence[str]
    limits: Sequence[str]  # what the verifier cannot read (Verifier limits)


def _pin(connection: Connection, tenant_id: str | None) -> None:
    expected = connection.external_tenant_id or connection.ms_tenant_id
    if tenant_id is None or (expected is not None and tenant_id != expected):
        raise TenantMismatchError(str(connection.id))
    if connection.external_tenant_id is None:
        connection.external_tenant_id = tenant_id  # immutable from now on (database trigger)


def record_verification(
    session: Session,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    report: VerificationReport,
) -> str:
    """The connection's status after this report."""
    if report.verdict != TRANSIENT and report.verdict not in VERDICT_STATUS:
        raise ValueError("unknown verification verdict")
    connection = session.scalars(
        select(Connection)
        .where(Connection.id == connection_id, Connection.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if connection is None:
        raise LookupError(str(connection_id))
    if connection.status == "disconnected":
        raise ConnectionStateError("a disconnected connection is never verified again")
    refs = (connection.credential_ref, connection.verifier_credential_ref)
    if any(ref is not None and ref.startswith("local:") for ref in refs):
        require_dev("local: credential references")
    if report.verdict == TRANSIENT:
        return connection.status
    if report.verdict == "ok":
        _pin(connection, report.tenant_id)
        connection.verified_at = func.now()
    if report.verdict == "revoked":
        connection.revoked_at = func.now()
    connection.status = VERDICT_STATUS[report.verdict]
    connection.granted = {
        "granted": {key: list(ids) for key, ids in report.granted.items()},
        "missing": list(report.missing),
        "extra": list(report.extra),
        "limits": list(report.limits),
    }
    action = "verified" if report.verdict == "ok" else report.verdict
    event_id = record(
        session,
        organization_id=organization_id,
        action=f"connection.{action}",
        target_type="connection",
        target_id=str(connection.id),
        metadata={
            "provider": connection.provider,
            "allowlist_version": connection.allowlist_version,
            "missing": len(report.missing),
            "extra": len(report.extra),
        },
    )
    queue_event(session, organization_id, event_id, f"connection.{action}")  # notifications spec
    session.flush()
    return connection.status
