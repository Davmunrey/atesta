"""db_bootstrap against a real Postgres: a role it sets up can log in with its URL password.

Uses throwaway roles, never atesta_app or atesta_owner: roles are cluster-wide, and other test
runs share this server.
"""

import secrets

import psycopg
from atesta_api.platform import db_bootstrap
from sqlalchemy import URL, Engine


def test_bootstrap_gives_login_with_a_password_that_needs_quoting(
    superuser: Engine, database: URL
) -> None:
    role = f"atesta_bootstrap_{secrets.token_hex(4)}"
    password = "it's 50% 'quoted' \\ pw"
    with superuser.begin() as conn:
        conn.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN')
    try:
        db_bootstrap.bootstrap(superuser, "SELECT 1;", {role: password})
        with psycopg.connect(
            host=database.host,
            port=database.port,
            dbname=database.database,
            user=role,
            password=password,
            sslmode="disable",
        ) as conn:
            assert conn.execute("SELECT current_user").fetchone() == (role,)
    finally:
        with superuser.begin() as conn:
            conn.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
