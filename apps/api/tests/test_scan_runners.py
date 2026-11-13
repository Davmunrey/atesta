"""Local scan output store and the fixture runner (scanner-connectors spec, local development)."""

import uuid
from pathlib import Path

import pytest
from atesta_api.modules.scanning.api import (
    FixtureRunner,
    LocalScanStore,
    OutputExistsError,
    ScanJob,
    output_prefix,
)
from atesta_core.manifest import verify_manifest

FIXTURES = Path(__file__).resolve().parents[3] / "scanner" / "fixtures" / "synthetic"
ORG = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
SCAN = uuid.UUID("dddddddd-0000-4000-8000-000000000001")


@pytest.fixture(autouse=True)
def dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATESTA_ENV", "test")


def job(provider: str = "m365", attempt: int = 1) -> ScanJob:
    return ScanJob(organization_id=ORG, scan_id=SCAN, attempt=attempt, provider=provider)


def test_output_prefix_is_the_tenant_scan_attempt_folder() -> None:
    assert output_prefix(ORG, SCAN, 2) == f"{ORG}/scans/{SCAN}/attempt-2/out/"
    with pytest.raises(ValueError, match="attempt"):
        output_prefix(ORG, SCAN, 0)


@pytest.mark.parametrize(
    ("provider", "folder"), [("m365", "m365"), ("google_workspace", "googleworkspace")]
)
def test_a_fixture_run_writes_the_output_and_its_manifest(
    tmp_path: Path, provider: str, folder: str
) -> None:
    store = LocalScanStore(tmp_path)
    assert FixtureRunner(store, FIXTURES).run(job(provider)) == 0
    prefix = f"{ORG}/scans/{SCAN}/attempt-1/out/"
    assert store.list(prefix) == [f"{prefix}manifest.json", f"{prefix}prowler.ocsf.json"]
    files = verify_manifest(
        store.read(f"{prefix}manifest.json"), lambda name: store.read(prefix + name), 10**8
    )
    assert files == {"prowler.ocsf.json": (FIXTURES / folder / "scan.ocsf.json").read_bytes()}


def test_a_failing_fixture_run_writes_nothing(tmp_path: Path) -> None:
    store = LocalScanStore(tmp_path)
    assert FixtureRunner(store, FIXTURES, exit_code=20).run(job()) == 20
    assert store.list(f"{ORG}/") == []


def test_outputs_are_write_once(tmp_path: Path) -> None:
    store = LocalScanStore(tmp_path)
    runner = FixtureRunner(store, FIXTURES)
    runner.run(job())
    with pytest.raises(OutputExistsError):
        runner.run(job())
    assert runner.run(job(attempt=2)) == 0


@pytest.mark.parametrize("key", ["../outside.json", f"{ORG}/../x", "/etc/passwd", "a//b", ""])
def test_store_keys_stay_inside_the_root(tmp_path: Path, key: str) -> None:
    store = LocalScanStore(tmp_path / "root")
    with pytest.raises(ValueError, match="key"):
        store.write(key, b"x")
    assert not (tmp_path / "outside.json").exists()


@pytest.mark.parametrize("env", [None, "prod", "staging"])
def test_local_store_and_fixture_runner_are_dev_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: str | None
) -> None:
    if env is None:
        monkeypatch.delenv("ATESTA_ENV")
    else:
        monkeypatch.setenv("ATESTA_ENV", env)
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        LocalScanStore(tmp_path)
    monkeypatch.setenv("ATESTA_ENV", "test")
    store = LocalScanStore(tmp_path)
    monkeypatch.setenv("ATESTA_ENV", env or "")
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        FixtureRunner(store, FIXTURES)
