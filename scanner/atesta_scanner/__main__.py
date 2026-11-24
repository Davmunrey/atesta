"""`atesta-scan scan`: one scan attempt inside the scanner container.

Locally, paths come from the runner's mounts (job.json read-only, the attempt's out/ folder, a
/work tmpfs) and the credential arrives on stdin. In a Fargate task (ATESTA_SCAN_SOURCE=s3,
issue 444) the job and outputs are in S3 and the credential in Secrets Manager. Its own log
lines carry ids, phases and exit codes only, as JSON.
"""

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from atesta_scanner.aws import (
    CredentialUnavailableError,
    S3Sink,
    attempt_prefix,
    job_matches,
    read_credentials,
    read_job,
)
from atesta_scanner.exits import ExitCode
from atesta_scanner.job import Job, JobError, load_job
from atesta_scanner.run import (
    DirectorySink,
    Sink,
    read_credential,
    run_scan,
    run_verification,
)


def _log(event: dict[str, object]) -> None:
    print(json.dumps(event), flush=True)


def _aws_clients() -> tuple[Any, Any]:
    """S3 and Secrets Manager with the task role, in the task's region (eu-south-2)."""
    import boto3  # type: ignore[import-untyped]  # noqa: PLC0415 - only a Fargate run needs it

    return boto3.client("s3"), boto3.client("secretsmanager")


def _local(args: list[str]) -> tuple[Job, Sink, dict[str, str] | None]:
    """Mounts and stdin (the local runner): job.json read-only, out/ and the credential."""
    job = load_job(Path(os.environ.get("ATESTA_SCAN_JOB", "/job/job.json")).read_bytes())
    sink = DirectorySink(Path(os.environ.get("ATESTA_SCAN_OUTPUT", "/output")))
    try:
        return job, sink, read_credential(sys.stdin.buffer.read())
    except ValueError:
        return job, sink, None


def _s3(args: list[str]) -> tuple[Job, Sink, dict[str, str] | None]:
    """A Fargate task (issue 444): the job and outputs in S3, the credential in Secrets Manager."""
    prefix = attempt_prefix(os.environ)
    bucket = os.environ["ATESTA_SCAN_BUCKET"]
    s3, secrets = _aws_clients()
    job = load_job(read_job(s3, bucket, prefix))
    if not job_matches((job.organization_id, job.scan_id, job.attempt), prefix):
        raise JobError("job.json belongs to another attempt")
    refs = [job.credential_ref]
    if args == ["verify"] and job.provider == "google_workspace":
        refs.append(job.verifier_credential_ref)  # D7: only the verify run holds it
    try:
        credential: dict[str, str] | None = read_credentials(secrets, refs)
    except CredentialUnavailableError:
        credential = None
    return job, S3Sink(s3, bucket, prefix), credential


def main(argv: Sequence[str] | None = None, executable: str = "prowler") -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in (["scan"], ["verify"]):  # verify: onboarding, no Prowler
        _log({"event": "scan.wrapper_usage"})
        sys.exit(2)
    source = _s3 if os.environ.get("ATESTA_SCAN_SOURCE") == "s3" else _local
    try:
        job, sink, credential = source(args)
    except (OSError, JobError, KeyError):
        _log({"event": "scan.wrapper_job_invalid"})
        sys.exit(2)
    if credential is None:
        code = ExitCode.CREDENTIAL_UNAVAILABLE
    elif args == ["verify"]:
        code = run_verification(job, credential, sink)
    else:
        work = Path(os.environ.get("ATESTA_SCAN_WORK", "/work"))
        code = run_scan(job, credential, sink, work, executable)
    _log(
        {
            "event": "scan.wrapper_finished",
            "scan_id": job.scan_id,
            "organization_id": job.organization_id,
            "attempt": job.attempt,
            "exit_code": int(code),
        }
    )
    sys.exit(int(code))


if __name__ == "__main__":
    main()
