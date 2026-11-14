"""Scan job configuration from the environment (scanner-connectors spec, Runners)."""

from pathlib import Path

import pytest
from atesta_worker.scans import config_from_env, configure_scans, scan_config, timeout_seconds


def test_the_attempt_timeout_defaults_to_an_hour_and_is_bounded() -> None:
    assert timeout_seconds({}) == 3600
    assert timeout_seconds({"ATESTA_SCAN_TIMEOUT_SECONDS": "86400"}) == 86400
    for bad in ("59", "86401", "-5", "1h", ""):
        with pytest.raises(ValueError, match="ATESTA_SCAN_TIMEOUT_SECONDS"):
            timeout_seconds({"ATESTA_SCAN_TIMEOUT_SECONDS": bad})


def test_without_a_runner_the_worker_starts_and_scan_jobs_refuse() -> None:
    configure_scans(config_from_env({}))
    with pytest.raises(RuntimeError, match="not configured"):
        scan_config()


def test_only_the_fixture_runner_exists_and_only_in_development(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = {
        "ATESTA_SCAN_RUNNER": "fixture",
        "ATESTA_SCAN_STORE_DIR": str(tmp_path / "scans"),
        "ATESTA_SCAN_FIXTURES": str(tmp_path),
        "ATESTA_SCANNER_EXPECTED": str(tmp_path),
    }
    with pytest.raises(ValueError, match="must be 'fixture'"):
        config_from_env({**env, "ATESTA_SCAN_RUNNER": "docker"})
    monkeypatch.setenv("ATESTA_ENV", "prod")
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        config_from_env(env)
    monkeypatch.setenv("ATESTA_ENV", "test")
    config = config_from_env(env)
    assert config is not None and config.timeout_seconds == 3600
