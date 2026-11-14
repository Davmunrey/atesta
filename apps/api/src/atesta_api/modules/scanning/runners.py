"""Scan runners and output stores (scanner-connectors spec, Runners and local development).

Outputs live under <org_id>/scans/<scan_id>/attempt-<n>/out/ and are write-once (ADR-004). The
local store and the fixture runner are dev-only: they refuse to start unless ATESTA_ENV names a
development environment, so a production process can never use them.
"""

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from atesta_core.manifest import build_manifest

from atesta_api.platform.devenv import require_dev

OCSF_FILE = "prowler.ocsf.json"
MANIFEST_FILE = "manifest.json"
JOB_FILE = "job.json"  # next to out/, written by the worker before the run
_SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
# Atesta provider -> Prowler provider folder name.
_PROWLER_PROVIDER = {"m365": "m365", "google_workspace": "googleworkspace"}


class OutputExistsError(FileExistsError):
    """Scan outputs are write-once."""


@dataclass(frozen=True, slots=True)
class ScanJob:
    organization_id: uuid.UUID
    scan_id: uuid.UUID
    attempt: int
    provider: str
    credential_ref: str | None = None  # Google: the connection's; M365 uses the platform's (D5)


class ScanStore(Protocol):
    def write(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def list(self, prefix: str) -> list[str]: ...


class ScanRunner(Protocol):
    def run(self, job: ScanJob) -> int: ...


def output_prefix(organization_id: uuid.UUID, scan_id: uuid.UUID, attempt: int) -> str:
    if attempt < 1:
        raise ValueError("attempt must be 1 or more")
    return f"{organization_id}/scans/{scan_id}/attempt-{attempt}/out/"


def _segments(key: str) -> list[str]:
    parts = key.split("/")
    if not key or not all(_SEGMENT.fullmatch(part) for part in parts):
        raise ValueError(f"unsafe store key: {key!r}")
    return parts


class LocalScanStore:
    """A directory laid out like the S3 bucket, for local development."""

    def __init__(self, root: Path) -> None:
        require_dev("LocalScanStore")
        root.mkdir(parents=True, exist_ok=True)
        self._root = root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, key: str) -> Path:
        path = self._root.joinpath(*_segments(key))
        if not path.resolve().is_relative_to(self._root):  # a symlink must not lead outside
            raise ValueError(f"unsafe store key: {key!r}")
        return path

    def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(data)
        except FileExistsError:
            raise OutputExistsError(key) from None

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def list(self, prefix: str) -> list[str]:
        base = self._path(prefix.rstrip("/"))
        if not base.is_dir():
            return []
        return sorted(p.relative_to(self._root).as_posix() for p in base.rglob("*") if p.is_file())


class FixtureRunner:
    """Replays a committed OCSF fixture as a scan output, with no Docker and no credentials."""

    def __init__(
        self,
        store: ScanStore,
        fixtures: Path,
        fixture: str = "scan.ocsf.json",
        exit_code: int = 0,
    ) -> None:
        require_dev("FixtureRunner")
        self._store, self._fixtures, self._fixture = store, fixtures, fixture
        self._exit_code = exit_code

    def run(self, job: ScanJob) -> int:
        if self._exit_code != 0:
            return self._exit_code
        folder = _PROWLER_PROVIDER.get(job.provider)
        if folder is None:
            raise ValueError("unknown provider")
        data = (self._fixtures / folder / self._fixture).read_bytes()
        prefix = output_prefix(job.organization_id, job.scan_id, job.attempt)
        try:  # like the wrapper, honor the job file's exclusions (Prowler --excluded-check)
            excluded = set(
                json.loads(self._store.read(prefix.removesuffix("out/") + JOB_FILE))["excluded"]
            )
        except FileNotFoundError:
            excluded = set()
        if excluded:
            findings = json.loads(data)
            kept = [f for f in findings if f["metadata"]["event_code"] not in excluded]
            data = json.dumps(kept).encode()
        self._store.write(prefix + OCSF_FILE, data)
        self._store.write(prefix + MANIFEST_FILE, build_manifest({OCSF_FILE: data}))  # last
        return 0
