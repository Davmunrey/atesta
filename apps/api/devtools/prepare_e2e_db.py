"""Fresh database for the web e2e suite (web-shell spec). Local and CI only.

Drops and recreates `atesta_e2e`, applies roles and migrations, and gives atesta_app a login.
With --operator, for the operator portal's suite (#487), it also gives atesta_operator a login and
seeds staff for the fake staff pool (fake_cognito.py --staff) and organizations.
Usage: uv run python apps/api/devtools/prepare_e2e_db.py postgresql+psycopg://postgres@host/postgres
"""

import os
import sys
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from atesta_api.platform.db import make_engine
from sqlalchemy import make_url, text

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


OPERATOR_PASSWORD = "e2e-only"  # noqa: S105 - throwaway local/CI database
# fake_cognito.py: a staff member's `sub` is uuid5 of this namespace and the email.
_SUB_NAMESPACE = uuid.UUID("6f1a8a3e-1b3c-4c2e-9d55-2f0e6f7c9a10")
STAFF = {
    "admin@atesta.test": "admin",
    "second-admin@atesta.test": "admin",
    "billing@atesta.test": "billing",
    "support@atesta.test": "support",
    "rotating@atesta.test": "support",  # the team screen's e2e changes this one's role
}


def seed_operator(admin_url: str) -> None:
    url = make_url(admin_url).set(database=NAME)
    with make_engine(url, sslmode="disable", null_pool=True).begin() as conn:
        conn.exec_driver_sql(f"ALTER ROLE atesta_operator LOGIN PASSWORD '{OPERATOR_PASSWORD}'")
        for email, role in STAFF.items():
            conn.execute(
                text(
                    "INSERT INTO operator_staff (id, cognito_sub, email, role)"
                    " VALUES (gen_random_uuid(), :s, :e, :r)"
                ),
                {"s": str(uuid.uuid5(_SUB_NAMESPACE, email)), "e": email, "r": role},
            )
        conn.execute(
            text(
                "INSERT INTO operator_staff (id, cognito_sub, email, role, disabled_at) VALUES"
                " (gen_random_uuid(), 'left-the-team', 'former@atesta.test', 'support', now())"
            )
        )
        # Enough organizations for a second page of 50, named so a search finds one.
        conn.execute(
            text(
                "INSERT INTO organizations (id, name, created_at)"
                " SELECT gen_random_uuid(), 'Organización de prueba ' || lpad(n::text, 2, '0'),"
                " now() - n * interval '1 day' FROM generate_series(1, 52) AS n"
            )
        )
        conn.execute(
            text(
                "INSERT INTO organizations (id, name, suspended_at, suspension_reason)"
                " VALUES (gen_random_uuid(), 'Clínica Norte S.L.', now() - interval '2 days',"
                " 'non_payment')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO billing_profiles (organization_id, legal_name, tax_id, address_line1,"
                " postal_code, city, region, country, contact_email) SELECT id,"
                " 'Clínica Norte Sociedad Limitada', 'B12345678', 'Calle Mayor 1', '28001',"
                " 'Madrid', 'Madrid', 'ES', 'facturas@example.test' FROM organizations"
                " WHERE name = 'Clínica Norte S.L.'"
            )
        )
        # An earlier erasure's receipt: the organization is gone, only its id and counts stay.
        conn.execute(
            text(
                "INSERT INTO erasure_receipts (id, organization_id, closure_requested_at, note,"
                " row_counts) VALUES (gen_random_uuid(), gen_random_uuid(),"
                " now() - interval '40 days', 'e2e', '{\"organizations\": 1, \"memberships\": 3}')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO subscriptions (organization_id, plan, addons) SELECT id, 'pro',"
                " '{}' FROM organizations WHERE name = 'Organización de prueba 01'"
            )
        )


if __name__ == "__main__":
    prepare(sys.argv[1])
    if "--operator" in sys.argv[2:]:
        seed_operator(sys.argv[1])
