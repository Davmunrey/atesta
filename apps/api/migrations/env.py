"""Alembic environment. Migrations run as atesta_owner (tenant-data-layer spec)."""

import os
import re
import sys
from pathlib import Path

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parent))  # lets versions import rls_v1

from atesta_api.modules.compliance import models as compliance_models  # noqa: E402, F401
from atesta_api.modules.evidence import models as evidence_models  # noqa: E402, F401
from atesta_api.modules.identity import models as identity_models  # noqa: E402, F401
from atesta_api.modules.scanning import models as scanning_models  # noqa: E402, F401
from atesta_api.platform import audit, tenancy  # noqa: E402, F401  (register models)
from atesta_api.platform.db import Base, make_engine  # noqa: E402

config = context.config
target_metadata = Base.metadata
_ROLE = re.compile(r"[a-z_][a-z0-9_]*")


def _include_name(name: str | None, type_: str, parent_names: object) -> bool:
    return type_ != "table" or name in target_metadata.tables


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url") or os.environ["ATESTA_MIGRATION_DATABASE_URL"]
    role = config.attributes.get("role") or os.environ.get("ATESTA_MIGRATION_ROLE")
    engine = make_engine(
        url, sslmode=os.environ.get("ATESTA_DB_SSLMODE", "verify-full"), null_pool=True
    )
    with engine.connect() as connection:
        if role:
            if not _ROLE.fullmatch(role):
                raise ValueError("bad migration role name")
            connection.exec_driver_sql(f"SET ROLE {role}")
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=_include_name,
            compare_server_default=True,  # `alembic check` also compares server defaults
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported")
run_migrations_online()
