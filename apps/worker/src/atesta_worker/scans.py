"""What scan jobs need besides the database: an output store, a runner and the expected lists.

Configured once at worker start from the environment (scanner-connectors spec, Runners and
local development). Only the dev-only fixture runner exists so far; LocalScanStore and
FixtureRunner refuse to start outside a development ATESTA_ENV, so a production worker cannot
be configured with them. Without ATESTA_SCAN_RUNNER the worker starts, and a scan job fails its
scan instead of leaving it active.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from atesta_api.modules.scanning.api import FixtureRunner, LocalScanStore, ScanRunner, ScanStore

DEFAULT_TIMEOUT_SECONDS = 3600
_TIMEOUT_RANGE = range(60, 86_401)


@dataclass(frozen=True, slots=True)
class ScanConfig:
    store: ScanStore
    runner: ScanRunner
    expected_root: Path
    timeout_seconds: int  # per attempt; the container runner enforces it (exit 21)


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
    if kind != "fixture":
        raise ValueError("ATESTA_SCAN_RUNNER must be 'fixture'")
    store = LocalScanStore(Path(env["ATESTA_SCAN_STORE_DIR"]))
    return ScanConfig(
        store=store,
        runner=FixtureRunner(store, Path(env["ATESTA_SCAN_FIXTURES"])),
        expected_root=Path(env["ATESTA_SCANNER_EXPECTED"]),
        timeout_seconds=timeout_seconds(env),
    )
