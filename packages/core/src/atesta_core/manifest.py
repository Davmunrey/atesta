"""Scan output manifests (scanner-connectors spec, Ingest step 1).

The runner writes the manifest last, listing every output file with its sha256 and size. Ingest
validates the whole manifest before reading any file, then reads only the files it lists and
checks each one. File names are flat and plain, so a manifest can never point outside its
folder.
An entry may also carry `raw_sha256`: the hash of the file as the engine wrote it, before the
wrapper rewrote it (D10: personal-data fields stripped).
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping

_VERSION = 1
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class ManifestError(ValueError):
    """The manifest or a file it lists cannot be trusted."""


def _check_name(name: object) -> str:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ManifestError("manifest lists an unsafe file name")
    return name


def _check_raw(name: str, raw: object) -> str:
    if not isinstance(raw, str) or not _SHA256.fullmatch(raw):
        raise ManifestError(f"{name} has a malformed raw sha256")
    return raw


def build_manifest(
    files: Mapping[str, bytes], raw_sha256: Mapping[str, str] | None = None
) -> bytes:
    raw = dict(raw_sha256 or {})
    if not raw.keys() <= files.keys():
        raise ManifestError("a raw sha256 names a file the manifest does not list")
    entries = []
    for name, data in sorted(files.items()):
        entry: dict[str, object] = {
            "name": _check_name(name),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }
        if name in raw:
            entry["raw_sha256"] = _check_raw(name, raw[name])
        entries.append(entry)
    return json.dumps({"version": _VERSION, "files": entries}, indent=1).encode()


def _entries(manifest: bytes, max_bytes: int) -> list[tuple[str, str, int]]:
    try:
        data = json.loads(manifest)
    except (ValueError, RecursionError):  # nesting too deep to parse is not a manifest
        raise ManifestError("manifest is not JSON") from None
    if not isinstance(data, dict) or data.get("version") != _VERSION:
        raise ManifestError("unknown manifest format")
    files = data.get("files")
    if not isinstance(files, list):
        raise ManifestError("unknown manifest format")
    entries: list[tuple[str, str, int]] = []
    for entry in files:
        if not isinstance(entry, dict):
            raise ManifestError("unknown manifest format")
        name = _check_name(entry.get("name"))
        sha256, size = entry.get("sha256"), entry.get("size")
        if any(name == seen for seen, _, _ in entries):
            raise ManifestError(f"{name} is listed twice")
        if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
            raise ManifestError(f"{name} has a malformed sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ManifestError(f"{name} has a malformed size")
        if size > max_bytes:
            raise ManifestError(f"{name} is over the size limit")
        if "raw_sha256" in entry:
            _check_raw(name, entry["raw_sha256"])
        entries.append((name, sha256, size))
    return entries


def verify_manifest(
    manifest: bytes, read: Callable[[str], bytes], max_bytes: int
) -> dict[str, bytes]:
    """Return the listed files, each checked against its size and sha256."""
    files: dict[str, bytes] = {}
    for name, sha256, size in _entries(manifest, max_bytes):
        data = read(name)
        if len(data) != size:
            raise ManifestError(f"{name}: size differs from the manifest")
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ManifestError(f"{name}: sha256 differs from the manifest")
        files[name] = data
    return files
