"""Scan output manifests: what the runner writes is exactly what ingest reads."""

import json
from typing import NoReturn

import pytest
from atesta_core.manifest import ManifestError, build_manifest, verify_manifest

FILES = {"prowler.ocsf.json": b'[{"a": 1}]', "notes.txt": b"x"}
X_SHA = "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
OCSF_SHA = "2696610e78752a9e7bd0c4b0404b2fb01a41a19bf23c9b8efa066811c8555d6b"


def manifest(*entries: dict[str, object], version: int = 1) -> bytes:
    return json.dumps({"version": version, "files": list(entries)}).encode()


def never_read(name: str) -> NoReturn:
    raise AssertionError(f"read {name} before the manifest was validated")


def test_a_manifest_lists_every_file_with_its_hash_and_size() -> None:
    assert json.loads(build_manifest(FILES)) == {
        "version": 1,
        "files": [
            {"name": "notes.txt", "sha256": X_SHA, "size": 1},
            {"name": "prowler.ocsf.json", "sha256": OCSF_SHA, "size": 10},
        ],
    }


def test_listed_files_come_back_verified() -> None:
    assert verify_manifest(build_manifest(FILES), FILES.__getitem__, max_bytes=10) == FILES


def test_a_changed_file_is_rejected() -> None:
    def tampered(name: str) -> bytes:
        return b"y" if name == "notes.txt" else FILES[name]

    with pytest.raises(ManifestError, match="notes.txt"):
        verify_manifest(build_manifest(FILES), tampered, max_bytes=10)


def test_a_wrong_size_is_rejected() -> None:
    wrong = manifest({"name": "notes.txt", "sha256": X_SHA, "size": 2})
    with pytest.raises(ManifestError, match="size"):
        verify_manifest(wrong, FILES.__getitem__, max_bytes=10)


INVALID = {
    "not json": b"{",
    "not an object": b"[]",
    "unknown version": manifest(version=2),
    "path traversal": manifest({"name": "../job.json", "sha256": X_SHA, "size": 1}),
    "nested path": manifest({"name": "a/b.json", "sha256": X_SHA, "size": 1}),
    "empty name": manifest({"name": "", "sha256": X_SHA, "size": 1}),
    "bad hash": manifest({"name": "notes.txt", "sha256": "X" * 64, "size": 1}),
    "negative size": manifest({"name": "notes.txt", "sha256": X_SHA, "size": -1}),
    "over the size limit": manifest({"name": "big.json", "sha256": X_SHA, "size": 11}),
    "duplicate name": manifest(
        {"name": "notes.txt", "sha256": X_SHA, "size": 1},
        {"name": "notes.txt", "sha256": X_SHA, "size": 1},
    ),
}


@pytest.mark.parametrize("name", sorted(INVALID))
def test_an_invalid_manifest_is_rejected_before_any_file_is_read(name: str) -> None:
    with pytest.raises(ManifestError):
        verify_manifest(INVALID[name], never_read, max_bytes=10)
