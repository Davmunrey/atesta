"""Local scanner container and credentials (scanner-connectors spec, Runners, Local development).

Dev-only: both refuse to start unless ATESTA_ENV names a development environment. The
credential is read from a 0600 file outside any repository and reaches the container on stdin
only, never as an argument, a variable or a mount. The container sees its own attempt's
job.json (read-only) and out/ folder, nothing else. Its stdout is logged only as the wrapper's
own JSON events; stderr is discarded.
"""

import json
import logging
import re
import stat
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from atesta_api.modules.scanning.runners import JOB_FILE, ScanJob, output_prefix
from atesta_api.platform.devenv import require_dev

CREDENTIAL_UNAVAILABLE = 11  # scanner/atesta_scanner/exits.py
TIMEOUT = 21  # added by the runner (spec, wrapper exit codes)
_LOCAL_REF = re.compile(r"local:([a-z0-9][a-z0-9-]{0,62})")
_HARDENING = (
    *("--user", "10001", "--read-only", "--tmpfs", "/work", "--tmpfs", "/home/scanner"),
    *("--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--cpus", "2", "--memory", "4g"),
)
scanner_log = logging.getLogger("atesta.scanner")
_EVENT = re.compile(r"scan\.[a-z_]{1,64}")


def _is_uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# The wrapper's own event keys (scanner/atesta_scanner/__main__.py); nothing else is forwarded.
_FIELDS: dict[str, Callable[[object], bool]] = {
    "scan_id": _is_uuid,
    "organization_id": _is_uuid,
    "attempt": _is_int,
    "exit_code": _is_int,
}


class LocalCredentialStore:
    """Credential files named after their local: reference, e.g. local:m365-scanner."""

    def __init__(self, root: Path) -> None:
        require_dev("LocalCredentialStore")
        resolved = root.resolve()
        if any((parent / ".git").exists() for parent in (resolved, *resolved.parents)):
            raise ValueError("local credentials must live outside the repository")
        self.root = resolved

    def read(self, ref: str) -> bytes:
        """The raw credential. Refuses a file any other user could read (mode 0600)."""
        match = _LOCAL_REF.fullmatch(ref)
        if match is None:
            raise ValueError("not a local credential reference")
        path = self.root / f"{match.group(1)}.json"
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError("local credential files must be mode 0600")
        return path.read_bytes()


class LocalDockerRunner:
    """One `docker run` per attempt, as the spec's Runners table fixes it."""

    def __init__(
        self,
        *,
        store_root: Path,
        credentials: LocalCredentialStore,
        image: str,
        m365_credential_ref: str,
        timeout_seconds: int,
        network: str = "atesta-scan",
        docker: str = "docker",
    ) -> None:
        require_dev("LocalDockerRunner")
        self._root, self._credentials = store_root.resolve(), credentials
        self._image, self._m365_ref = image, m365_credential_ref
        self._timeout, self._network, self._docker = timeout_seconds, network, docker

    def _credential(self, job: ScanJob) -> bytes | None:
        ref = self._m365_ref if job.provider == "m365" else job.credential_ref
        if ref is None:
            return None
        try:
            return self._credentials.read(ref)
        except (OSError, ValueError):  # never echo the file or its contents
            return None

    def run(self, job: ScanJob) -> int:
        credential = self._credential(job)
        if credential is None:
            return CREDENTIAL_UNAVAILABLE
        out = self._root / output_prefix(job.organization_id, job.scan_id, job.attempt)
        job_file = out.parent / JOB_FILE
        out.mkdir(parents=True, exist_ok=True)
        out.chmod(0o777)  # the container's user 10001 writes here; dev machines only
        name = f"atesta-scan-{job.scan_id}-{job.attempt}"
        argv = [
            *(self._docker, "run", "-i", "--rm", "--name", name, *_HARDENING),
            *("--network", self._network),
            *("-v", f"{job_file}:/job/job.json:ro", "-v", f"{out}:/output:rw"),
            *(self._image, "scan"),
        ]
        try:
            done = subprocess.run(  # noqa: S603 - fixed argv, no shell, ids from the database
                argv,
                input=credential,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            # The CLI died with the timeout; the container did not.
            subprocess.run(  # noqa: S603 - fixed argv, no shell
                [self._docker, "kill", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return TIMEOUT
        _forward(done.stdout)
        return done.returncode


def _forward(stdout: bytes) -> None:
    """Re-log the wrapper's own events, allowed keys of the right shape only (rule 2).

    Anything else on stdout, and any other key or value in an event, is dropped.
    """
    for line in stdout.decode(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        name = event.get("event")
        if not (isinstance(name, str) and _EVENT.fullmatch(name)):
            continue
        kept = {key: event[key] for key, valid in _FIELDS.items() if valid(event.get(key))}
        scanner_log.info(json.dumps({"event": name, **kept}, sort_keys=True))
