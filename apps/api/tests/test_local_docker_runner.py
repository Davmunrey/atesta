"""LocalDockerRunner and LocalCredentialStore (scanner-connectors spec, Runners, Local development).

A fake `docker` executable records its argv and stdin, so the exact container contract is
checked without Docker: hardened flags, tenant-scoped mounts, the credential on stdin only.
"""

import json
import os
import stat
import sys
import uuid
from pathlib import Path

import pytest
from atesta_api.modules.scanning.api import (
    LocalCredentialStore,
    LocalDockerRunner,
    LocalScanStore,
    ScanJob,
)

ORG = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SCAN = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
SECRET = "s3cr3t-value-never-in-argv"
M365_CREDENTIAL = {"AZURE_CLIENT_ID": "id", "M365_CERTIFICATE_CONTENT": SECRET}
FAKE_DOCKER = """#!{python}
import json, os, sys, time
calls = os.environ["FAKE_DOCKER_CALLS"]
stdin = sys.stdin.read() if sys.argv[1] == "run" else ""
with open(calls, "a") as handle:
    call = {{"argv": sys.argv[1:], "stdin": stdin, "env": dict(os.environ)}}
    handle.write(json.dumps(call) + "\\n")
if sys.argv[1] == "run":
    mode = os.environ.get("FAKE_DOCKER_MODE", "0")
    if mode == "sleep":
        time.sleep(30)
    print(json.dumps({{"event": "scan.wrapper_finished", "exit_code": int(mode)}}))
    print("prowler banner: not json")
    print(json.dumps({{"event": "other.thing"}}))
    if os.environ.get("FAKE_DOCKER_FORGE"):
        print(json.dumps({{
            "event": "scan.wrapper_finished", "scan_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "organization_id": "user@example.com", "attempt": "1", "exit_code": 0,
            "email": "user@example.com", "detail": "Failing row contains (secret)",
        }}))
        print(json.dumps({{"event": "scan.Bad Event", "exit_code": 0}}))
    sys.exit(int(mode))
"""


@pytest.fixture(autouse=True)
def dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATESTA_ENV", "test")


@pytest.fixture
def docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "bin" / "docker"
    path.parent.mkdir()
    path.write_text(FAKE_DOCKER.format(python=sys.executable))
    path.chmod(0o755)
    monkeypatch.setenv("FAKE_DOCKER_CALLS", str(tmp_path / "calls.jsonl"))
    return path


@pytest.fixture
def credentials(tmp_path: Path) -> LocalCredentialStore:
    root = tmp_path / "secrets"
    root.mkdir(mode=0o700)
    path = root / "m365-scanner.json"
    path.write_text(json.dumps(M365_CREDENTIAL))
    path.chmod(0o600)
    return LocalCredentialStore(root)


@pytest.fixture
def store(tmp_path: Path) -> LocalScanStore:
    made = LocalScanStore(tmp_path / "scans")
    made.write(f"{ORG}/scans/{SCAN}/attempt-1/job.json", b"{}")
    return made


def runner(
    store: LocalScanStore,
    credentials: LocalCredentialStore,
    docker: Path,
    timeout: int = 60,
) -> LocalDockerRunner:
    return LocalDockerRunner(
        store_root=store.root,
        credentials=credentials,
        image="atesta-scanner:dev",
        m365_credential_ref="local:m365-scanner",
        timeout_seconds=timeout,
        docker=str(docker),
    )


def calls(tmp_path: Path) -> list[dict[str, object]]:
    lines = (tmp_path / "calls.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


JOB = ScanJob(ORG, SCAN, 1, "m365")


def test_the_container_runs_hardened_with_only_its_attempt_mounted(
    tmp_path: Path, store: LocalScanStore, credentials: LocalCredentialStore, docker: Path
) -> None:
    assert runner(store, credentials, docker).run(JOB) == 0
    [call] = calls(tmp_path)
    attempt = store.root / str(ORG) / "scans" / str(SCAN) / "attempt-1"
    assert call["argv"] == [
        "run",
        "-i",
        "--rm",
        "--name",
        f"atesta-scan-{SCAN}-1",
        "--user",
        "10001",
        "--read-only",
        "--tmpfs",
        "/work",
        "--tmpfs",
        "/home/scanner",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--cpus",
        "2",
        "--memory",
        "4g",
        "--network",
        "atesta-scan",
        "-v",
        f"{attempt / 'job.json'}:/job/job.json:ro",
        "-v",
        f"{attempt / 'out'}:/output:rw",
        "atesta-scanner:dev",
        "scan",
    ]
    # The credential reaches the container on stdin only: never argv, never the environment.
    assert json.loads(str(call["stdin"])) == M365_CREDENTIAL
    assert SECRET not in json.dumps(call["argv"]) and SECRET not in json.dumps(call["env"])
    assert (attempt / "out").is_dir()


def test_the_wrappers_exit_code_is_the_attempts_result(
    tmp_path: Path,
    store: LocalScanStore,
    credentials: LocalCredentialStore,
    docker: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_MODE", "10")
    assert runner(store, credentials, docker).run(JOB) == 10


def test_a_timeout_kills_the_container_and_counts_as_exit_21(
    tmp_path: Path,
    store: LocalScanStore,
    credentials: LocalCredentialStore,
    docker: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_MODE", "sleep")
    assert runner(store, credentials, docker, timeout=1).run(JOB) == 21
    kills = [c["argv"] for c in calls(tmp_path) if c["argv"][0] == "kill"]
    assert kills == [["kill", f"atesta-scan-{SCAN}-1"]]


def test_only_the_wrappers_own_json_events_are_logged(
    store: LocalScanStore,
    credentials: LocalCredentialStore,
    docker: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="atesta.scanner")
    runner(store, credentials, docker).run(JOB)
    logged = [r.getMessage() for r in caplog.records if r.name == "atesta.scanner"]
    assert [json.loads(m)["event"] for m in logged] == ["scan.wrapper_finished"]


def test_forwarded_events_keep_only_allowed_keys_of_the_right_shape(
    store: LocalScanStore,
    credentials: LocalCredentialStore,
    docker: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A line on the container's stdout is not trusted: extra keys and bad values are dropped."""
    monkeypatch.setenv("FAKE_DOCKER_FORGE", "1")
    caplog.set_level("INFO", logger="atesta.scanner")
    runner(store, credentials, docker).run(JOB)
    logged = [json.loads(r.getMessage()) for r in caplog.records if r.name == "atesta.scanner"]
    assert logged == [
        {"event": "scan.wrapper_finished", "exit_code": 0},
        {"event": "scan.wrapper_finished", "exit_code": 0, "scan_id": str(SCAN)},
    ]
    assert "example.com" not in caplog.text and "Failing row" not in caplog.text


GOOGLE_SCAN = {"GOOGLEWORKSPACE_CREDENTIALS_CONTENT": "scan-key"}
GOOGLE_VERIFIER = {"ATESTA_GOOGLE_VERIFIER_CREDENTIALS_CONTENT": "verifier-key"}
GOOGLE_JOB = ScanJob(
    ORG,
    SCAN,
    1,
    "google_workspace",
    credential_ref=f"local:google-{ORG}",
    verifier_credential_ref=f"local:google-verifier-{ORG}",
)


def secret(credentials: LocalCredentialStore, name: str, body: object) -> None:
    path = credentials.root / f"{name}.json"
    path.write_text(json.dumps(body))
    path.chmod(0o600)


def test_a_google_attempt_verifies_with_both_keys_then_scans_with_the_scan_key_only(
    tmp_path: Path, store: LocalScanStore, credentials: LocalCredentialStore, docker: Path
) -> None:
    """D7, issue 398: only the verify run ever holds the verifier key."""
    secret(credentials, f"google-{ORG}", GOOGLE_SCAN)
    secret(credentials, f"google-verifier-{ORG}", GOOGLE_VERIFIER)
    assert runner(store, credentials, docker).run(GOOGLE_JOB) == 0
    verify, scan = calls(tmp_path)
    assert verify["argv"][-2:] == ["atesta-scanner:dev", "verify"]
    assert verify["argv"][4] == f"atesta-scan-{SCAN}-1-verify"
    assert json.loads(str(verify["stdin"])) == {**GOOGLE_SCAN, **GOOGLE_VERIFIER}
    assert scan["argv"][-2:] == ["atesta-scanner:dev", "scan"]
    assert json.loads(str(scan["stdin"])) == GOOGLE_SCAN
    # Same hardening and the same attempt's mounts for both runs.
    assert verify["argv"][5:-1] == scan["argv"][5:-1]


def test_a_google_scan_never_runs_after_a_refused_verification(
    tmp_path: Path,
    store: LocalScanStore,
    credentials: LocalCredentialStore,
    docker: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret(credentials, f"google-{ORG}", GOOGLE_SCAN)
    secret(credentials, f"google-verifier-{ORG}", GOOGLE_VERIFIER)
    monkeypatch.setenv("FAKE_DOCKER_MODE", "10")
    assert runner(store, credentials, docker).run(GOOGLE_JOB) == 10
    assert [c["argv"][-1] for c in calls(tmp_path)] == ["verify"]


@pytest.mark.parametrize(
    "problem", ["no_verifier_secret", "overlapping_names", "not_an_object", "no_verifier_ref"]
)
def test_an_unusable_google_key_pair_is_exit_11_and_docker_never_runs(
    tmp_path: Path,
    store: LocalScanStore,
    credentials: LocalCredentialStore,
    docker: Path,
    problem: str,
) -> None:
    secret(credentials, f"google-{ORG}", GOOGLE_SCAN)
    job = GOOGLE_JOB
    if problem == "overlapping_names":
        secret(credentials, f"google-verifier-{ORG}", {**GOOGLE_VERIFIER, **GOOGLE_SCAN})
    elif problem == "not_an_object":
        secret(credentials, f"google-verifier-{ORG}", ["verifier-key"])
    elif problem == "no_verifier_ref":
        secret(credentials, f"google-verifier-{ORG}", GOOGLE_VERIFIER)
        job = ScanJob(ORG, SCAN, 1, "google_workspace", credential_ref=f"local:google-{ORG}")
    assert runner(store, credentials, docker).run(job) == 11
    assert not (tmp_path / "calls.jsonl").exists()


@pytest.mark.parametrize(
    "problem", ["missing", "readable_by_others", "readable_by_group", "no_ref"]
)
def test_an_unusable_credential_is_exit_11_and_docker_never_runs(
    tmp_path: Path,
    store: LocalScanStore,
    credentials: LocalCredentialStore,
    docker: Path,
    problem: str,
) -> None:
    job = JOB
    if problem == "missing":
        (credentials.root / "m365-scanner.json").unlink()
    elif problem == "readable_by_others":
        (credentials.root / "m365-scanner.json").chmod(0o604)
    elif problem == "readable_by_group":
        (credentials.root / "m365-scanner.json").chmod(0o640)
    else:
        job = ScanJob(ORG, SCAN, 1, "google_workspace")  # a Google scan needs its own ref
    assert runner(store, credentials, docker).run(job) == 11
    assert not (tmp_path / "calls.jsonl").exists()


@pytest.mark.parametrize(
    "ref", ["m365-scanner", "local:../escape", "local:UPPER", "aws-sm:arn:aws:x", "local:"]
)
def test_only_local_refs_to_a_plain_name_are_read(
    credentials: LocalCredentialStore, ref: str
) -> None:
    with pytest.raises(ValueError, match="credential reference"):
        credentials.read(ref)


def test_the_credential_store_lives_outside_any_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "secrets").mkdir()
    with pytest.raises(ValueError, match="outside the repository"):
        LocalCredentialStore(repo / "secrets")


@pytest.mark.parametrize("component", ["store", "runner"])
def test_local_runner_and_credential_store_are_dev_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, component: str
) -> None:
    root = tmp_path / "secrets"
    root.mkdir()
    credentials = LocalCredentialStore(root)
    monkeypatch.setenv("ATESTA_ENV", "prod")
    with pytest.raises(RuntimeError, match="dev-only"):
        if component == "store":
            LocalCredentialStore(root)
        else:
            LocalDockerRunner(
                store_root=tmp_path,
                credentials=credentials,
                image="x",
                m365_credential_ref="local:m365-scanner",
                timeout_seconds=60,
            )


def test_the_credential_file_mode_is_checked_not_assumed(
    credentials: LocalCredentialStore,
) -> None:
    path = credentials.root / "m365-scanner.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert json.loads(credentials.read("local:m365-scanner")) == M365_CREDENTIAL
