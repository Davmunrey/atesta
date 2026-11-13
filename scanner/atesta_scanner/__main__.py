"""`atesta-scan scan`: one scan attempt inside the scanner container.

Paths come from the runner's mounts (job.json read-only, the attempt's out/ folder, a /work
tmpfs); the credential arrives on stdin. Its own log lines carry ids, phases and exit codes
only, as JSON.
"""

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from atesta_scanner.exits import ExitCode
from atesta_scanner.job import JobError, load_job
from atesta_scanner.run import DirectorySink, read_credential, run_scan


def _log(event: dict[str, object]) -> None:
    print(json.dumps(event), flush=True)


def main(argv: Sequence[str] | None = None, executable: str = "prowler") -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["scan"]:  # verify mode arrives with the verifiers (PRs 9 and 11)
        _log({"event": "scan.wrapper_usage"})
        sys.exit(2)
    try:
        job = load_job(Path(os.environ.get("ATESTA_SCAN_JOB", "/job/job.json")).read_bytes())
    except (OSError, JobError):
        _log({"event": "scan.wrapper_job_invalid"})
        sys.exit(2)
    try:
        credential = read_credential(sys.stdin.buffer.read())
    except ValueError:
        code = ExitCode.CREDENTIAL_UNAVAILABLE
    else:
        sink = DirectorySink(Path(os.environ.get("ATESTA_SCAN_OUTPUT", "/output")))
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
