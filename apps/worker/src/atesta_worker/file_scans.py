"""GuardDuty malware scan results, from SQS to the evidence record (evidence-malware-scanning spec).

EventBridge puts each "GuardDuty Malware Protection Object Scan Result" of the evidence bucket's
plan on an SQS queue; the periodic job poll_file_scans drains it. A message is deleted once its
result is recorded, or when it is not a result for an uploaded file. One whose evidence row is
not visible yet stays: SQS shows it again after the visibility timeout, and moves it to the
dead-letter queue after 10 receives. Logs hold counts only, never a key (keys carry a file
name, rule 2). Without ATESTA_FILE_SCAN_QUEUE_URL nothing is configured and the job does nothing.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import boto3  # type: ignore[import-untyped]  # boto3 ships no type stubs
from atesta_api.modules.evidence.api import has_file_scan, parse_scan_result, record_file_scan
from atesta_api.modules.notifications.api import queue_event

from atesta_worker.context import org_session

MAX_BATCHES = 20  # 200 messages a run; the next run, a minute later, takes the rest


@dataclass(frozen=True, slots=True)
class Message:
    receipt: str
    body: str


class Queue(Protocol):
    def receive(self) -> list[Message]: ...

    def delete(self, receipt: str) -> None: ...


class SqsQueue:
    """Long polls (a wait above 0 s asks every SQS server, so a non-empty queue is not missed)."""

    def __init__(self, url: str, client: Any) -> None:
        self._url = url
        self._client = client

    def receive(self) -> list[Message]:
        answer = self._client.receive_message(
            QueueUrl=self._url, MaxNumberOfMessages=10, WaitTimeSeconds=1
        )
        return [Message(m["ReceiptHandle"], m.get("Body", "")) for m in answer.get("Messages", [])]

    def delete(self, receipt: str) -> None:
        self._client.delete_message(QueueUrl=self._url, ReceiptHandle=receipt)


@dataclass(frozen=True, slots=True)
class FileScanConfig:
    queue: Queue
    bucket: str  # the evidence bucket: results for any other bucket are dropped


_config: FileScanConfig | None = None


def configure(config: FileScanConfig | None) -> None:
    global _config
    _config = config


def file_scan_config() -> FileScanConfig | None:
    return _config


def config_from_env(env: Mapping[str, str]) -> FileScanConfig | None:
    url = env.get("ATESTA_FILE_SCAN_QUEUE_URL")
    if url is None:
        return None
    bucket = env["ATESTA_EVIDENCE_BUCKET"]
    client = boto3.client("sqs", region_name=env.get("AWS_DEFAULT_REGION"))
    return FileScanConfig(queue=SqsQueue(url, client), bucket=bucket)


def handle(body: str, bucket: str) -> bool:
    """Record one message's result in its organization's context. True: delete the message."""
    event = parse_scan_result(body, bucket)
    if event is None:
        return True  # not a result for an uploaded file: scan outputs, other buckets, noise
    with org_session(str(event.organization_id)) as session:
        recorded = record_file_scan(
            session,
            event.organization_id,
            event.evidence_id,
            storage_key=event.storage_key,
            status=event.status,
            object_version=event.object_version,
        )
        if recorded is not None:
            queue_event(session, event.organization_id, recorded.event_id, recorded.action)
            return True
        return has_file_scan(session, event.organization_id, event.evidence_id)


def drain(
    queue: Queue, handler: Callable[[str], bool], max_batches: int = MAX_BATCHES
) -> dict[str, int]:
    """Handle batches until the queue answers empty. A message whose handler fails is kept."""
    counts = {"done": 0, "retried": 0}
    for _ in range(max_batches):
        batch = queue.receive()
        if not batch:
            break
        for message in batch:
            try:
                done = handler(message.body)
            except Exception:  # noqa: BLE001 - kept for a later receive, then dead-lettered
                done = False
            if done:
                queue.delete(message.receipt)
            counts["done" if done else "retried"] += 1
    return counts
