"""The preview import writes as the schema owner, so it reaches a loopback dev database only."""

import importlib
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def preview(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    return importlib.import_module("devtools.preview_catalog")


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_a_loopback_dev_database_is_accepted(preview: Any, host: str) -> None:
    url = preview.loopback_dev_url(f"postgresql+psycopg://postgres@{host}:5432/atesta_dev")
    assert url.database == "atesta_dev"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://postgres@db.example:5432/atesta_dev",
        "postgresql+psycopg://postgres@127.0.0.1:5432/postgres",
        # libpq reads these query parameters after the guard has looked at host and database.
        "postgresql+psycopg://postgres@127.0.0.1:5432/atesta_dev?host=db.example",
        "postgresql+psycopg://postgres@127.0.0.1:5432/atesta_dev?hostaddr=10.0.0.5",
        "postgresql+psycopg://postgres@127.0.0.1:5432/atesta_dev?dbname=prod",
        "postgresql+psycopg://postgres@127.0.0.1:5432/atesta_dev?service=prod",
        "postgresql+psycopg://postgres@/atesta_dev?host=db.example",
    ],
)
def test_anything_else_is_refused(preview: Any, url: str) -> None:
    with pytest.raises(RuntimeError, match="loopback"):
        preview.loopback_dev_url(url)


@pytest.mark.parametrize("variable", ["PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"])
def test_libpq_connection_variables_are_refused(
    preview: Any, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    """libpq reads these after the guard; PGHOSTADDR=<remote> overrides a loopback host."""
    monkeypatch.setenv(variable, "10.0.0.5")
    with pytest.raises(RuntimeError, match="loopback"):
        preview.loopback_dev_url("postgresql+psycopg://postgres@127.0.0.1:5432/atesta_dev")
