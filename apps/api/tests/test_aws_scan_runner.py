"""The AWS scan runner and store (scanner-connectors spec, AWS runner; issue 444).

botocore's Stubber answers for S3 and ECS, so the exact requests are checked with no account and
no network. Each container run is one RunTask with the per-org role and ids only; the runner waits
for STOPPED, stops a task at the timeout, and never starts a Google scan after a refused verify.
"""

import dataclasses
import io
import uuid
from typing import Any

import boto3  # type: ignore[import-untyped]  # boto3 ships no type stubs
import pytest
from atesta_api.modules.scanning.aws import (
    FargateRunner,
    FargateSettings,
    S3ScanStore,
    ScanStoreUnavailableError,
)
from atesta_api.modules.scanning.runners import OutputExistsError, ScanJob
from botocore.response import StreamingBody  # type: ignore[import-untyped]
from botocore.stub import Stubber  # type: ignore[import-untyped]

BUCKET = "atesta-dev-evidence"
ORG = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
SCAN = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
KEY = f"{ORG}/scans/{SCAN}/attempt-1/job.json"
CLUSTER = "atesta-dev"
TASK = f"arn:aws:ecs:eu-south-2:123456789012:task/{CLUSTER}/0123456789abcdef"
SETTINGS = FargateSettings(
    cluster=CLUSTER,
    task_definition="atesta-dev-scan",
    subnets=("subnet-aaa", "subnet-bbb"),
    security_group="sg-scan",
    role_prefix="arn:aws:iam::123456789012:role/atesta-scan/dev/",
    timeout_seconds=3600,
)


def client(service: str) -> Any:
    return boto3.client(
        service,
        region_name="eu-south-2",
        aws_access_key_id="test",
        aws_secret_access_key="test",  # noqa: S106 - stubbed client, never sent
    )


# --- S3ScanStore ---------------------------------------------------------------------------


def test_writes_are_write_once_with_if_none_match() -> None:
    s3 = client("s3")
    with Stubber(s3) as stub:
        stub.add_response(
            "put_object", {}, {"Bucket": BUCKET, "Key": KEY, "Body": b"{}", "IfNoneMatch": "*"}
        )
        stub.add_client_error(
            "put_object", service_error_code="PreconditionFailed", http_status_code=412
        )
        store = S3ScanStore(BUCKET, s3)
        store.write(KEY, b"{}")
        with pytest.raises(OutputExistsError):
            store.write(KEY, b"{}")
        stub.assert_no_pending_responses()


def test_reads_a_missing_key_as_not_found_and_other_failures_as_unavailable() -> None:
    s3 = client("s3")
    with Stubber(s3) as stub:
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(b"{}"), 2)},
            {"Bucket": BUCKET, "Key": KEY},
        )
        stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
        stub.add_client_error(
            "get_object", service_error_code="InternalError", http_status_code=500
        )
        store = S3ScanStore(BUCKET, s3)
        assert store.read(KEY) == b"{}"
        with pytest.raises(FileNotFoundError):
            store.read(KEY)
        with pytest.raises(ScanStoreUnavailableError) as error:
            store.read(KEY)
        assert KEY not in str(error.value)  # an error never echoes a key
        assert isinstance(error.value, OSError)  # callers treat it as an unreadable output
        stub.assert_no_pending_responses()


def _denied_then_listed(stub: Any, keys: list[str]) -> None:
    stub.add_client_error("get_object", service_error_code="AccessDenied", http_status_code=403)
    stub.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": k} for k in keys], "IsTruncated": False},
        {"Bucket": BUCKET, "Prefix": KEY, "MaxKeys": 1},
    )


def test_a_403_is_not_found_when_the_scan_prefix_lists_no_such_key() -> None:
    """Issue 453: without s3:ListBucket on the whole bucket, S3 answers 403 for a missing key.

    The worker may list only scan prefixes (evidence keys carry document names), so a 403 is
    settled by listing that key: absent is not found, present is a real refusal.
    """
    s3 = client("s3")
    with Stubber(s3) as stub:
        _denied_then_listed(stub, [])
        _denied_then_listed(stub, [KEY + ".other"])  # a longer key under the same prefix
        _denied_then_listed(stub, [KEY])
        store = S3ScanStore(BUCKET, s3)
        for _ in range(2):
            with pytest.raises(FileNotFoundError):
                store.read(KEY)
        with pytest.raises(ScanStoreUnavailableError):
            store.read(KEY)
        stub.add_client_error("get_object", service_error_code="AccessDenied", http_status_code=403)
        stub.add_client_error(
            "list_objects_v2", service_error_code="AccessDenied", http_status_code=403
        )
        with pytest.raises(ScanStoreUnavailableError):
            store.read(KEY)
        stub.assert_no_pending_responses()


def test_lists_every_page_under_a_prefix() -> None:
    s3 = client("s3")
    prefix = f"{ORG}/scans/{SCAN}/attempt-1/out/"
    with Stubber(s3) as stub:
        stub.add_response(
            "list_objects_v2",
            {
                "Contents": [{"Key": prefix + "a"}],
                "IsTruncated": True,
                "NextContinuationToken": "t",
            },
            {"Bucket": BUCKET, "Prefix": prefix},
        )
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": prefix + "b"}], "IsTruncated": False},
            {"Bucket": BUCKET, "Prefix": prefix, "ContinuationToken": "t"},
        )
        assert S3ScanStore(BUCKET, s3).list(prefix) == [prefix + "a", prefix + "b"]


# --- FargateRunner -------------------------------------------------------------------------


def run_task_params(kind: str, mode: str) -> dict[str, Any]:
    return {
        "cluster": CLUSTER,
        "taskDefinition": "atesta-dev-scan",
        "launchType": "FARGATE",
        "count": 1,
        "clientToken": f"{SCAN}-1-{mode}",
        "startedBy": "atesta-scan",
        "networkConfiguration": {
            "awsvpcConfiguration": {
                "subnets": ["subnet-aaa", "subnet-bbb"],
                "securityGroups": ["sg-scan"],
                "assignPublicIp": "DISABLED",
            }
        },
        "overrides": {
            "taskRoleArn": f"arn:aws:iam::123456789012:role/atesta-scan/dev/{kind}-{ORG}",
            "containerOverrides": [
                {
                    "name": "scan",
                    "command": [mode],
                    "environment": [
                        {"name": "ATESTA_ORGANIZATION_ID", "value": str(ORG)},
                        {"name": "ATESTA_SCAN_ID", "value": str(SCAN)},
                        {"name": "ATESTA_SCAN_ATTEMPT", "value": "1"},
                    ],
                }
            ],
        },
    }


def started(stub: Any, kind: str, mode: str) -> None:
    stub.add_response(
        "run_task", {"tasks": [{"taskArn": TASK}], "failures": []}, run_task_params(kind, mode)
    )


def status(stub: Any, last: str, exit_code: int | None = None) -> None:
    container: dict[str, Any] = {"name": "scan", "lastStatus": last}
    if exit_code is not None:
        container["exitCode"] = exit_code
    stub.add_response(
        "describe_tasks",
        {
            "tasks": [{"taskArn": TASK, "lastStatus": last, "containers": [container]}],
            "failures": [],
        },
        {"cluster": CLUSTER, "tasks": [TASK]},
    )


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def runner(ecs: Any, clock: Clock, timeout: int = 3600) -> FargateRunner:
    settings = dataclasses.replace(SETTINGS, timeout_seconds=timeout)
    return FargateRunner(ecs, settings, sleep=clock.sleep, clock=clock)


M365 = ScanJob(ORG, SCAN, 1, "m365")
GOOGLE = ScanJob(ORG, SCAN, 1, "google_workspace", "aws-sm:x", "aws-sm:y")


def test_an_m365_attempt_is_one_task_with_its_org_role_and_ids_only() -> None:
    ecs, clock = client("ecs"), Clock()
    with Stubber(ecs) as stub:
        started(stub, "scan-m365", "scan")
        status(stub, "RUNNING")
        status(stub, "STOPPED", 0)
        assert runner(ecs, clock).run(M365) == 0
        stub.assert_no_pending_responses()
    assert clock.slept == [15]


def test_a_google_attempt_verifies_with_its_role_then_scans_with_another() -> None:
    ecs, clock = client("ecs"), Clock()
    with Stubber(ecs) as stub:
        started(stub, "verify-gws", "verify")
        status(stub, "STOPPED", 0)
        started(stub, "scan-gws", "scan")
        status(stub, "STOPPED", 0)
        assert runner(ecs, clock).run(GOOGLE) == 0
        stub.assert_no_pending_responses()


def test_a_refused_google_verification_never_starts_the_scan() -> None:
    ecs, clock = client("ecs"), Clock()
    with Stubber(ecs) as stub:
        started(stub, "verify-gws", "verify")
        status(stub, "STOPPED", 10)
        assert runner(ecs, clock).run(GOOGLE) == 10
        stub.assert_no_pending_responses()  # no second RunTask


def test_the_timeout_stops_the_task_and_counts_as_exit_21() -> None:
    ecs, clock = client("ecs"), Clock()
    with Stubber(ecs) as stub:
        started(stub, "scan-m365", "scan")
        status(stub, "RUNNING")
        status(stub, "RUNNING")
        stub.add_response(
            "stop_task",
            {},
            {"cluster": CLUSTER, "task": TASK, "reason": "atesta: the attempt timed out"},
        )
        assert runner(ecs, clock, timeout=20).run(M365) == 21
        stub.assert_no_pending_responses()


@pytest.mark.parametrize(
    "answer",
    [
        {"tasks": [], "failures": [{"arn": "x", "reason": "RESOURCE:MEMORY"}]},
        "stopped without an exit code",
    ],
)
def test_a_task_that_never_ran_the_wrapper_is_exit_20(answer: object) -> None:
    ecs, clock = client("ecs"), Clock()
    with Stubber(ecs) as stub:
        if isinstance(answer, dict):
            stub.add_response("run_task", answer, run_task_params("scan-m365", "scan"))
        else:
            started(stub, "scan-m365", "scan")
            status(stub, "STOPPED")  # TaskFailedToStart: the container has no exit code
        assert runner(ecs, clock).run(M365) == 20


def test_client_tokens_fit_ecs_limit() -> None:
    token = f"{SCAN}-99-verify"
    assert len(token) <= 64 and all(33 <= ord(c) <= 126 for c in token)


def test_an_unknown_provider_is_refused() -> None:
    ecs, clock = client("ecs"), Clock()
    with pytest.raises(ValueError, match="provider"):
        runner(ecs, clock).run(ScanJob(ORG, SCAN, 1, "aws"))
