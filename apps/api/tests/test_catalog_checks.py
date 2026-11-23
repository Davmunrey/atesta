"""Where the pinned scanner checks sit in the common controls (ADR-005, ADR-011).

A check stored `not_evaluated` keeps its control from passing (`atesta_core.controls`). So a
control must not list a check the scanner never runs.
"""

from functools import cache
from pathlib import Path

import pytest
from atesta_api.modules.compliance.catalog import read_catalog
from atesta_api.modules.compliance.catalog_schema import ControlContent
from atesta_api.modules.scanning.api import exclusions, expected_checks, powershell_checks

ROOT = Path(__file__).resolve().parents[3]
EXPECTED = ROOT / "scanner" / "expected"
PROVIDERS = ("m365", "google_workspace")


@cache
def listed() -> set[str]:
    return {c for provider in PROVIDERS for c in expected_checks(EXPECTED, provider)}


@cache
def waiting() -> set[str]:
    """PowerShell-backed checks: not granted today, expected once the permission lands."""
    return set(powershell_checks(EXPECTED))


@cache
def never_run() -> set[str]:
    excluded = {c for provider in PROVIDERS for c in exclusions(EXPECTED, provider)}
    return excluded - waiting()


@cache
def controls() -> list[ControlContent]:
    catalog = read_catalog(ROOT / "catalog", expected_checks=listed(), engine_version="5.49.0")
    return list(catalog.controls.values())


def test_the_pinned_lists_split_as_the_spec_says() -> None:
    assert len(listed()) == 214
    assert len(waiting()) == 54
    assert len(never_run()) == 8  # D3 (3) and D6 (5)


@pytest.mark.parametrize("control", controls(), ids=lambda c: c.id)
def test_no_control_lists_a_check_the_scanner_never_runs(control: ControlContent) -> None:
    assert sorted(set(control.prowler_checks) & never_run()) == []
