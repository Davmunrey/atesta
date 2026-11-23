"""One wrapper run (scanner-connectors spec, Scanner image and wrapper; Logs and personal data).

Prowler runs as a child process with the minimal environment and its stdout and stderr
discarded. Its log is kept only scrubbed. The OCSF output must parse strictly and belong to the
job's tenant; it is stored stripped of resource dumps (D10). Outputs are write-once and the
manifest is written last, recording the raw OCSF hash: a run without a manifest is not ingested.
"""

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
from atesta_core.manifest import build_manifest
from atesta_core.ocsf import OcsfError, TenantMismatchError, parse_findings, pin_tenant

from atesta_scanner.entra_token import (
    TokenRevokedError,
    TokenTransientError,
    TokenUnavailableError,
    m365_graph_token,
)
from atesta_scanner.exits import ExitCode, after_prowler
from atesta_scanner.graph import Graph
from atesta_scanner.invocation import child_env, prowler_argv
from atesta_scanner.job import Job
from atesta_scanner.scrub import scrub
from atesta_scanner.strip import OutputInvalidError, strip_metadata
from atesta_scanner.verify_m365 import report, verify_m365

OCSF_FILE, LOG_FILE, MANIFEST_FILE = "prowler.ocsf.json", "prowler.log", "manifest.json"
VERIFICATION_FILE = "verification.json"  # read by the worker on exit 10 (record_verification)
type Verifier = Callable[[Job, Mapping[str, str]], dict[str, Any]]
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class OutputExistsError(FileExistsError):
    """Scan outputs are write-once."""


class DirectorySink:
    """The attempt's out/ folder (a local mount; S3 with if-none-match in AWS)."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._root = root

    def write(self, name: str, data: bytes) -> None:
        if not _NAME.fullmatch(name):
            raise ValueError("unsafe output name")
        try:
            with (self._root / name).open("xb") as handle:
                handle.write(data)
        except FileExistsError:
            raise OutputExistsError(name) from None


def read_credential(raw: bytes) -> dict[str, str]:
    """The credential arrives on stdin as {variable: value}. Errors never echo it."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise ValueError("credential on stdin is not JSON") from None
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise ValueError("credential on stdin must map variable names to strings")
    return data


def _prowler(argv: Sequence[str], env: Mapping[str, str]) -> int:
    devnull = subprocess.DEVNULL  # stdout and stderr never reach the container log
    process = subprocess.run(  # noqa: S603 - fixed argv, validated check ids, no shell
        list(argv), env=dict(env), stdin=devnull, stdout=devnull, stderr=devnull, check=False
    )
    return process.returncode


def verify_job(job: Job, credential: Mapping[str, str]) -> dict[str, Any]:
    """Read-only verification of an M365 job (spec steps 1 to 5). Google arrives in PR 11."""
    if job.provider != "m365":  # fail closed: no Google scan runs unverified
        return report("incomplete", missing=["google verifier (PR 11)"])
    client_id = credential["AZURE_CLIENT_ID"]
    try:
        token = m365_graph_token(client_id, job.tenant, credential["M365_CERTIFICATE_CONTENT"])
    except TokenRevokedError:
        return report("revoked")
    except TokenTransientError:
        return report("transient")
    with httpx.Client(timeout=30.0) as client:
        graph = Graph(token, client)
        return verify_m365(
            graph,
            app_id=client_id,
            tenant=job.tenant,
            version=job.allowlist_version,
            admin_oid=job.admin_oid,
        )


def run_verification(
    job: Job,
    credential: Mapping[str, str],
    sink: DirectorySink,
    verifier: Verifier | None = None,
) -> ExitCode:
    """Write the verification report; DONE only for `ok`. Fails closed (rule 1)."""
    try:
        result = (verifier or verify_job)(job, credential)
    except TokenUnavailableError:
        return ExitCode.CREDENTIAL_UNAVAILABLE
    sink.write(VERIFICATION_FILE, json.dumps(result, sort_keys=True).encode())
    if result["verdict"] == "ok":
        return ExitCode.DONE
    if result["verdict"] == "transient":
        return ExitCode.VERIFICATION_TRANSIENT
    return ExitCode.VERIFICATION_REFUSED


def run_scan(
    job: Job,
    credential: Mapping[str, str],
    sink: DirectorySink,
    work: Path,
    executable: str = "prowler",
    verifier: Verifier | None = None,
) -> ExitCode:
    """Step 0 verifies; Prowler runs only after an `ok`."""
    try:
        env = child_env(job.provider, credential, job.tenant)
    except ValueError:
        return ExitCode.CREDENTIAL_UNAVAILABLE
    verified = run_verification(job, credential, sink, verifier)
    if verified is not ExitCode.DONE:
        return verified
    (work / "out").mkdir(parents=True, exist_ok=True)
    (work / "tmp").mkdir(exist_ok=True)
    argv = prowler_argv(job.provider, job.excluded, work=str(work))
    code = after_prowler(_prowler([executable, *argv[1:]], env))
    log_path = work / LOG_FILE
    text = log_path.read_text(errors="replace") if log_path.exists() else ""
    log = scrub(text, credential.values()).encode()
    sink.write(LOG_FILE, log)
    if code is not ExitCode.DONE:
        return code
    try:
        raw = (work / "out" / OCSF_FILE).read_bytes()
        pin_tenant(parse_findings(raw), job.provider, job.tenant)
        stripped = strip_metadata(raw)
    except (OSError, OcsfError, TenantMismatchError, OutputInvalidError):
        return ExitCode.OUTPUT_INVALID
    sink.write(OCSF_FILE, stripped)
    raw_sha256 = {OCSF_FILE: hashlib.sha256(raw).hexdigest()}
    sink.write(MANIFEST_FILE, build_manifest({OCSF_FILE: stripped, LOG_FILE: log}, raw_sha256))
    return ExitCode.DONE
