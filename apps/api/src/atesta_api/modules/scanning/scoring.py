"""Scan results to control results to score snapshots (scanner-connectors spec).

Scores come only from catalog rows read through compliance.api; no framework name appears here
(rule 9). A snapshot for a scan is computed as of that scan: the scan's own results plus, for
every other connection, its latest scan ingested no later. A retried job therefore writes the
same snapshot, and one connection's scan never erases another's results.

Manual controls take the human review current at the same moment (manual-control-review spec).
A review recorded later reaches the score through rescore_reviews: a correction snapshot of the
latest scan, so recorded history is never rewritten.
"""

import uuid
from datetime import datetime

from atesta_core.controls import control_results
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.api import (
    active_control_checks,
    reviewed_control_results,
    scoreable_framework_keys,
    snapshot_chain_tip,
    snapshot_framework,
)
from atesta_api.modules.scanning.ingest import ScanNotFoundError
from atesta_api.modules.scanning.models import Scan, ScanCheckResult

RESCORE_TASK = "atesta:rescore_reviews"  # the worker's namespaced name; a worker test pins it


def _ingested(session: Session, scan_id: uuid.UUID) -> Scan | None:
    scan = session.scalars(select(Scan).where(Scan.id == scan_id)).one_or_none()
    if scan is None:
        raise ScanNotFoundError(str(scan_id))
    return scan if scan.ingested_at is not None else None


def _as_of(session: Session, scan: Scan) -> list[tuple[str, str, str]]:
    others = (
        select(Scan.id)
        .where(
            Scan.connection_id != scan.connection_id,
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
    if scan is None or scan.ingested_at is None:
        return {}
    results = control_results(active_control_checks(session), _as_of(session, scan))
    results += reviewed_control_results(session, scan.organization_id, scan.ingested_at)
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


def rescore_reviews(
    session: Session, organization_id: uuid.UUID, as_of: datetime | None = None
) -> dict[str, uuid.UUID]:
    """{framework key: correction id} for the org's latest ingested scan; empty without one.

    Check results stay as of that scan; manual controls take the reviews current at as_of
    (default: now). Each correction supersedes the tip of its chain, so the chain stays linear.
    The caller's transaction must be REPEATABLE READ.
    """
    scan = session.scalars(
        select(Scan)
        .where(Scan.organization_id == organization_id, Scan.ingested_at.is_not(None))
        .order_by(Scan.ingested_at.desc(), Scan.id.desc())
        .limit(1)
    ).one_or_none()
    if scan is None:
        return {}
    moment = as_of or session.execute(select(func.now())).scalar_one()
    results = control_results(active_control_checks(session), _as_of(session, scan))
    results += reviewed_control_results(session, organization_id, moment)
    created = {}
    for key in scoreable_framework_keys(session):
        snapshot_id = snapshot_framework(
            session,
            organization_id=organization_id,
            framework_key=key,
            scan_id=scan.id,
            control_results=results,
            supersedes_id=snapshot_chain_tip(session, organization_id, key, scan.id),
        )
        if snapshot_id is not None:
            created[key] = snapshot_id
    return created
