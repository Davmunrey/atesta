"""Validate packs, or import immutable drafts into a loopback development database."""

import argparse
import json
import os
from pathlib import Path

from atesta_api.modules.compliance.api import import_preview, read_catalog
from atesta_api.modules.scanning.api import ENGINE_VERSION
from atesta_api.platform.db import make_engine
from atesta_api.platform.devenv import require_dev
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parents[3]
_LIBPQ_TARGET = ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE")


def loopback_dev_url(raw: str) -> URL:
    """The URL of the loopback atesta_dev database, or an error.

    No query string is accepted: libpq takes host, hostaddr, dbname and service from it, after
    this check has read the host and database from the URL itself. The same holds for libpq's
    environment variables (PGHOSTADDR overrides a loopback host), so those are refused too.
    """
    url = make_url(raw)
    if (
        url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.database != "atesta_dev"
        or url.query
        or any(os.environ.get(name) for name in _LIBPQ_TARGET)
    ):
        raise RuntimeError("preview import requires the loopback atesta_dev database")
    return url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import", dest="apply", action="store_true")
    args = parser.parse_args()
    expected = set()
    for provider in ("m365", "googleworkspace"):
        path = ROOT / "scanner" / "expected" / ENGINE_VERSION / f"{provider}.json"
        expected.update(json.loads(path.read_text())[provider])
    catalog = read_catalog(
        ROOT / "catalog", expected_checks=expected, engine_version=ENGINE_VERSION
    )
    if args.apply:
        require_dev("catalog preview")
        url = loopback_dev_url(os.environ["ATESTA_MIGRATION_DATABASE_URL"])
        engine = make_engine(url, sslmode="disable", null_pool=True)
        with engine.begin() as conn:
            conn.exec_driver_sql("SET LOCAL ROLE atesta_owner")
            import_preview(conn, catalog)
    for pack in catalog.packs:
        print(
            json.dumps(
                {
                    "framework": pack.metadata.id,
                    "state": pack.metadata.attributes.content_state,
                    "requirements": len(pack.requirements),
                    "candidate_mappings": sum(m.reviewed_by is None for m in pack.mappings),
                    "signed_mappings": sum(m.reviewed_by is not None for m in pack.mappings),
                    "controls": len(catalog.used_controls(pack)),
                    "fingerprint": catalog.fingerprint(pack),
                    "imported": args.apply,
                }
            )
        )


if __name__ == "__main__":
    main()
