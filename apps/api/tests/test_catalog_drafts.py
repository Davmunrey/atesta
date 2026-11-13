"""ATESTA_CATALOG_INCLUDE_DRAFTS fails closed (control-model spec, rule 10 at runtime)."""

import pytest
from atesta_api.main import app
from atesta_api.modules.compliance.api import include_drafts
from fastapi.testclient import TestClient


@pytest.mark.parametrize("env", [None, "prod", "production", "staging", ""])
def test_flag_outside_a_dev_env_refuses(monkeypatch: pytest.MonkeyPatch, env: str | None) -> None:
    monkeypatch.setenv("ATESTA_CATALOG_INCLUDE_DRAFTS", "true")
    if env is None:
        monkeypatch.delenv("ATESTA_ENV", raising=False)
    else:
        monkeypatch.setenv("ATESTA_ENV", env)
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        include_drafts()


@pytest.mark.parametrize("env", ["local", "dev", "test"])
def test_flag_in_a_dev_env_is_honoured(monkeypatch: pytest.MonkeyPatch, env: str) -> None:
    monkeypatch.setenv("ATESTA_CATALOG_INCLUDE_DRAFTS", "true")
    monkeypatch.setenv("ATESTA_ENV", env)
    assert include_drafts() is True


def test_no_flag_means_no_drafts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATESTA_CATALOG_INCLUDE_DRAFTS", raising=False)
    monkeypatch.delenv("ATESTA_ENV", raising=False)
    assert include_drafts() is False


def test_api_refuses_to_start_with_the_flag_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """Checked first in the lifespan, before any database or network setup."""
    monkeypatch.setenv("ATESTA_CATALOG_INCLUDE_DRAFTS", "true")
    monkeypatch.delenv("ATESTA_ENV", raising=False)
    monkeypatch.delenv("ATESTA_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="ATESTA_CATALOG_INCLUDE_DRAFTS"), TestClient(app):
        pass
