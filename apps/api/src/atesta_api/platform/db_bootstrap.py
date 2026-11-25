"""One-off database bootstrap for a hosted environment (hosted-environment spec, deploy runbook).

Runs once per environment as an ECS task built from the API image, with four ECS secrets: the
RDS master password (the `password` key of the RDS-managed secret) and the three role URLs. It
applies bootstrap.sql as the master user, then gives atesta_owner, atesta_app and atesta_operator
(ADR-017, the operator service) LOGIN with the password in each role's own URL, so the secrets
stay the single source of truth. Running it again changes nothing but the passwords. It prints
role names only, never a password or URL (rule 2).

    python -m atesta_api.platform.db_bootstrap [path/to/bootstrap.sql]
"""

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from psycopg import sql
from sqlalchemy import URL, Engine, make_url

from atesta_api.platform.db import make_engine

DEFAULT_SCRIPT = Path("apps/api/migrations/bootstrap.sql")  # relative to the image's /app
MASTER_USER = "atesta_master"  # infra/modules/rds
ROLES = (
    ("ATESTA_MIGRATION_DATABASE_URL", "atesta_owner"),
    ("ATESTA_DATABASE_URL", "atesta_app"),
    ("ATESTA_OPERATOR_DATABASE_URL", "atesta_operator"),
)


def role_passwords(env: Mapping[str, str]) -> dict[str, str]:
    """Each role's password, read from its own connection URL; refuses a URL for another role."""
    passwords: dict[str, str] = {}
    for variable, role in ROLES:
        url = make_url(env[variable])
        if url.username != role:
            raise ValueError(f"{variable} must log in as {role}")
        if not url.password:
            raise ValueError(f"{variable} has no password")
        passwords[role] = str(url.password)
    return passwords


def master_url(env: Mapping[str, str]) -> URL:
    """The master user on the same host, port and database as the application URL."""
    app = make_url(env["ATESTA_DATABASE_URL"])
    return app.set(username=MASTER_USER, password=env["ATESTA_MASTER_PASSWORD"])


def bootstrap(engine: Engine, script: str, passwords: Mapping[str, str]) -> None:
    """Apply the roles script, then set LOGIN and the password of each role, in one transaction."""
    with engine.begin() as conn:
        conn.exec_driver_sql(script)
        raw = conn.connection.driver_connection
        if raw is None:
            raise RuntimeError("no driver connection")
        with raw.cursor() as cursor:  # no parameters: a % in a password stays literal
            for role, password in passwords.items():
                statement = sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
                # Composed with sql.Identifier and sql.Literal: psycopg quotes both.
                cursor.execute(statement)  # noqa: E501  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query


def main() -> None:
    env = os.environ
    passwords = role_passwords(env)
    engine = make_engine(
        master_url(env), sslmode=env.get("ATESTA_DB_SSLMODE", "verify-full"), null_pool=True
    )
    script = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SCRIPT
    bootstrap(engine, script.read_text(), passwords)
    engine.dispose()
    print(f"bootstrap done; LOGIN set for {', '.join(sorted(passwords))}")


if __name__ == "__main__":
    main()
