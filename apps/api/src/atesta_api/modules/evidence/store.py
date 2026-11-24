"""Where uploaded evidence files live (evidence-file-uploads spec).

The API is the only writer. A key is built by the server under `<organization_id>/evidence/`
and is never echoed in an error: it carries a file name (rule 2).
"""

import base64
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO, Protocol

import boto3  # type: ignore[import-untyped]  # boto3 ships no type stubs
from botocore.exceptions import (  # type: ignore[import-untyped]  # nor does botocore
    BotoCoreError,
    ClientError,
)

from atesta_api.platform.devenv import require_dev

_CHUNK = 1024 * 1024


class StoreUnavailableError(Exception):
    """The store did not accept the write or could not answer the read."""


class ObjectMissingError(Exception):
    """No object under the key: for a recorded file, an integrity failure."""


class EvidenceStore(Protocol):
    # True when a malware scanner reports on every new object (evidence-malware-scanning spec).
    scanned: bool

    def write(self, key: str, body: BinaryIO, *, sha256: str, media_type: str, size: int) -> None:
        """Store the whole body under the key. A repeated key is a new version."""

    def read(self, key: str, max_bytes: int, version: str | None = None) -> bytes:
        """At most max_bytes of the object (of that version, when given), so a swapped-in huge
        object cannot fill memory."""


class LocalEvidenceStore:
    """A directory laid out like the bucket, for local development and tests. No scanner, and
    one version per key: a given version is ignored."""

    scanned = False

    def __init__(self, root: Path) -> None:
        require_dev("LocalEvidenceStore")
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        parts = key.split("/")
        if not key or any(p in ("", ".", "..") or "\\" in p or "\x00" in p for p in parts):
            raise ValueError("unsafe evidence key")
        path = self.root.joinpath(*parts)
        if not path.resolve().is_relative_to(self.root):  # a symlink must not lead outside
            raise ValueError("unsafe evidence key")
        return path

    def write(self, key: str, body: BinaryIO, *, sha256: str, media_type: str, size: int) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            shutil.copyfileobj(body, handle, _CHUNK)

    def read(self, key: str, max_bytes: int, version: str | None = None) -> bytes:
        try:
            with self._path(key).open("rb") as handle:
                return handle.read(max_bytes)
        except FileNotFoundError:
            raise ObjectMissingError from None


class S3EvidenceStore:
    """The evidence bucket (hosted-environment spec, `s3-evidence`).

    The SHA-256 goes with the write, so S3 refuses bytes that changed on the way; Object Lock
    also requires a checksum on every upload. Encryption and retention are the bucket's defaults.
    GuardDuty Malware Protection scans every new object version in the bucket.
    """

    scanned = True

    def __init__(self, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    def write(self, key: str, body: BinaryIO, *, sha256: str, media_type: str, size: int) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType=media_type,
                ContentLength=size,
                ChecksumSHA256=base64.b64encode(bytes.fromhex(sha256)).decode(),
            )
        except (BotoCoreError, ClientError) as error:
            raise StoreUnavailableError(type(error).__name__) from None

    def read(self, key: str, max_bytes: int, version: str | None = None) -> bytes:
        where = {"Bucket": self._bucket, "Key": key}
        if version is not None:
            where["VersionId"] = version
        try:
            response = self._client.get_object(**where)
            data: bytes = response["Body"].read(max_bytes)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in ("NoSuchKey", "NoSuchVersion"):
                raise ObjectMissingError from None
            raise StoreUnavailableError(type(error).__name__) from None
        except BotoCoreError as error:
            raise StoreUnavailableError(type(error).__name__) from None
        return data


def store_from_env(env: Mapping[str, str]) -> EvidenceStore | None:
    """The store named by ATESTA_EVIDENCE_STORE; None (uploads disabled) when it is unset."""
    kind = env.get("ATESTA_EVIDENCE_STORE")
    if kind is None:
        return None
    if kind == "local":
        return LocalEvidenceStore(Path(env["ATESTA_EVIDENCE_STORE_DIR"]))
    if kind == "s3":
        bucket = env["ATESTA_EVIDENCE_BUCKET"]
        return S3EvidenceStore(
            bucket, boto3.client("s3", region_name=env.get("AWS_DEFAULT_REGION"))
        )
    raise ValueError("ATESTA_EVIDENCE_STORE must be 'local' or 's3'")
