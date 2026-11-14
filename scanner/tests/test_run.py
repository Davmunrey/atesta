"""One wrapper run, end to end, with a fake Prowler (scanner-connectors spec, Wrapper)."""

import hashlib
import io
import json
import sys
from pathlib import Path

import pytest
from atesta_core.manifest import verify_manifest
from atesta_scanner import __main__ as cli
from atesta_scanner.exits import ExitCode
from atesta_scanner.job import Job, JobError, load_job
from atesta_scanner.run import DirectorySink, OutputExistsError, read_credential, run_scan

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic" / "m365"
TENANT = "11111111-1111-4111-8111-111111111111"
SECRET = {  # Atesta's one M365 certificate: the tenant comes from the job (D5)
    "AZURE_CLIENT_ID": "22222222-aaaa-4bbb-8ccc-333333333333",
    "M365_CERTIFICATE_CONTENT": "TUlJS0h5LXRlc3QtY2VydGlmaWNhdGUtY29udGVudA==",
}
JOB = {
    "organization_id": "aaaaaaaa-0000-4000-8000-000000000001",
    "scan_id": "dddddddd-0000-4000-8000-000000000001",
    "attempt": 1,
    "provider": "m365",
    "tenant": TENANT,
    "excluded": ["teams_meeting_recording_disabled"],
}

FAKE = """#!{python}
import json, os, sys
argv = sys.argv[1:]
out = argv[argv.index("-o") + 1]
log = argv[argv.index("--log-file") + 1]
with open(log, "w") as f:
    f.write("env " + " ".join(sorted(os.environ)) + "\\n")
    f.write("argv " + " ".join(argv) + "\\n")
    cert = os.environ.get("M365_CERTIFICATE_CONTENT", "")
    f.write("ERROR pwsh: [Convert]::FromBase64String(" + cert + ")\\n")
print("stdout never reaches the container log", os.environ.get("M365_CERTIFICATE_CONTENT"))
{body}
"""
WRITE_OUTPUT = """
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "prowler.ocsf.json"), "wb") as f:
    f.write(open({fixture!r}, "rb").read())
sys.exit(0)
"""


def fake_prowler(tmp_path: Path, body: str) -> str:
    path = tmp_path / "prowler"
    path.write_text(FAKE.format(python=sys.executable, body=body))
    path.chmod(0o755)
    return str(path)


def with_metadata(tmp_path: Path, fixture: str = "scan.ocsf.json") -> Path:
    findings = json.loads((FIXTURES / fixture).read_bytes())
    for finding in findings:
        for resource in finding["resources"]:
            resource["data"] = {"metadata": {"userPrincipalName": "person@fixture.example"}}
    path = tmp_path / "raw.ocsf.json"
    path.write_text(json.dumps(findings))
    return path


def scan(tmp_path: Path, body: str, credential: dict[str, str] | None = None) -> ExitCode:
    work, output = tmp_path / "work", tmp_path / "output"
    executable = fake_prowler(tmp_path, body)
    sink = DirectorySink(output)
    return run_scan(
        load_job(json.dumps(JOB).encode()), credential or SECRET, sink, work, executable
    )


def files(tmp_path: Path) -> list[str]:
    return sorted(p.name for p in (tmp_path / "output").iterdir())


def test_a_successful_run_writes_stripped_output_scrubbed_log_and_manifest_last(
    tmp_path: Path,
) -> None:
    raw = with_metadata(tmp_path)
    assert scan(tmp_path, WRITE_OUTPUT.format(fixture=str(raw))) is ExitCode.DONE
    output = tmp_path / "output"
    assert files(tmp_path) == ["manifest.json", "prowler.log", "prowler.ocsf.json"]
    assert (output / "manifest.json").stat().st_mtime_ns >= (
        output / "prowler.ocsf.json"
    ).stat().st_mtime_ns
    manifest = (output / "manifest.json").read_bytes()
    verified = verify_manifest(manifest, lambda name: (output / name).read_bytes(), 10**8)
    assert set(verified) == {"prowler.log", "prowler.ocsf.json"}
    entry = next(e for e in json.loads(manifest)["files"] if e["name"] == "prowler.ocsf.json")
    assert entry["raw_sha256"] == hashlib.sha256(raw.read_bytes()).hexdigest()
    assert b"person@fixture.example" not in (output / "prowler.ocsf.json").read_bytes()
    log = (output / "prowler.log").read_text()
    assert SECRET["M365_CERTIFICATE_CONTENT"] not in log
    # The child saw exactly the minimal environment, and the exact argv.
    env_line = next(line for line in log.splitlines() if line.startswith("env "))
    observed_keys = env_line.split()[1:]
    # macOS adds this during Python startup, even when absent from subprocess.run(env=...).
    if sys.platform == "darwin" and "__CF_USER_TEXT_ENCODING" in observed_keys:
        observed_keys.remove("__CF_USER_TEXT_ENCODING")
    assert observed_keys == sorted(
        [
            "AZURE_CLIENT_ID",
            "AZURE_TENANT_ID",
            "HOME",
            "LANG",
            "M365_CERTIFICATE_CONTENT",
            "PATH",
            "POWERSHELL_TELEMETRY_OPTOUT",
            "TMPDIR",
        ]
    )
    assert "--excluded-checks teams_meeting_recording_disabled" in log


def test_a_failed_prowler_keeps_only_the_scrubbed_log(tmp_path: Path) -> None:
    assert scan(tmp_path, "sys.exit(1)") is ExitCode.PROWLER_FAILED
    assert files(tmp_path) == ["prowler.log"]
    assert (
        SECRET["M365_CERTIFICATE_CONTENT"] not in (tmp_path / "output" / "prowler.log").read_text()
    )


@pytest.mark.parametrize(
    "body",
    [
        "sys.exit(0)",  # no output file
        "os.makedirs(out, exist_ok=True)\n"
        "open(os.path.join(out, 'prowler.ocsf.json'), 'w').write('{')\n"
        "sys.exit(0)",
    ],
)
def test_missing_or_broken_output_is_invalid(tmp_path: Path, body: str) -> None:
    assert scan(tmp_path, body) is ExitCode.OUTPUT_INVALID
    assert files(tmp_path) == ["prowler.log"]


def test_a_finding_from_another_tenant_is_invalid_output(tmp_path: Path) -> None:
    raw = with_metadata(tmp_path, "wrong-tenant.ocsf.json")
    assert scan(tmp_path, WRITE_OUTPUT.format(fixture=str(raw))) is ExitCode.OUTPUT_INVALID
    assert files(tmp_path) == ["prowler.log"]


def test_an_incomplete_credential_never_starts_prowler(tmp_path: Path) -> None:
    partial = {k: v for k, v in SECRET.items() if k != "M365_CERTIFICATE_CONTENT"}
    assert scan(tmp_path, "sys.exit(0)", partial) is ExitCode.CREDENTIAL_UNAVAILABLE
    assert not (tmp_path / "output").exists() or files(tmp_path) == []
    assert not (tmp_path / "work" / "prowler.log").exists()


def test_outputs_are_write_once(tmp_path: Path) -> None:
    sink = DirectorySink(tmp_path / "output")
    sink.write("prowler.log", b"x")
    with pytest.raises(OutputExistsError):
        sink.write("prowler.log", b"y")
    with pytest.raises(ValueError, match="name"):
        sink.write("../escape", b"x")


BAD_JOBS = {
    "not json": b"{",
    "unknown key": json.dumps({**JOB, "secret": "x"}).encode(),
    "missing tenant": json.dumps({k: v for k, v in JOB.items() if k != "tenant"}).encode(),
    "empty tenant": json.dumps({**JOB, "tenant": ""}).encode(),
    "bad uuid": json.dumps({**JOB, "scan_id": "nope"}).encode(),
    "attempt zero": json.dumps({**JOB, "attempt": 0}).encode(),
    "unknown provider": json.dumps({**JOB, "provider": "aws"}).encode(),
    "excluded flag": json.dumps({**JOB, "excluded": ["--fixer"]}).encode(),
}


@pytest.mark.parametrize("name", sorted(BAD_JOBS))
def test_a_malformed_job_is_refused(name: str) -> None:
    with pytest.raises(JobError):
        load_job(BAD_JOBS[name])


def test_a_job_reads_back() -> None:
    assert load_job(json.dumps(JOB).encode()) == Job(
        organization_id=JOB["organization_id"],
        scan_id=JOB["scan_id"],
        attempt=1,
        provider="m365",
        tenant=TENANT,
        excluded=("teams_meeting_recording_disabled",),
    )


@pytest.mark.parametrize("raw", [b"", b"[]", b'{"A": 1}', b"not json"])
def test_an_unreadable_credential_is_refused_without_echoing_it(raw: bytes) -> None:
    with pytest.raises(ValueError, match="credential") as error:
        read_credential(raw)
    assert raw.decode() not in str(error.value) or not raw


def test_the_command_line_logs_ids_and_codes_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    raw = with_metadata(tmp_path)
    (tmp_path / "job.json").write_text(json.dumps(JOB))
    monkeypatch.setenv("ATESTA_SCAN_JOB", str(tmp_path / "job.json"))
    monkeypatch.setenv("ATESTA_SCAN_OUTPUT", str(tmp_path / "output"))
    monkeypatch.setenv("ATESTA_SCAN_WORK", str(tmp_path / "work"))
    fake = fake_prowler(tmp_path, WRITE_OUTPUT.format(fixture=str(raw)))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(SECRET).encode())))
    with pytest.raises(SystemExit) as exit_:
        cli.main(["scan"], executable=fake)
    assert exit_.value.code == 0
    out = capfd.readouterr().out
    assert not any(value in out for value in SECRET.values())
    events = [json.loads(line) for line in out.splitlines()]
    assert events[-1] == {
        "event": "scan.wrapper_finished",
        "scan_id": JOB["scan_id"],
        "organization_id": JOB["organization_id"],
        "attempt": 1,
        "exit_code": 0,
    }


def test_the_command_line_exits_with_the_run_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "job.json").write_text(json.dumps(JOB))
    monkeypatch.setenv("ATESTA_SCAN_JOB", str(tmp_path / "job.json"))
    monkeypatch.setenv("ATESTA_SCAN_OUTPUT", str(tmp_path / "output"))
    monkeypatch.setenv("ATESTA_SCAN_WORK", str(tmp_path / "work"))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"not a credential")))
    with pytest.raises(SystemExit) as exit_:
        cli.main(["scan"], executable=fake_prowler(tmp_path, "sys.exit(0)"))
    assert exit_.value.code == ExitCode.CREDENTIAL_UNAVAILABLE
    event = json.loads(capfd.readouterr().out.splitlines()[-1])
    assert event["exit_code"] == ExitCode.CREDENTIAL_UNAVAILABLE
