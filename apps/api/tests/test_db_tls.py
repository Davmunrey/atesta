"""Server authentication by default: verify-full with the pinned RDS CA (tenant-data-layer spec)."""

import hashlib
import tomllib
from pathlib import Path
from typing import Any

import pytest
from atesta_api.main import app
from atesta_api.platform.db import RDS_CA, make_engine
from cryptography import x509
from fastapi.testclient import TestClient
from sqlalchemy import event

# Source: https://truststore.pki.rds.amazonaws.com/eu-south-2/eu-south-2-bundle.pem (2026-11-13)
RDS_CA_SHA256 = "6e4db6870d865a83140270728f62fbdb73202a3a017dc500ae2605e3d17344c0"


def connect_params(url: str, **kwargs: Any) -> dict[str, Any]:
    """The parameters handed to libpq, captured before any network I/O."""
    engine = make_engine(url, null_pool=True, **kwargs)
    captured: dict[str, Any] = {}

    def hook(dialect: object, conn_rec: object, cargs: object, cparams: dict[str, Any]) -> None:
        captured.update(cparams)
        raise RuntimeError("captured")

    event.listen(engine, "do_connect", hook)
    with pytest.raises(RuntimeError, match="captured"):
        engine.connect()
    return captured


def test_default_is_verify_full_with_the_pinned_ca(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PGSSLROOTCERT", str(tmp_path / "attacker.pem"))
    url = f"postgresql+psycopg://u@db.example/x?sslmode=disable&sslrootcert={tmp_path}/x.pem"
    params = connect_params(url)
    assert (params["sslmode"], params["sslrootcert"]) == ("verify-full", RDS_CA)


def test_disable_sets_no_root_certificate() -> None:
    params = connect_params("postgresql+psycopg://u@localhost/x", sslmode="disable")
    assert params["sslmode"] == "disable"
    assert "sslrootcert" not in params


@pytest.mark.parametrize("mode", ["allow", "prefer", "require", "verify-ca", "bogus"])
def test_weak_or_unknown_modes_are_refused(mode: str) -> None:
    with pytest.raises(ValueError, match="sslmode"):
        make_engine("postgresql+psycopg://u@db.example/x", sslmode=mode)


def test_pinned_bundle_is_the_official_eu_south_2_roots() -> None:
    data = Path(RDS_CA).read_bytes()
    assert hashlib.sha256(data).hexdigest() == RDS_CA_SHA256
    names = sorted(c.subject.rfc4514_string() for c in x509.load_pem_x509_certificates(data))
    assert len(names) == 3
    assert all("CN=Amazon RDS eu-south-2 Root CA" in n for n in names)


def test_api_refuses_to_start_with_a_weak_sslmode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATESTA_CATALOG_INCLUDE_DRAFTS", raising=False)
    monkeypatch.setenv("ATESTA_DATABASE_URL", "postgresql+psycopg://u@db.example/x")
    monkeypatch.setenv("ATESTA_DB_SSLMODE", "prefer")
    with pytest.raises(ValueError, match="sslmode"), TestClient(app):
        pass


def test_wheel_config_ships_the_bundle() -> None:
    """*.pem is git-ignored, and hatchling drops ignored files unless listed as artifacts."""
    api = Path(__file__).resolve().parents[1]
    wheel = tomllib.loads((api / "pyproject.toml").read_text())["tool"]["hatch"]["build"]
    globs = wheel["targets"]["wheel"]["artifacts"]
    bundle = Path(RDS_CA).relative_to(api)
    assert any(bundle.match(g) for g in globs)
