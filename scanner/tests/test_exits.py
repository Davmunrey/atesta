"""Wrapper exit codes (scanner-connectors spec): the run_scan job maps them to scan status."""

import pytest
from atesta_scanner.exits import ExitCode, after_prowler, is_transient


def test_codes_are_the_specs() -> None:
    assert {c.name: c.value for c in ExitCode} == {
        "DONE": 0,
        "VERIFICATION_REFUSED": 10,
        "CREDENTIAL_UNAVAILABLE": 11,
        "VERIFICATION_TRANSIENT": 12,
        "PROWLER_FAILED": 20,
        "OUTPUT_INVALID": 30,
    }


def test_only_a_refused_verification_is_permanent() -> None:
    assert [c for c in ExitCode if c is not ExitCode.DONE and not is_transient(c)] == [
        ExitCode.VERIFICATION_REFUSED
    ]
    assert not is_transient(ExitCode.DONE)


@pytest.mark.parametrize(
    ("returncode", "code"),
    [
        (0, ExitCode.DONE),
        (1, ExitCode.PROWLER_FAILED),
        (3, ExitCode.PROWLER_FAILED),
        (-9, ExitCode.PROWLER_FAILED),
    ],
)
def test_prowler_exit(returncode: int, code: ExitCode) -> None:
    # -z makes FAIL findings exit 0; 1 is a provider init failure; negative is a signal.
    assert after_prowler(returncode) is code
