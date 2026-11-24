"""The wrapper in a Fargate task (scanner-connectors spec, AWS runner; issue 444).

No mounts and no stdin there: the job comes from S3 under the attempt's prefix, the credential
from Secrets Manager by the job's refs, and the outputs go back to S3 write-once. botocore's
Stubber plays S3 and Secrets Manager; nothing reaches the network.
"""

import io
import json
from typing import Any

import boto3  # type: ignore[import-untyped]  # boto3 ships no type stubs
import pytest
from atesta_scanner import __main__ as cli
from atesta_scanner import run as run_module
from atesta_scanner.aws import (
    CredentialUnavailableError,
    S3Sink,
    attempt_prefix,
    read_credentials,
)
from atesta_scanner.exits import ExitCode
from atesta_scanner.job import JobError, load_job
from atesta_scanner.run import OutputExistsError
from botocore.response import StreamingBody  # type: ignore[import-untyped]
from botocore.stub import Stubber  # type: ignore[import-untyped]

BUCKET = "atesta-dev-evidence"
ORG = "aaaaaaaa-0000-4000-8000-000000000001"
SCAN = "dddddddd-0000-4000-8000-000000000001"
PREFIX = f"{ORG}/scans/{SCAN}/attempt-1/"
ARN = "arn:aws:secretsmanager:eu-south-2:123456789012:secret:atesta/dev/m365-scanner-AbC123"
GOOGLE_ARN = f"arn:aws:secretsmanager:eu-south-2:123456789012:secret:atesta/dev/google/{ORG}-AbC123"
VERIFIER_ARN = (
    f"arn:aws:secretsmanager:eu-south-2:123456789012:secret:atesta/dev/google-verifier/{ORG}-x9Y8z7"
)
JOB = {
    "organization_id": ORG,
    "scan_id": SCAN,
    "attempt": 1,
    "provider": "m365",
    "tenant": "11111111-1111-4111-8111-111111111111",
    "excluded": [],
    "allowlist_version": "m365-v1",
    "credential_ref": f"aws-sm:{ARN}",
}
IDS = {"ATESTA_ORGANIZATION_ID": ORG, "ATESTA_SCAN_ID": SCAN, "ATESTA_SCAN_ATTEMPT": "1"}


def client(service: str) -> Any:
    return boto3.client(
        service,
        region_name="eu-south-2",
        aws_access_key_id="test",
        aws_secret_access_key="test",  # noqa: S106 - stubbed client, never sent
    )


def test_the_attempt_prefix_comes_from_the_three_ids_only() -> None:
    assert attempt_prefix(IDS) == PREFIX
    for bad in (
        {**IDS, "ATESTA_ORGANIZATION_ID": "../x"},
        {**IDS, "ATESTA_SCAN_ATTEMPT": "0"},
        {**IDS, "ATESTA_SCAN_ATTEMPT": "one"},
        {k: v for k, v in IDS.items() if k != "ATESTA_SCAN_ID"},
    ):
        with pytest.raises(JobError):
            attempt_prefix(bad)


def test_outputs_are_written_once_under_out() -> None:
    s3 = client("s3")
    with Stubber(s3) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": BUCKET,
                "Key": PREFIX + "out/verification.json",
                "Body": b"{}",
                "IfNoneMatch": "*",
            },
        )
        stub.add_client_error(
            "put_object", service_error_code="PreconditionFailed", http_status_code=412
        )
        sink = S3Sink(s3, BUCKET, PREFIX)
        sink.write("verification.json", b"{}")
        with pytest.raises(OutputExistsError):
            sink.write("verification.json", b"{}")
    with pytest.raises(ValueError, match="name"):
        sink.write("../job.json", b"{}")


def secret(stub: Any, arn: str, value: dict[str, str]) -> None:
    stub.add_response(
        "get_secret_value",
        {"ARN": arn, "Name": "x", "SecretString": json.dumps(value)},
        {"SecretId": arn},
    )


def test_credentials_come_from_the_jobs_refs_and_google_keys_merge() -> None:
    sm = client("secretsmanager")
    with Stubber(sm) as stub:
        secret(stub, GOOGLE_ARN, {"GOOGLEWORKSPACE_CREDENTIALS_CONTENT": "scan-key"})
        secret(stub, VERIFIER_ARN, {"ATESTA_GOOGLE_VERIFIER_CREDENTIALS_CONTENT": "verifier-key"})
        merged = read_credentials(sm, [f"aws-sm:{GOOGLE_ARN}", f"aws-sm:{VERIFIER_ARN}"])
    assert merged == {
        "GOOGLEWORKSPACE_CREDENTIALS_CONTENT": "scan-key",
        "ATESTA_GOOGLE_VERIFIER_CREDENTIALS_CONTENT": "verifier-key",
    }


@pytest.mark.parametrize("problem", ["denied", "local ref", "not json", "overlap", "no ref"])
def test_a_credential_the_task_cannot_read_is_unavailable_and_never_echoed(problem: str) -> None:
    sm = client("secretsmanager")
    refs = [f"aws-sm:{GOOGLE_ARN}", f"aws-sm:{VERIFIER_ARN}"]
    with Stubber(sm) as stub:
        if problem == "denied":
            stub.add_client_error("get_secret_value", service_error_code="AccessDeniedException")
        elif problem == "local ref":
            refs = [f"local:google-{ORG}"]
        elif problem == "not json":
            stub.add_response(
                "get_secret_value", {"SecretString": "s3cr3t-not-json"}, {"SecretId": GOOGLE_ARN}
            )
        elif problem == "overlap":
            secret(stub, GOOGLE_ARN, {"GOOGLEWORKSPACE_CREDENTIALS_CONTENT": "scan-key"})
            secret(stub, VERIFIER_ARN, {"GOOGLEWORKSPACE_CREDENTIALS_CONTENT": "other-key"})
        else:
            refs = [None]  # type: ignore[list-item]
        with pytest.raises(CredentialUnavailableError) as error:
            read_credentials(sm, refs)
    assert not any(value in str(error.value) for value in ("s3cr3t", "scan-key", "other-key"))


def test_the_job_names_its_credential_refs_as_refs_only() -> None:
    job = load_job(json.dumps(JOB).encode())
    assert job.credential_ref == f"aws-sm:{ARN}" and job.verifier_credential_ref is None
    for bad in (
        "-----BEGIN PRIVATE KEY-----",
        "aws-sm:arn:aws:secretsmanager:us-east-1:1:secret:x",
        "",
    ):
        with pytest.raises(JobError):
            load_job(json.dumps({**JOB, "credential_ref": bad}).encode())
    with pytest.raises(JobError):  # only Google has a verifier key
        load_job(json.dumps({**JOB, "verifier_credential_ref": f"aws-sm:{ARN}"}).encode())


def test_a_fargate_run_reads_its_job_and_secret_and_writes_back_to_s3(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    s3, sm = client("s3"), client("secretsmanager")
    monkeypatch.setattr(cli, "_aws_clients", lambda: (s3, sm))
    monkeypatch.setattr(
        run_module,
        "verify_job",
        lambda job, credential, full: {"verdict": "ok", "tenant_id": job.tenant},
    )
    for name, value in {**IDS, "ATESTA_SCAN_SOURCE": "s3", "ATESTA_SCAN_BUCKET": BUCKET}.items():
        monkeypatch.setenv(name, value)
    body = json.dumps(JOB).encode()
    with Stubber(s3) as s3_stub, Stubber(sm) as sm_stub:
        s3_stub.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(body), len(body))},
            {"Bucket": BUCKET, "Key": PREFIX + "job.json"},
        )
        secret(sm_stub, ARN, {"AZURE_CLIENT_ID": "id", "M365_CERTIFICATE_CONTENT": "Y2VydA=="})
        s3_stub.add_response(
            "put_object",
            {},
            {
                "Bucket": BUCKET,
                "Key": PREFIX + "out/verification.json",
                "Body": b'{"tenant_id": "11111111-1111-4111-8111-111111111111", "verdict": "ok"}',
                "IfNoneMatch": "*",
            },
        )
        with pytest.raises(SystemExit) as exit_:
            cli.main(["verify"])
        s3_stub.assert_no_pending_responses()
    assert exit_.value.code == ExitCode.DONE
    assert "Y2VydA==" not in capfd.readouterr().out


def test_a_job_for_another_attempt_than_the_tasks_ids_is_refused(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    s3, sm = client("s3"), client("secretsmanager")
    monkeypatch.setattr(cli, "_aws_clients", lambda: (s3, sm))
    for name, value in {**IDS, "ATESTA_SCAN_SOURCE": "s3", "ATESTA_SCAN_BUCKET": BUCKET}.items():
        monkeypatch.setenv(name, value)
    body = json.dumps({**JOB, "attempt": 2}).encode()
    with Stubber(s3) as stub:
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(body), len(body))},
            {"Bucket": BUCKET, "Key": PREFIX + "job.json"},
        )
        with pytest.raises(SystemExit) as exit_:
            cli.main(["scan"])
    assert exit_.value.code == 2
    assert json.loads(capfd.readouterr().out.splitlines()[-1]) == {
        "event": "scan.wrapper_job_invalid"
    }
