"""The worker records GuardDuty results and tells owners and admins about malware
(evidence-malware-scanning spec, #430). Real PostgreSQL with RLS; the queue is a fake."""

import json
import uuid
from collections.abc import Iterator

import pytest
from atesta_api.modules.notifications.api import MemoryMailer
from atesta_worker import context, file_scans, jobs
from atesta_worker.file_scans import FileScanConfig, Message
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth
from .test_control_workspace import workspace as workspace
from .test_evidence_files import upload
from .test_evidence_malware import ScanningStore, key_of, stored_scans
from .test_evidence_malware import scanning as scanning
from .test_members import events, org_with
from .test_notify_events import mailer as mailer

BUCKET = "atesta-test-evidence"


class FakeQueue:
    def __init__(self, bodies: list[str]) -> None:
        self.messages = [Message(f"r{i}", body) for i, body in enumerate(bodies)]
        self.deleted: list[str] = []

    def receive(self) -> list[Message]:
        batch, self.messages = self.messages, []
        return batch

    def delete(self, receipt: str) -> None:
        self.deleted.append(receipt)


def guardduty(key: str, status: str, *, bucket: str = BUCKET) -> str:
    """A scan result as GuardDuty publishes it (AWS sample, trimmed)."""
    return json.dumps(
        {
            "detail-type": "GuardDuty Malware Protection Object Scan Result",
            "source": "aws.guardduty",
            "detail": {
                "scanStatus": "COMPLETED",
                "resourceType": "S3_OBJECT",
                "s3ObjectDetails": {"bucketName": bucket, "objectKey": key, "versionId": "v1"},
                "scanResultDetails": {"scanResultStatus": status, "threats": None},
            },
        }
    )


@pytest.fixture
def poll(app_engine: Engine) -> Iterator[None]:
    context.configure(app_engine)
    yield
    file_scans.configure(None)


def run(bodies: list[str]) -> FakeQueue:
    queue = FakeQueue(bodies)
    file_scans.configure(FileScanConfig(queue=queue, bucket=BUCKET))
    jobs.poll_file_scans(0)
    return queue


def notify_jobs(superuser: Engine, org: str) -> list[dict[str, str]]:
    with superuser.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT args FROM procrastinate_jobs WHERE task_name = 'notify_event'"
                    " AND args->>'organization_id' = :o"
                ),
                {"o": org},
            ).scalars()
        )


def test_malware_is_recorded_blocked_and_announced_to_owners_and_admins(
    client: TestClient,
    superuser: Engine,
    workspace: str,
    scanning: ScanningStore,
    poll: None,
    mailer: MemoryMailer,
) -> None:
    org, subs = org_with(client, superuser, adm="admin", mem="member")
    item = upload(
        client, org, workspace, subs["mem"], name="factura-secreta.pdf", title="Título secreto"
    ).json()
    key = key_of(superuser, item["id"])
    queue = run([guardduty(key, "THREATS_FOUND"), guardduty(key, "THREATS_FOUND")])
    assert queue.deleted == ["r0", "r1"]  # the repeat is a no-op, and is deleted too
    assert stored_scans(superuser, item["id"]) == [("threats_found", "v1")]
    assert events(superuser, org, "evidence.file_malware_found") == 1
    [job] = notify_jobs(superuser, org)
    assert set(job) == {"organization_id", "event_id"}  # ids only (ADR-012 amendment 2)

    jobs.notify_event(job["organization_id"], job["event_id"])
    jobs.notify_event(job["organization_id"], job["event_id"])  # a retried job sends nothing
    emails = {
        name: client.get("/api/v1/me", headers=auth(subs[name])).json()["email"]
        for name in ("owner", "adm")
    }
    assert sorted(m.to for m in mailer.sent) == sorted(emails.values())
    message = mailer.sent[0]
    assert "List-Unsubscribe" not in message.headers  # critical: nobody can turn it off
    assert "malware" in message.subject
    assert f"https://app.example.com/app/activity?org={org}" in message.body
    for secret in ("factura", "secreta", "Título", key):
        assert secret not in message.body and secret not in message.subject
    got = client.get(f"/api/v1/orgs/{org}/evidence/{item['id']}/file", headers=auth(subs["mem"]))
    assert got.json()["detail"]["code"] == "evidence.file_malware_found"


def test_a_clean_result_is_recorded_and_notifies_nobody(
    client: TestClient,
    superuser: Engine,
    workspace: str,
    scanning: ScanningStore,
    poll: None,
    mailer: MemoryMailer,
) -> None:
    org, subs = org_with(client, superuser)
    item = upload(client, org, workspace, subs["owner"]).json()
    run([guardduty(key_of(superuser, item["id"]), "NO_THREATS_FOUND")])
    assert stored_scans(superuser, item["id"]) == [("no_threats_found", "v1")]
    assert notify_jobs(superuser, org) == []
    got = client.get(f"/api/v1/orgs/{org}/evidence/{item['id']}/file", headers=auth(subs["owner"]))
    assert got.status_code == 200
    assert scanning.reads[-1][1] == "v1"


def test_results_that_are_not_for_an_uploaded_file_are_dropped_and_early_ones_kept(
    client: TestClient,
    superuser: Engine,
    workspace: str,
    scanning: ScanningStore,
    poll: None,
) -> None:
    org, subs = org_with(client, superuser)
    item = upload(client, org, workspace, subs["owner"]).json()
    key = key_of(superuser, item["id"])
    not_committed_yet = f"{org}/evidence/{uuid.uuid4()}/policy.pdf"
    queue = run(
        [
            guardduty(f"{org}/scans/{uuid.uuid4()}/attempt-1/out/result.ocsf.json", "FAILED"),
            guardduty(key, "NO_THREATS_FOUND", bucket="another-bucket"),
            "not json",
            guardduty(not_committed_yet, "NO_THREATS_FOUND"),
            guardduty(key.replace(org, str(uuid.uuid4())), "NO_THREATS_FOUND"),
        ]
    )
    assert queue.deleted == ["r0", "r1", "r2"]
    assert stored_scans(superuser, item["id"]) == []  # still pending
    assert events(superuser, org, "evidence.file_scanned") == 0


def test_without_a_queue_the_job_does_nothing(poll: None) -> None:
    file_scans.configure(None)
    jobs.poll_file_scans(0)
