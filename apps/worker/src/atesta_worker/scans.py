"""What scan jobs need besides the database: an output store, a runner and the expected lists.

Configured once at worker start from the environment (scanner-connectors spec, Runners and
local development). The fixture and docker runners are dev-only: LocalScanStore, FixtureRunner,
LocalDockerRunner and LocalCredentialStore refuse to start outside a development ATESTA_ENV, so a
production worker cannot be configured with them. The Fargate runner and the S3 store (issue
444) run anywhere.
Without ATESTA_SCAN_RUNNER the worker starts, and a scan job fails its scan instead of leaving
it active.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import boto3  # type: ignore[import-untyped]  # boto3 ships no type stubs
from atesta_api.modules.scanning.api import (
    FargateRunner,
    FargateSettings,
    FixtureRunner,
    LocalCredentialStore,
    LocalDockerRunner,
    LocalScanStore,
    S3ScanStore,
    ScanRunner,
    ScanStore,
)

DEFAULT_TIMEOUT_SECONDS = 3600
_TIMEOUT_RANGE = range(60, 86_401)
# The platform certificate a Fargate scan reads with its task role (issue 444): a Secrets
# Manager reference in eu-south-2, never a local file.
_AWS_REF = re.compile(
    r"aws-sm:arn:aws:secretsmanager:eu-south-2:[0-9]{12}:secret:[A-Za-z0-9/_+=.@-]+"
)
_FARGATE = (
    "ATESTA_SCAN_BUCKET",
    "ATESTA_SCAN_CLUSTER",
    "ATESTA_SCAN_TASK_DEFINITION",
    "ATESTA_SCAN_SUBNETS",
    "ATESTA_SCAN_SECURITY_GROUP",
    "ATESTA_SCAN_ROLE_PREFIX",
    "ATESTA_M365_CREDENTIAL_REF",
    "ATESTA_SCANNER_EXPECTED",
)


@dataclass(frozen=True, slots=True)
class ScanConfig:
    store: ScanStore
    runner: ScanRunner
    expected_root: Path
    timeout_seconds: int  # per attempt; the container runner enforces it (exit 21)
    m365_credential_ref: str | None = None  # named in M365 job files (issue 444)


_config: ScanConfig | None = None


def configure_scans(config: ScanConfig | None) -> None:
    global _config
    _config = config


def scan_config() -> ScanConfig:
    if _config is None:
        raise RuntimeError("scan jobs are not configured (ATESTA_SCAN_RUNNER)")
    return _config


def timeout_seconds(env: Mapping[str, str]) -> int:
    raw = env.get("ATESTA_SCAN_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    value = int(raw) if raw.isdigit() else -1
    if value not in _TIMEOUT_RANGE:
        raise ValueError("ATESTA_SCAN_TIMEOUT_SECONDS must be 60 to 86400 seconds")
    return value


def config_from_env(env: Mapping[str, str]) -> ScanConfig | None:
    kind = env.get("ATESTA_SCAN_RUNNER")
    if kind is None:
        return None
    if kind == "fargate":
        return _fargate(env)
    if kind not in ("fixture", "docker"):
        raise ValueError("ATESTA_SCAN_RUNNER must be 'fixture', 'docker' or 'fargate'")
    store = LocalScanStore(Path(env["ATESTA_SCAN_STORE_DIR"]))
    timeout = timeout_seconds(env)
    runner: ScanRunner
    if kind == "fixture":
        runner = FixtureRunner(store, Path(env["ATESTA_SCAN_FIXTURES"]))
    else:
        runner = LocalDockerRunner(
            store_root=store.root,
            credentials=LocalCredentialStore(Path(env["ATESTA_SCAN_CREDENTIALS_DIR"])),
            image=env["ATESTA_SCAN_IMAGE"],
            m365_credential_ref=env.get("ATESTA_M365_CREDENTIAL_REF", "local:m365-scanner"),
            timeout_seconds=timeout,
            network=env.get("ATESTA_SCAN_NETWORK", "atesta-scan"),
        )
    return ScanConfig(
        store=store,
        runner=runner,
        expected_root=Path(env["ATESTA_SCANNER_EXPECTED"]),
        timeout_seconds=timeout,
    )


def _fargate(env: Mapping[str, str]) -> ScanConfig:
    """AWS (issue 444): RunTask per container run, outputs in the evidence bucket. Not dev-only."""
    missing = [name for name in _FARGATE if not env.get(name)]
    if missing:
        raise ValueError(f"the Fargate runner needs {', '.join(missing)}")
    ref = env["ATESTA_M365_CREDENTIAL_REF"]
    if not _AWS_REF.fullmatch(ref):
        raise ValueError("ATESTA_M365_CREDENTIAL_REF must be a Secrets Manager reference")
    region = env.get("AWS_DEFAULT_REGION")
    timeout = timeout_seconds(env)
    settings = FargateSettings(
        cluster=env["ATESTA_SCAN_CLUSTER"],
        task_definition=env["ATESTA_SCAN_TASK_DEFINITION"],
        subnets=tuple(s.strip() for s in env["ATESTA_SCAN_SUBNETS"].split(",") if s.strip()),
        security_group=env["ATESTA_SCAN_SECURITY_GROUP"],
        role_prefix=env["ATESTA_SCAN_ROLE_PREFIX"],
        timeout_seconds=timeout,
    )
    return ScanConfig(
        store=S3ScanStore(env["ATESTA_SCAN_BUCKET"], boto3.client("s3", region_name=region)),
        runner=FargateRunner(boto3.client("ecs", region_name=region), settings),
        expected_root=Path(env["ATESTA_SCANNER_EXPECTED"]),
        timeout_seconds=timeout,
        m365_credential_ref=ref,
    )
