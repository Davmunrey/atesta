"""Evidence stores (evidence-file-uploads spec): local for development, S3 for hosted."""

import base64
import hashlib
import io
from pathlib import Path
from typing import Any

import boto3
import pytest
from atesta_api.modules.evidence.api import (
    LocalEvidenceStore,
    ObjectMissingError,
    S3EvidenceStore,
    StoreUnavailableError,
    store_from_env,
)
from botocore.response import StreamingBody
from botocore.stub import Stubber

DATA = b"%PDF-1.7\nsynthetic\n"
DIGEST = hashlib.sha256(DATA).hexdigest()
KEY = "11111111-1111-4111-8111-111111111111/evidence/22222222-2222-4222-8222-222222222222/a.pdf"
BUCKET = "atesta-test-evidence"


@pytest.fixture
def dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATESTA_ENV", "test")


# --- local ---------------------------------------------------------------------------------


@pytest.mark.parametrize("env", [None, "prod", "production", "staging", ""])
def test_the_local_store_refuses_to_start_outside_development(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: str | None
) -> None:
    if env is None:
        monkeypatch.delenv("ATESTA_ENV", raising=False)
    else:
        monkeypatch.setenv("ATESTA_ENV", env)
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        LocalEvidenceStore(tmp_path)


def test_the_local_store_round_trips_and_bounds_its_reads(tmp_path: Path, dev: None) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    store.write(KEY, io.BytesIO(DATA), sha256=DIGEST, media_type="application/pdf", size=len(DATA))
    assert store.read(KEY, max_bytes=1000) == DATA
    assert store.read(KEY, max_bytes=4) == DATA[:4]
    with pytest.raises(ObjectMissingError):
        store.read(KEY.replace("a.pdf", "b.pdf"), max_bytes=10)
    # A second write under the same key is a new version, as in the versioned bucket.
    store.write(KEY, io.BytesIO(b"v2"), sha256="0" * 64, media_type="text/plain", size=2)
    assert store.read(KEY, max_bytes=10) == b"v2"


@pytest.mark.parametrize(
    "key", ["", "/etc/passwd", "../outside", "a/../../b", "a//b", "a/./b", "a\\b", "a/b\x00"]
)
def test_the_local_store_refuses_unsafe_keys(tmp_path: Path, dev: None, key: str) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    with pytest.raises(ValueError, match="unsafe"):
        store.write(key, io.BytesIO(b"x"), sha256=DIGEST, media_type="text/plain", size=1)
    with pytest.raises(ValueError, match="unsafe"):
        store.read(key, max_bytes=1)


def test_the_local_store_does_not_follow_a_symlink_out_of_its_root(
    tmp_path: Path, dev: None
) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    (tmp_path / "outside").mkdir()
    (store.root / "org").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="unsafe"):
        store.write("org/a.pdf", io.BytesIO(b"x"), sha256=DIGEST, media_type="x/y", size=1)


# --- S3 (botocore stubber: no network) -----------------------------------------------------


@pytest.fixture
def s3() -> Any:
    return boto3.client(
        "s3",
        region_name="eu-south-2",
        aws_access_key_id="test",
        aws_secret_access_key="test",  # noqa: S106 - stubbed client, never sent
    )


def test_the_s3_store_sends_the_checksum_type_and_length(s3: Any) -> None:
    body = io.BytesIO(DATA)
    with Stubber(s3) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": BUCKET,
                "Key": KEY,
                "Body": body,
                "ContentType": "application/pdf",
                "ContentLength": len(DATA),
                "ChecksumSHA256": base64.b64encode(bytes.fromhex(DIGEST)).decode(),
            },
        )
        S3EvidenceStore(BUCKET, s3).write(
            KEY, body, sha256=DIGEST, media_type="application/pdf", size=len(DATA)
        )
        stub.assert_no_pending_responses()


def test_the_s3_store_reads_at_most_the_bytes_asked_for(s3: Any) -> None:
    stored = DATA + b"appended by someone else"
    with Stubber(s3) as stub:
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(stored), len(stored))},
            {"Bucket": BUCKET, "Key": KEY},
        )
        assert (
            S3EvidenceStore(BUCKET, s3).read(KEY, max_bytes=len(DATA) + 1)
            == stored[: len(DATA) + 1]
        )


def test_the_s3_store_reads_the_scanned_version_when_one_is_given(s3: Any) -> None:
    """evidence-malware-scanning spec D5: the version GuardDuty read is the one served."""
    with Stubber(s3) as stub:
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(DATA), len(DATA))},
            {"Bucket": BUCKET, "Key": KEY, "VersionId": "v-scanned"},
        )
        assert S3EvidenceStore(BUCKET, s3).read(KEY, len(DATA) + 1, version="v-scanned") == DATA
        stub.assert_no_pending_responses()


def test_only_the_s3_store_has_a_scanner(tmp_path: Path, dev: None, s3: Any) -> None:
    """The local store never claims a scan ran (evidence-malware-scanning spec)."""
    assert S3EvidenceStore(BUCKET, s3).scanned is True
    local = LocalEvidenceStore(tmp_path / "evidence")
    assert local.scanned is False
    local.write(KEY, io.BytesIO(DATA), sha256=DIGEST, media_type="application/pdf", size=len(DATA))
    assert local.read(KEY, 100, version="ignored-locally") == DATA


def test_the_s3_store_tells_a_missing_object_from_an_outage(s3: Any) -> None:
    store = S3EvidenceStore(BUCKET, s3)
    with Stubber(s3) as stub:
        stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
        with pytest.raises(ObjectMissingError):
            store.read(KEY, max_bytes=10)
        stub.add_client_error("get_object", service_error_code="SlowDown", http_status_code=503)
        with pytest.raises(StoreUnavailableError):
            store.read(KEY, max_bytes=10)
        stub.add_client_error("put_object", service_error_code="BadDigest", http_status_code=400)
        with pytest.raises(StoreUnavailableError) as failure:
            store.write(KEY, io.BytesIO(DATA), sha256=DIGEST, media_type="x/y", size=len(DATA))
    assert KEY not in str(failure.value)  # keys carry file names: never in errors or logs


# --- configuration -------------------------------------------------------------------------


def test_no_store_is_configured_by_default() -> None:
    assert store_from_env({}) is None


def test_the_local_store_needs_its_directory_and_a_development_environment(
    tmp_path: Path, dev: None
) -> None:
    store = store_from_env(
        {"ATESTA_EVIDENCE_STORE": "local", "ATESTA_EVIDENCE_STORE_DIR": str(tmp_path / "e")}
    )
    assert isinstance(store, LocalEvidenceStore)
    with pytest.raises(KeyError, match="ATESTA_EVIDENCE_STORE_DIR"):
        store_from_env({"ATESTA_EVIDENCE_STORE": "local"})


def test_the_s3_store_needs_its_bucket() -> None:
    env = {"ATESTA_EVIDENCE_STORE": "s3", "AWS_DEFAULT_REGION": "eu-south-2"}
    with pytest.raises(KeyError, match="ATESTA_EVIDENCE_BUCKET"):
        store_from_env(env)
    store = store_from_env({**env, "ATESTA_EVIDENCE_BUCKET": BUCKET})
    assert isinstance(store, S3EvidenceStore)


@pytest.mark.parametrize("value", ["S3", "disk", "", "none"])
def test_an_unknown_store_stops_the_start(value: str) -> None:
    with pytest.raises(ValueError, match="ATESTA_EVIDENCE_STORE"):
        store_from_env({"ATESTA_EVIDENCE_STORE": value})
