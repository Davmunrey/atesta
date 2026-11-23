"""Erase a closed organization (organization-closure spec). Operator only; dry run by default.

    uv run python -m apps.api.devtools.erase_org --org <uuid> --note "contract ended, ticket 42"
    uv run python -m apps.api.devtools.erase_org --org <uuid> --note "..." --execute

Connects with ATESTA_MIGRATION_DATABASE_URL and acts as atesta_owner, the only role that may
delete append-only rows (ADR-012). It refuses an organization that has not asked to close, or
whose 30-day grace period has not ended. A receipt with row counts, and no names or content, is
written to erasure_receipts. Follow docs/runbooks/offboarding.md.
"""

import argparse
import json
import os
import sys
import uuid

from atesta_api.modules.identity.erasure import ErasureRefusedError, erase_organization
from atesta_api.platform.db import make_engine
from sqlalchemy.engine import make_url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, type=uuid.UUID)
    parser.add_argument("--note", required=True, help="why, and the ticket or request reference")
    parser.add_argument("--execute", action="store_true", help="delete; without it, a dry run")
    args = parser.parse_args()
    url = make_url(os.environ["ATESTA_MIGRATION_DATABASE_URL"])
    engine = make_engine(
        url, sslmode=os.environ.get("ATESTA_DB_SSLMODE", "verify-full"), null_pool=True
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("SET LOCAL ROLE atesta_owner")
        try:
            counts = erase_organization(conn, args.org, note=args.note, execute=args.execute)
        except ErasureRefusedError as refused:
            print(f"refused: {refused}", file=sys.stderr)
            sys.exit(2)
    mode = "erased" if args.execute else "dry run, nothing deleted"
    print(json.dumps({"organization": str(args.org), "mode": mode, "rows": counts}, indent=1))


if __name__ == "__main__":
    main()
