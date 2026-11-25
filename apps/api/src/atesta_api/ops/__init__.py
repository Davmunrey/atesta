"""One-off operations run with the migration credential as atesta_owner, never by the app.

They ship in the API image, so the hosted environment runs them as ECS tasks (the erasure
runner, operator-portal spec; the deploy and staff runbooks). They reach modules only through
their `api.py` (ADR-008), and print ids, counts and codes only (rule 2).
"""

import os

from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from atesta_api.platform.db import make_engine


def owner_engine() -> Engine:
    """The migration credential's engine; each transaction sets `ROLE atesta_owner` itself."""
    url = make_url(os.environ["ATESTA_MIGRATION_DATABASE_URL"])
    sslmode = os.environ.get("ATESTA_DB_SSLMODE", "verify-full")
    return make_engine(url, sslmode=sslmode, null_pool=True)
