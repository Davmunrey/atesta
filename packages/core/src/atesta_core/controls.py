"""Control results from check results (scanner-connectors spec, Findings to controls; ADR-005).

A check is in scope when some connection reported a result for it: every scan stores one result
per check of its provider, so this is "a check of a provider with a connection". A control gets:

- `fail` if any in-scope check fails, on any connection;
- no result if any in-scope check was not evaluated, or none is in scope (never `pass`);
- `manual` if any in-scope check is manual;
- `pass` if every in-scope check passes.

Controls without a result count as manual at requirement level (atesta_core.frameworks).
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping

from atesta_core.scoring import ControlResult, Status

type CheckKey = tuple[str, str]  # (engine, check_id)

_CHECK_STATUSES = frozenset({"pass", "fail", "manual", "not_evaluated"})


def control_status(statuses: Iterable[str]) -> Status | None:
    seen = set(statuses)
    if not seen <= _CHECK_STATUSES:
        raise ValueError("unknown check status")
    if "fail" in seen:
        return Status.FAIL
    if not seen or "not_evaluated" in seen:
        return None
    return Status.MANUAL if "manual" in seen else Status.PASS


def control_results(
    control_checks: Mapping[str, Iterable[CheckKey]],
    check_results: Iterable[tuple[str, str, str]],
) -> list[ControlResult]:
    """One result per control with checks in scope, sorted by control key."""
    by_check: dict[CheckKey, list[str]] = defaultdict(list)
    for engine, check_id, status in check_results:
        by_check[(engine, check_id)].append(status)
    results = []
    for control_key in sorted(control_checks):
        statuses = [s for check in control_checks[control_key] for s in by_check.get(check, [])]
        result = control_status(statuses)
        if result is not None:
            results.append(ControlResult(control_key, result))
    return results
