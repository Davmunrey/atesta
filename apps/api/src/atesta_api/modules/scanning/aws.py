"""The AWS scan runner and store (scanner-connectors spec, AWS runner; issue 444).

Outputs stay under <org_id>/scans/<scan_id>/attempt-<n>/ in the evidence bucket, write-once by
S3's conditional write. Each container run is one RunTask of the scan task definition with the
per-org, per-provider role the owner's OpenTofu module created (owner, 2026-11-24), and the ids
as its only environment overrides: the wrapper reads its job and credentials with that role.
Errors carry error codes, never a key, a body or a secret.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import (  # type: ignore[import-untyped]  # botocore ships no stubs
    BotoCoreError,
    ClientError,
)

from atesta_api.modules.scanning.runners import OutputExistsError, ScanJob

CONTAINER = "scan"  # the scan task definition's one container (infra/modules/ecs)
POLL_SECONDS = 15
STARTED_BY = "atesta-scan"
ENGINE_FAILED = 20  # the wrapper never ran: transient (scanner exits.py)
TIMEOUT = 21  # added by the runner
# Which role runs which mode: the provider's scan role, and Google's verify role (D7).
KINDS = {
    ("m365", "scan"): "scan-m365",
    ("google_workspace", "verify"): "verify-gws",
    ("google_workspace", "scan"): "scan-gws",
}
MODES = {"m365": ("scan",), "google_workspace": ("verify", "scan")}


class ScanStoreUnavailableError(OSError):
    """S3 did not accept the write or could not answer the read (an OSError, as a missing file)."""


def _code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


class S3ScanStore:
    """The scan outputs in the evidence bucket; the bucket's KMS key encrypts them."""

    def __init__(self, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    def write(self, key: str, data: bytes) -> None:
        try:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data, IfNoneMatch="*")
        except ClientError as error:
            if _code(error) in ("PreconditionFailed", "412"):
                raise OutputExistsError("the scan output exists") from None
            raise ScanStoreUnavailableError(_code(error) or "s3 refused the write") from None
        except BotoCoreError as error:
            raise ScanStoreUnavailableError(type(error).__name__) from None

    def read(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            data: bytes = response["Body"].read()
        except ClientError as error:
            if _code(error) in ("NoSuchKey", "404"):
                raise FileNotFoundError("no scan output under that key") from None
            raise ScanStoreUnavailableError(_code(error) or "s3 refused the read") from None
        except BotoCoreError as error:
            raise ScanStoreUnavailableError(type(error).__name__) from None
        return data

    def list(self, prefix: str) -> list[str]:
        keys: list[str] = []
        request: dict[str, str] = {"Bucket": self._bucket, "Prefix": prefix}
        try:
            while True:
                page = self._client.list_objects_v2(**request)
                keys.extend(item["Key"] for item in page.get("Contents", []))
                if not page.get("IsTruncated"):
                    return sorted(keys)
                request["ContinuationToken"] = page["NextContinuationToken"]
        except ClientError as error:
            raise ScanStoreUnavailableError(_code(error) or "s3 refused the list") from None
        except BotoCoreError as error:
            raise ScanStoreUnavailableError(type(error).__name__) from None


@dataclass(frozen=True, slots=True)
class FargateSettings:
    cluster: str
    task_definition: str
    subnets: tuple[str, ...]
    security_group: str
    role_prefix: str  # arn:aws:iam::<account>:role/atesta-scan/<env>/
    timeout_seconds: int  # per container run


class FargateRunner:
    """One RunTask per container run: Google verifies, then scans; M365 scans (D7)."""

    def __init__(
        self,
        ecs: Any,
        settings: FargateSettings,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ecs, self._settings = ecs, settings
        self._sleep, self._clock = sleep, clock

    @property
    def settings(self) -> FargateSettings:
        return self._settings

    def run(self, job: ScanJob) -> int:
        modes = MODES.get(job.provider)
        if modes is None:
            raise ValueError("unknown provider")
        for mode in modes:
            code = self._run(job, mode)
            if code != 0:
                return code  # a refused or failed verify never starts the scan
        return 0

    def _run(self, job: ScanJob, mode: str) -> int:
        s = self._settings
        role = f"{s.role_prefix}{KINDS[(job.provider, mode)]}-{job.organization_id}"
        ids = {
            "ATESTA_ORGANIZATION_ID": str(job.organization_id),
            "ATESTA_SCAN_ID": str(job.scan_id),
            "ATESTA_SCAN_ATTEMPT": str(job.attempt),
        }
        response = self._ecs.run_task(
            cluster=s.cluster,
            taskDefinition=s.task_definition,
            launchType="FARGATE",
            count=1,
            clientToken=f"{job.scan_id}-{job.attempt}-{mode}",  # a redelivered job reuses it
            startedBy=STARTED_BY,
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": list(s.subnets),
                    "securityGroups": [s.security_group],
                    "assignPublicIp": "DISABLED",
                }
            },
            overrides={
                "taskRoleArn": role,
                "containerOverrides": [
                    {
                        "name": CONTAINER,
                        "command": [mode],
                        "environment": [{"name": k, "value": v} for k, v in ids.items()],
                    }
                ],
            },
        )
        tasks = response.get("tasks") or []
        if not tasks:
            return ENGINE_FAILED  # ECS could not place it (capacity, a bad setting)
        return self._wait(tasks[0]["taskArn"])

    def _wait(self, task: str) -> int:
        s = self._settings
        deadline = self._clock() + s.timeout_seconds
        while True:
            described = self._ecs.describe_tasks(cluster=s.cluster, tasks=[task]).get("tasks", [])
            if described and described[0].get("lastStatus") == "STOPPED":
                for container in described[0].get("containers", []):
                    code = container.get("exitCode")
                    if container.get("name") == CONTAINER and isinstance(code, int):
                        return code
                return ENGINE_FAILED  # stopped before the wrapper ran (TaskFailedToStart)
            self._sleep(POLL_SECONDS)
            if self._clock() >= deadline:
                self._ecs.stop_task(
                    cluster=s.cluster, task=task, reason="atesta: the attempt timed out"
                )
                return TIMEOUT
