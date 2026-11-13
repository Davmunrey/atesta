"""One synthetic scan with no Docker, network or credentials (scanner-connectors spec, dev only)."""

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.scanning.expected import ENGINE_VERSION, expected_checks
from atesta_api.modules.scanning.ingest import ENGINE, ingest_scan
from atesta_api.modules.scanning.models import Scan
from atesta_api.modules.scanning.runners import FixtureRunner, ScanJob, ScanStore, output_prefix
from atesta_api.platform.devenv import require_dev


def run_fixture_scan(
    session: Session,
    *,
    organization_id: uuid.UUID,
    scan_id: uuid.UUID,
    connection_id: uuid.UUID,
    provider: str,
    tenant: str,
    store: ScanStore,
    fixtures: Path,
    expected_root: Path,
) -> str:
    """Replay a synthetic fixture as one collected attempt and ingest it. Reruns change nothing.

    The caller's session is in organization_id's context (RLS rejects any other org).
    """
    require_dev("run_fixture_scan")
    scan = session.scalars(select(Scan).where(Scan.id == scan_id)).one_or_none()
    if scan is not None:
        return scan.status
    org = organization_id
    prefix = output_prefix(org, scan_id, 1)
    if not store.list(prefix):  # outputs are write-once; a failed earlier run may have left them
        FixtureRunner(store, fixtures).run(ScanJob(org, scan_id, 1, provider))
    session.add(
        Scan(
            id=scan_id,
            organization_id=org,
            connection_id=connection_id,
            provider=provider,
            trigger="user",
            status="collected",
            attempts=1,
            engine=ENGINE,
            engine_version=ENGINE_VERSION,
            output_prefix=prefix,
        )
    )
    session.flush()
    listed = expected_checks(expected_root, provider)
    return ingest_scan(session, scan_id, store=store, tenant=tenant, listed=listed, excluded={})
