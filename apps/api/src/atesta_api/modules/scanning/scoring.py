"""Scan results to control results to score snapshots (scanner-connectors spec).

Scores come only from catalog rows read through compliance.api; no framework name appears here
(rule 9). A snapshot for a scan is computed as of that scan: the scan's own results plus, for
every other connection, its latest scan ingested no later. A retried job therefore writes the
same snapshot, and one connection's scan never erases another's results.
"""

import uuid

from atesta_core.controls import control_results
from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.api import (
    active_control_checks,
    scoreable_framework_keys,
    snapshot_framework,
)
from atesta_api.modules.connections.api import ended_connection_ids
from atesta_api.modules.scanning.ingest import ScanNotFoundError
from atesta_api.modules.scanning.models import Scan, ScanCheckResult


def _ingested(session: Session, scan_id: uuid.UUID) -> Scan | None:
    scan = session.scalars(select(Scan).where(Scan.id == scan_id)).one_or_none()
    if scan is None:
        raise ScanNotFoundError(str(scan_id))
    return scan if scan.ingested_at is not None else None


def _as_of(session: Session, scan: Scan) -> list[tuple[str, str, str]]:
    """This scan's results and the latest of every other connection that has not ended.

    A disconnected or revoked connection's last scan describes a tenant Atesta no longer reads:
    its passes would linger and its failures could never clear (spec: active connections).
    """
    ended = ended_connection_ids(session, scan.organization_id)
    others = (
        select(Scan.id)
        .where(
            Scan.connection_id != scan.connection_id,
            Scan.connection_id.not_in(ended),
            Scan.ingested_at.is_not(None),
            Scan.ingested_at <= scan.ingested_at,
        )
        .distinct(Scan.connection_id)
        .order_by(Scan.connection_id, Scan.ingested_at.desc(), Scan.id.desc())
    )
    scans = [scan.id, *session.execute(others).scalars()]
    rows = session.execute(
        select(ScanCheckResult.engine, ScanCheckResult.check_id, ScanCheckResult.status)
        .where(ScanCheckResult.scan_id.in_(scans))
        .order_by(ScanCheckResult.scan_id, ScanCheckResult.engine, ScanCheckResult.check_id)
    )
    return [(engine, check_id, status) for engine, check_id, status in rows]


def latest_check_results(session: Session, scan_id: uuid.UUID) -> list[tuple[str, str, str]]:
    """(engine, check_id, status) of the latest ingested scan per connection, as of this scan."""
    scan = _ingested(session, scan_id)
    return [] if scan is None else _as_of(session, scan)


def snapshot_scores(session: Session, scan_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """{framework key: snapshot id}, one per scoreable framework; empty if not ingested.

    The caller's transaction must be REPEATABLE READ (snapshot_framework refuses otherwise).
    """
    scan = _ingested(session, scan_id)
    if scan is None:
        return {}
    results = control_results(active_control_checks(session), _as_of(session, scan))
    created = {}
    for key in scoreable_framework_keys(session):
        snapshot_id = snapshot_framework(
            session,
            organization_id=scan.organization_id,
            framework_key=key,
            scan_id=scan.id,
            control_results=results,
        )
        if snapshot_id is not None:
            created[key] = snapshot_id
    return created
