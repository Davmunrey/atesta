"""`atesta-dev-scan`: one synthetic scan end to end, no network and no credentials (dev only).

Loads the synthetic catalog fixture as atesta_owner, then in a fixed dev org replays the
synthetic M365 OCSF fixture, ingests it against the committed expected list and scores it with
drafts included. Fails unless every synthetic framework has a snapshot for the scan. A rerun
changes nothing.

Environment: ATESTA_ENV (local, dev or test), ATESTA_MIGRATION_DATABASE_URL (a role that may
SET ROLE atesta_owner), ATESTA_DATABASE_URL (atesta_app), ATESTA_DB_SSLMODE, and optionally
ATESTA_DEV_SCAN_DIR (default .atesta-dev/scans in the repository).
"""

import os
import sys
import uuid
from pathlib import Path

import yaml
from atesta_api.modules.compliance.api import load_catalog_fixture
from atesta_api.modules.identity.api import (
    ContextReason,
    ensure_dev_organization,
    enter_org_context,
)
from atesta_api.modules.scanning.api import (
    ENGINE_VERSION,
    LocalScanStore,
    run_fixture_scan,
    snapshot_scores,
)
from atesta_api.platform.db import make_engine
from atesta_api.platform.devenv import require_dev
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

REPO = Path(__file__).resolve().parents[4]
CATALOG = REPO / "apps" / "api" / "tests" / "fixtures" / "catalog" / "synthetic.yaml"
FIXTURES = REPO / "scanner" / "fixtures" / "synthetic"
EXPECTED = REPO / "scanner" / "expected"
DEV_ORG = uuid.UUID("de000000-0000-4000-8000-000000000001")
DEV_CONNECTION = uuid.UUID("de000000-0000-4000-8000-0000000000c1")
DEV_SCAN = uuid.UUID("de000000-0000-4000-8000-0000000000a1")
FIXTURE_TENANT = "11111111-1111-4111-8111-111111111111"  # scanner/fixtures/synthetic/README.md


def run(
    owner_url: str | URL, app_url: str | URL, sslmode: str, store_root: Path
) -> dict[str, uuid.UUID]:
    """Return {framework key: snapshot id} for the dev scan."""
    require_dev("atesta-dev-scan")
    os.environ["ATESTA_CATALOG_INCLUDE_DRAFTS"] = "true"  # synthetic frameworks are drafts
    owner = make_engine(owner_url, sslmode=sslmode, null_pool=True)
    with owner.begin() as conn:
        conn.exec_driver_sql("SET LOCAL ROLE atesta_owner")
        keys = load_catalog_fixture(
            conn, yaml.safe_load(CATALOG.read_text()), "prowler", ENGINE_VERSION
        )
    app = make_engine(app_url, sslmode=sslmode, null_pool=True)
    with Session(app) as session, session.begin():
        ensure_dev_organization(session, DEV_ORG, "Atesta dev")
        run_fixture_scan(
            session,
            organization_id=DEV_ORG,
            scan_id=DEV_SCAN,
            connection_id=DEV_CONNECTION,
            provider="m365",
            tenant=FIXTURE_TENANT,
            store=LocalScanStore(store_root),
            fixtures=FIXTURES,
            expected_root=EXPECTED,
        )
    scoring = app.execution_options(isolation_level="REPEATABLE READ")
    with Session(scoring) as session, session.begin():
        enter_org_context(session, DEV_ORG, ContextReason.JOB)
        snapshots = snapshot_scores(session, DEV_SCAN)
    missing = sorted(set(keys) - snapshots.keys())
    if missing:
        raise RuntimeError(f"no snapshot for synthetic frameworks: {', '.join(missing)}")
    return snapshots


def main() -> None:
    store = Path(os.environ.get("ATESTA_DEV_SCAN_DIR", REPO / ".atesta-dev" / "scans"))
    try:
        snapshots = run(
            os.environ["ATESTA_MIGRATION_DATABASE_URL"],
            os.environ["ATESTA_DATABASE_URL"],
            os.environ.get("ATESTA_DB_SSLMODE", "verify-full"),
            store,
        )
    except (KeyError, RuntimeError) as error:
        sys.exit(f"atesta-dev-scan: {error}")
    for key, snapshot_id in sorted(snapshots.items()):
        print(f"{key}\t{snapshot_id}")


if __name__ == "__main__":
    main()
