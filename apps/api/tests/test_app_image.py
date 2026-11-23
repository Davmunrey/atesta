"""API and worker image (issue #236): pinned, hash-locked, non-root, no repo paths at runtime."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = (ROOT / "apps" / "Dockerfile").read_text()


def test_third_party_packages_come_from_the_frozen_lockfile() -> None:
    assert "uv export --frozen --no-dev --package atesta-worker --no-emit-workspace" in DOCKERFILE
    assert "COPY pyproject.toml uv.lock ./" in DOCKERFILE


def test_every_base_image_is_pinned_by_digest() -> None:
    bases = re.findall(r"^FROM (\S+)", DOCKERFILE, flags=re.MULTILINE)
    external = [b for b in bases if b not in {"base", "build", "runtime", "uv"}]
    assert external and all(re.search(r"@sha256:[0-9a-f]{64}$", b) for b in external)


def test_installs_are_hash_locked_or_offline() -> None:
    installs = [line for line in DOCKERFILE.splitlines() if re.search(r"pip (install|wheel)", line)]
    assert len(installs) >= 3
    for line in installs:
        # Third-party packages only by hash; Atesta's own packages only from the local tree.
        assert "--require-hashes" in line or ("--no-index" in line and "--no-deps" in line), line


def test_the_image_runs_as_user_10001_with_the_catalog_path_set() -> None:
    assert re.findall(r"^USER (\S+)", DOCKERFILE, flags=re.MULTILINE)[-1] == "10001"
    assert "ATESTA_CATALOG_DIR=/app/catalog" in DOCKERFILE
    assert "ATESTA_SCANNER_EXPECTED=/app/scanner/expected" in DOCKERFILE
    targets = set(re.findall(r"^FROM \S+ AS (\S+)", DOCKERFILE, flags=re.MULTILINE))
    assert {"api", "worker"} <= targets
