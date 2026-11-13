"""Wrapper exit codes (scanner-connectors spec). The runner adds 21 for a timeout."""

from enum import IntEnum


class ExitCode(IntEnum):
    DONE = 0
    VERIFICATION_REFUSED = 10  # permanent: the scan is blocked, never retried
    CREDENTIAL_UNAVAILABLE = 11
    VERIFICATION_TRANSIENT = 12
    PROWLER_FAILED = 20
    OUTPUT_INVALID = 30  # missing file, bad JSON, wrong tenant


def is_transient(code: ExitCode) -> bool:
    return code not in (ExitCode.DONE, ExitCode.VERIFICATION_REFUSED)


def after_prowler(returncode: int) -> ExitCode:
    """With -z, FAIL findings exit 0; anything else (1: provider init, <0: signal) failed."""
    return ExitCode.DONE if returncode == 0 else ExitCode.PROWLER_FAILED
