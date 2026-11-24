"""The wrapper's AWS source (scanner-connectors spec, AWS runner; issue 444).

In a Fargate task there is no mount and no stdin. The attempt's prefix comes from the three id
variables the runner sets, the job from S3 under it, each credential from Secrets Manager by the
job's ref, and the outputs go back under `out/` write-once (S3's conditional write). The task role
reaches only this organization's prefix and secrets. Errors name what failed, never a value
(rule 2).
"""

import re
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from botocore.exceptions import (  # type: ignore[import-untyped]  # botocore ships no stubs
    BotoCoreError,
    ClientError,
)

from atesta_scanner.job import JobError
from atesta_scanner.run import OutputExistsError, read_credential

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_ARN = "aws-sm:"


class CredentialUnavailableError(Exception):
    """A credential the task role cannot read, or that is not one: exit 11."""


def attempt_prefix(env: Mapping[str, str]) -> str:
    """`<org>/scans/<scan>/attempt-<n>/` from the runner's ids, each checked."""
    try:
        org = uuid.UUID(env["ATESTA_ORGANIZATION_ID"])
        scan = uuid.UUID(env["ATESTA_SCAN_ID"])
        attempt = int(env["ATESTA_SCAN_ATTEMPT"])
    except (KeyError, ValueError):
        raise JobError("the task's ids are missing or malformed") from None
    if (
        attempt < 1
        or str(org) != env["ATESTA_ORGANIZATION_ID"]
        or str(scan) != env["ATESTA_SCAN_ID"]
    ):
        raise JobError("the task's ids are malformed")
    return f"{org}/scans/{scan}/attempt-{attempt}/"


def read_job(s3: Any, bucket: str, prefix: str) -> bytes:
    try:
        body: bytes = s3.get_object(Bucket=bucket, Key=prefix + "job.json")["Body"].read()
    except (BotoCoreError, ClientError):
        raise JobError("job.json could not be read") from None
    return body


def read_credentials(secrets: Any, refs: Iterable[str | None]) -> dict[str, str]:
    """The run's credential: each ref's `{variable: value}` secret, merged (Google verify: two)."""
    merged: dict[str, str] = {}
    for ref in refs:
        if not isinstance(ref, str) or not ref.startswith(_ARN):
            raise CredentialUnavailableError("the job names no Secrets Manager reference")
        try:
            raw = secrets.get_secret_value(SecretId=ref.removeprefix(_ARN))["SecretString"]
            part = read_credential(raw.encode())
        except (BotoCoreError, ClientError, KeyError, ValueError):
            raise CredentialUnavailableError("a credential could not be read") from None
        if merged.keys() & part.keys():
            raise CredentialUnavailableError("two credentials hold the same variable")
        merged.update(part)
    return merged


class S3Sink:
    """The attempt's `out/` folder in S3, write-once like the local DirectorySink."""

    def __init__(self, s3: Any, bucket: str, prefix: str) -> None:
        self._s3, self._bucket, self._prefix = s3, bucket, prefix

    def write(self, name: str, data: bytes) -> None:
        if not _NAME.fullmatch(name):
            raise ValueError("unsafe output name")
        try:
            self._s3.put_object(
                Bucket=self._bucket, Key=f"{self._prefix}out/{name}", Body=data, IfNoneMatch="*"
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in ("PreconditionFailed", "412"):
                raise OutputExistsError(name) from None
            raise OSError("s3 refused the output") from None
        except BotoCoreError:
            raise OSError("s3 is unreachable") from None


def job_matches(job_ids: tuple[str, str, int], prefix: str) -> bool:
    """The job file belongs to the attempt the task was started for."""
    org, scan, attempt = job_ids
    return prefix == f"{org}/scans/{scan}/attempt-{attempt}/"
