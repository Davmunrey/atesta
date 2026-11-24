"""Draining GuardDuty scan results from SQS (evidence-malware-scanning spec, #430). No network:
the queue client is stubbed with botocore's Stubber."""

from collections.abc import Callable
from typing import Any

import boto3
import pytest
from atesta_worker.file_scans import (
    FileScanConfig,
    Message,
    SqsQueue,
    config_from_env,
    drain,
)
from atesta_worker.jobs import make_blueprint
from botocore.stub import Stubber

QUEUE_URL = "https://sqs.eu-south-2.amazonaws.com/111122223333/atesta-dev-file-scans"


@pytest.fixture
def sqs() -> Any:
    return boto3.client(
        "sqs",
        region_name="eu-south-2",
        aws_access_key_id="testing",  # nosec - stubbed client, never sent
        aws_secret_access_key="testing",  # nosec - stubbed client, never sent
    )


def test_the_queue_long_polls_ten_at_a_time_and_deletes_by_receipt(sqs: Any) -> None:
    with Stubber(sqs) as stub:
        stub.add_response(
            "receive_message",
            {"Messages": [{"ReceiptHandle": "r1", "Body": "{}"}, {"ReceiptHandle": "r2"}]},
            {"QueueUrl": QUEUE_URL, "MaxNumberOfMessages": 10, "WaitTimeSeconds": 1},
        )
        stub.add_response("receive_message", {}, None)
        stub.add_response("delete_message", {}, {"QueueUrl": QUEUE_URL, "ReceiptHandle": "r1"})
        queue = SqsQueue(QUEUE_URL, sqs)
        assert queue.receive() == [Message("r1", "{}"), Message("r2", "")]
        assert queue.receive() == []
        queue.delete("r1")
        stub.assert_no_pending_responses()


class FakeQueue:
    def __init__(self, *batches: list[str]) -> None:
        self.batches = [
            [Message(f"r{i}-{j}", body) for j, body in enumerate(batch)]
            for i, batch in enumerate(batches)
        ]
        self.deleted: list[str] = []

    def receive(self) -> list[Message]:
        return self.batches.pop(0) if self.batches else []

    def delete(self, receipt: str) -> None:
        self.deleted.append(receipt)


def outcome(table: dict[str, bool | Exception]) -> Callable[[str], bool]:
    def handle(body: str) -> bool:
        result = table[body]
        if isinstance(result, Exception):
            raise result
        return result

    return handle


def test_drain_deletes_handled_messages_and_keeps_the_rest() -> None:
    queue = FakeQueue(["recorded", "not-ours", "too-early"], ["broken"])
    counts = drain(
        queue,
        outcome(
            {
                "recorded": True,
                "not-ours": True,
                "too-early": False,
                "broken": RuntimeError("database down"),
            }
        ),
    )
    assert queue.deleted == ["r0-0", "r0-1"]  # kept ones come back after the visibility timeout
    assert counts == {"done": 2, "retried": 2}


def test_drain_stops_at_its_batch_limit() -> None:
    queue = FakeQueue(*[["a"]] * 5)
    assert drain(queue, outcome({"a": True}), max_batches=3) == {"done": 3, "retried": 0}
    assert len(queue.batches) == 2


def test_without_a_queue_nothing_is_configured() -> None:
    assert config_from_env({}) is None
    assert config_from_env({"ATESTA_EVIDENCE_BUCKET": "b"}) is None
    with pytest.raises(KeyError, match="ATESTA_EVIDENCE_BUCKET"):
        config_from_env({"ATESTA_FILE_SCAN_QUEUE_URL": QUEUE_URL})
    config = config_from_env(
        {
            "ATESTA_FILE_SCAN_QUEUE_URL": QUEUE_URL,
            "ATESTA_EVIDENCE_BUCKET": "b",
            "AWS_DEFAULT_REGION": "eu-south-2",
        }
    )
    assert isinstance(config, FileScanConfig) and config.bucket == "b"
    assert isinstance(config.queue, SqsQueue)


def test_the_poll_is_a_periodic_job_with_no_arguments_but_its_time() -> None:
    blueprint = make_blueprint()
    task = blueprint.tasks["poll_file_scans"]
    assert task.queue == "files"
    periodic = blueprint.periodic_registry.periodic_tasks[("poll_file_scans", "")]
    assert periodic.cron == "* * * * *"
