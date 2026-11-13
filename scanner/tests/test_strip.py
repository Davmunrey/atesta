"""Resource dumps never leave the container (scanner-connectors spec, D10)."""

import json
from pathlib import Path

import pytest
from atesta_scanner.strip import OutputInvalidError, strip_metadata

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic" / "m365" / "scan.ocsf.json"


def with_metadata() -> list[dict[str, object]]:
    findings = json.loads(FIXTURE.read_bytes())
    for finding in findings:
        for resource in finding["resources"]:
            resource["data"] = {"details": "kept", "metadata": {"userPrincipalName": "a@x.io"}}
    return findings


def test_resource_metadata_is_removed_and_nothing_else() -> None:
    findings = with_metadata()
    stripped = json.loads(strip_metadata(json.dumps(findings).encode()))
    for finding in findings:
        for resource in finding["resources"]:
            del resource["data"]["metadata"]
    assert stripped == findings


def test_findings_without_data_pass_unchanged() -> None:
    raw = FIXTURE.read_bytes()
    assert json.loads(strip_metadata(raw)) == json.loads(raw)


@pytest.mark.parametrize(
    "raw",
    [b"{", b"{}", b'[{"resources": "x"}]', b"[1]", b'[{"resources": [{"data": []}]}]'],
)
def test_output_that_is_not_an_ocsf_array_is_invalid(raw: bytes) -> None:
    with pytest.raises(OutputInvalidError):
        strip_metadata(raw)
