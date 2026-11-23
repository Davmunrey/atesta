"""PostgreSQL error text never reaches a log (log-redaction spec, rule 2).

PostgreSQL's DETAIL line carries the duplicate key's value or the whole failing row, and
hide_parameters does not hide it. uvicorn and Procrastinate log unhandled errors with exc_info.
"""

import io
import logging
import secrets
from collections.abc import Iterator

import pytest
from atesta_api.platform.logs import install_log_redaction
from sqlalchemy import Engine

EMAIL = "ana.garcia@example.com"
DOCUMENT = "SECRET-DOCUMENT-TEXT"


@pytest.fixture
def table(superuser: Engine) -> Iterator[str]:
    name = f"log_probe_{secrets.token_hex(4)}"
    with superuser.begin() as conn:
        conn.exec_driver_sql(
            f"CREATE TABLE {name} (email text CONSTRAINT {name}_email_key UNIQUE,"
            f" body text CONSTRAINT {name}_body_short CHECK (length(body) < 5),"
            " owner text NOT NULL)"
        )
        conn.exec_driver_sql(f"INSERT INTO {name} VALUES (%(e)s, 'ok', 'x')", {"e": EMAIL})  # noqa: S608 - name is ours
    yield name
    with superuser.begin() as conn:
        conn.exec_driver_sql(f"DROP TABLE {name}")


def _logged(logger_name: str, error: BaseException) -> str:
    install_log_redaction()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    try:
        logger.error("Exception in ASGI application\n", exc_info=error)
    finally:
        logger.removeHandler(handler)
    return stream.getvalue()


def _raise(superuser: Engine, sql: str, values: dict[str, str]) -> BaseException:
    try:
        with superuser.begin() as conn:
            conn.exec_driver_sql(sql, values)
    except Exception as error:  # noqa: BLE001 - the error is what the test logs
        return error
    raise AssertionError("the statement was expected to fail")


@pytest.mark.parametrize("logger_name", ["uvicorn.error", "procrastinate.worker"])
@pytest.mark.parametrize(
    ("statement", "values", "sqlstate", "constraint"),
    [
        ("INSERT INTO {t} VALUES (%(v)s, 'ok', 'x')", {"v": EMAIL}, "23505", "{t}_email_key"),
        (
            "INSERT INTO {t} VALUES ('b@c.d', %(v)s, 'x')",
            {"v": DOCUMENT},
            "23514",
            "{t}_body_short",
        ),  # noqa: E501
        ("INSERT INTO {t} VALUES (%(v)s, 'ok', NULL)", {"v": DOCUMENT}, "23502", None),
    ],
)
def test_a_database_error_is_logged_without_its_values(
    superuser: Engine,
    table: str,
    logger_name: str,
    statement: str,
    values: dict[str, str],
    sqlstate: str,
    constraint: str | None,
) -> None:
    text = _logged(logger_name, _raise(superuser, statement.format(t=table), values))
    assert EMAIL not in text and DOCUMENT not in text
    assert "DETAIL" not in text and "Failing row" not in text
    assert "sqlalchemy.exc.IntegrityError" in text
    assert f"sqlstate {sqlstate}" in text and f"table {table}" in text
    if constraint is not None:
        assert f"constraint {constraint.format(t=table)}" in text
    else:
        assert "column owner" in text
    assert "Traceback (most recent call last):" in text and "line " in text
