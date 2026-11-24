"""Scan job configuration from the environment (scanner-connectors spec, Runners)."""

from pathlib import Path

import pytest
from atesta_api.modules.scanning.api import FixtureRunner, LocalDockerRunner
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


@pytest.mark.parametrize(
    ("kind", "runner"), [("fixture", FixtureRunner), ("docker", LocalDockerRunner)]
)
def test_only_dev_runners_exist_and_only_in_development(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, runner: type
) -> None:
    (tmp_path / "secrets").mkdir()
    env = {
        "ATESTA_SCAN_RUNNER": kind,
        "ATESTA_SCAN_STORE_DIR": str(tmp_path / "scans"),
        "ATESTA_SCAN_FIXTURES": str(tmp_path),
        "ATESTA_SCANNER_EXPECTED": str(tmp_path),
        "ATESTA_SCAN_CREDENTIALS_DIR": str(tmp_path / "secrets"),
        "ATESTA_SCAN_IMAGE": "atesta-scanner:dev",
    }
    with pytest.raises(ValueError, match="must be 'fixture', 'docker' or 'fargate'"):
        config_from_env({**env, "ATESTA_SCAN_RUNNER": "ec2"})
    monkeypatch.setenv("ATESTA_ENV", "prod")
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        config_from_env(env)
    monkeypatch.setenv("ATESTA_ENV", "test")
    config = config_from_env(env)
    assert config is not None and config.timeout_seconds == 3600
    assert isinstance(config.runner, runner)


FARGATE = {
    "ATESTA_SCAN_RUNNER": "fargate",
    "ATESTA_SCAN_BUCKET": "atesta-prod-evidence",
    "ATESTA_SCAN_CLUSTER": "atesta-prod",
    "ATESTA_SCAN_TASK_DEFINITION": "atesta-prod-scan",
    "ATESTA_SCAN_SUBNETS": "subnet-a, subnet-b",
    "ATESTA_SCAN_SECURITY_GROUP": "sg-scan",
    "ATESTA_SCAN_ROLE_PREFIX": "arn:aws:iam::123456789012:role/atesta-scan/prod/",
    "ATESTA_M365_CREDENTIAL_REF": (
        "aws-sm:arn:aws:secretsmanager:eu-south-2:123456789012:secret:atesta/prod/m365-scanner-AbC123"
    ),
    "ATESTA_SCANNER_EXPECTED": "/opt/atesta/expected",
    "AWS_DEFAULT_REGION": "eu-south-2",
}


def test_the_fargate_runner_runs_in_production_with_the_s3_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """issue 444: the one runner that is not dev-only."""
    from atesta_api.modules.scanning.api import FargateRunner, S3ScanStore

    monkeypatch.setenv("ATESTA_ENV", "prod")
    config = config_from_env(FARGATE)
    assert config is not None
    assert isinstance(config.runner, FargateRunner) and isinstance(config.store, S3ScanStore)
    assert config.m365_credential_ref == FARGATE["ATESTA_M365_CREDENTIAL_REF"]
    assert config.runner.settings.subnets == ("subnet-a", "subnet-b")
    assert config.runner.settings.timeout_seconds == 3600


@pytest.mark.parametrize("missing", sorted(set(FARGATE) - {"AWS_DEFAULT_REGION"}))
def test_a_missing_fargate_setting_is_named(missing: str) -> None:
    if missing == "ATESTA_SCAN_RUNNER":
        assert config_from_env({k: v for k, v in FARGATE.items() if k != missing}) is None
        return
    with pytest.raises(ValueError, match=missing):
        config_from_env({k: v for k, v in FARGATE.items() if k != missing})


def test_the_platform_certificate_ref_must_be_a_secrets_manager_ref() -> None:
    with pytest.raises(ValueError, match="ATESTA_M365_CREDENTIAL_REF"):
        config_from_env({**FARGATE, "ATESTA_M365_CREDENTIAL_REF": "local:m365-scanner"})
