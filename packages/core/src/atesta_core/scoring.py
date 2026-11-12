"""Compliance scoring and regression detection. Pure functions, no I/O."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    PASS = "pass"  # noqa: S105 (status value, not a password)
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class ControlResult:
    control_id: str
    status: Status


def score(results: Iterable[ControlResult]) -> float | None:
    """Percentage (0-100, one decimal) of evaluable controls that pass.

    Only PASS and FAIL are evaluable. Returns None when nothing is evaluable,
    so the UI can show "not assessed" instead of a misleading 0 or 100.
    """
    passed = failed = 0
    for result in results:
        if result.status is Status.PASS:
            passed += 1
        elif result.status is Status.FAIL:
            failed += 1
    evaluable = passed + failed
    if evaluable == 0:
        return None
    return round(100 * passed / evaluable, 1)


def regressions(previous: Iterable[ControlResult], current: Iterable[ControlResult]) -> list[str]:
    """Control ids that passed in the previous scan and fail in the current one, sorted."""
    passed_before = {r.control_id for r in previous if r.status is Status.PASS}
    return sorted(
        r.control_id for r in current if r.status is Status.FAIL and r.control_id in passed_before
    )
