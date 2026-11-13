"""Fresh database for the web e2e suite (web-shell spec). Local and CI only.

Drops and recreates `atesta_e2e`, applies roles and migrations, and gives atesta_app a login.
Usage: uv run python apps/api/devtools/prepare_e2e_db.py postgresql+psycopg://postgres@host/postgres
"""

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from atesta_api.platform.db import make_engine
from sqlalchemy import make_url

API_DIR = Path(__file__).resolve().parents[1]
NAME = "atesta_e2e"
APP_PASSWORD = "e2e-only"  # noqa: S105 - throwaway local/CI database


def prepare(admin_url: str) -> None:
    os.environ.setdefault("ATESTA_DB_SSLMODE", "disable")
    admin = make_url(admin_url)
    with make_engine(admin, sslmode="disable", null_pool=True).connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{NAME}" WITH (FORCE)')
        conn.exec_driver_sql(f'CREATE DATABASE "{NAME}"')
    url = admin.set(database=NAME)
    with make_engine(url, sslmode="disable", null_pool=True).begin() as conn:
        conn.exec_driver_sql((API_DIR / "migrations" / "bootstrap.sql").read_text())
        conn.exec_driver_sql(f"ALTER ROLE atesta_app LOGIN PASSWORD '{APP_PASSWORD}'")
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    config.attributes["role"] = "atesta_owner"
    command.upgrade(config, "head")


if __name__ == "__main__":
    prepare(sys.argv[1])
