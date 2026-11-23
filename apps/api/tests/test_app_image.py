"""API and worker image (issue #236): pinned, hash-locked, non-root, no repo paths at runtime.

The API's start command must never log request query strings (issue #257, rule 2): the sign-in
callback receives the OAuth code and state there.
"""

import http.client
import json
import re
import socket
import subprocess
import sys
import time
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


STAND_IN = """
async def app(scope, receive, send):
    if scope["type"] == "http":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})
"""


def api_command() -> list[str]:
    """The JSON CMD of the `api` stage."""
    stage = DOCKERFILE.split("FROM runtime AS api", 1)[1].split("FROM ", 1)[0]
    match = re.search(r"^CMD (\[.*\])$", stage, re.MULTILINE)
    assert match, "the api stage has no JSON CMD"
    command: list[str] = json.loads(match.group(1))
    return command


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def test_the_api_runs_uvicorn_on_the_app() -> None:
    assert api_command()[:2] == ["uvicorn", "atesta_api.main:app"]


def test_the_api_server_never_logs_a_query_string(tmp_path: Path) -> None:
    """uvicorn with the image's own flags, against a stand-in app, on loopback."""
    (tmp_path / "stand_in.py").write_text(STAND_IN)
    port = free_port()
    flags = api_command()[2:]
    for option in ("--host", "--port"):  # drop each option with its value; bound below
        if option in flags:
            at = flags.index(option)
            del flags[at : at + 2]
    argv = [sys.executable, "-m", "uvicorn", "stand_in:app", *flags, "--host", "127.0.0.1"]
    server = subprocess.Popen(  # noqa: S603 - fixed argv built from the repository's Dockerfile
        [*argv, "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        path = "/auth/callback?code=SYNTHETIC_CODE&state=SYNTHETIC_STATE"
        for _ in range(50):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            try:
                connection.request("GET", path)
                connection.getresponse().read()
                break
            except OSError:
                time.sleep(0.1)
            finally:
                connection.close()
        else:
            raise AssertionError("the stand-in server never answered")
        time.sleep(0.3)
    finally:
        server.terminate()
        output, _ = server.communicate(timeout=10)
    assert "Application startup complete" in output  # the server ran and logs at INFO
    assert "SYNTHETIC_CODE" not in output and "SYNTHETIC_STATE" not in output
