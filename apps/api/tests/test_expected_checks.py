"""Committed expected check lists (scanner-connectors spec, Image and Coverage)."""

import json
from pathlib import Path

import pytest
import yaml
from atesta_api.modules.scanning.api import ENGINE_VERSION, expected_checks

REPO = Path(__file__).resolve().parents[3]
EXPECTED = REPO / "scanner" / "expected"
FIXTURES = REPO / "scanner" / "fixtures" / "synthetic"
CATALOG = Path(__file__).resolve().parent / "fixtures" / "catalog" / "synthetic.yaml"
FOLDER = {"m365": "m365", "google_workspace": "googleworkspace"}


@pytest.mark.parametrize(("provider", "count"), [("m365", 149), ("google_workspace", 65)])
def test_the_lists_are_the_pinned_engine_output(provider: str, count: int) -> None:
    # `prowler <provider> --list-checks-json` from the 5.49.0 wheel (sha256 e5ed983e...705).
    checks = expected_checks(EXPECTED, provider)
    assert ENGINE_VERSION == "5.49.0"
    assert len(checks) == count
    assert checks == sorted(set(checks))


@pytest.mark.parametrize("provider", ["m365", "google_workspace"])
def test_synthetic_fixtures_use_listed_checks_only(provider: str) -> None:
    listed = set(expected_checks(EXPECTED, provider))
    for path in sorted((FIXTURES / FOLDER[provider]).glob("*.ocsf.json")):
        findings = json.loads(path.read_bytes())
        if path.name == "unexpected-check.ocsf.json":
            findings = findings[:-1]  # the last finding is the deliberate unknown check
        assert {f["metadata"]["event_code"] for f in findings} <= listed, path.name


def test_synthetic_catalog_checks_are_listed() -> None:
    listed = {c for p in FOLDER for c in expected_checks(EXPECTED, p)}
    controls = yaml.safe_load(CATALOG.read_text())["controls"]
    assert {c for checks in controls.values() for c in checks} <= listed


BAD = {
    "not json": b"{",
    "other provider": b'{"azure": ["entra_x"]}',
    "extra provider": b'{"m365": ["entra_x"], "azure": ["entra_y"]}',
    "not a list": b'{"m365": "entra_x"}',
    "duplicate": b'{"m365": ["entra_x", "entra_x"]}',
    "unsafe id": b'{"m365": ["../x"]}',
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_a_malformed_list_is_refused(tmp_path: Path, name: str) -> None:
    (tmp_path / ENGINE_VERSION).mkdir()
    (tmp_path / ENGINE_VERSION / "m365.json").write_bytes(BAD[name])
    with pytest.raises(ValueError, match="expected check list"):
        expected_checks(tmp_path, "m365")


def test_an_unknown_provider_is_refused() -> None:
    with pytest.raises(ValueError, match="provider"):
        expected_checks(EXPECTED, "aws")
