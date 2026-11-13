"""Scan coverage (scanner-connectors spec, Coverage; ADR-005).

Every listed check gets exactly one result. A check with findings is `fail` if any unmuted
finding fails, else `pass` if any passes, else `manual`. A check with no finding is
`not_evaluated` (`no_findings`), never `pass`. Excluded checks are not expected: they are
`not_evaluated` with their reason, and a finding for one rejects the scan like any check the
image should not run. Counts include muted findings; only the status ignores a muted FAIL.
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from atesta_core.ocsf import OcsfFinding

EXCLUSION_REASONS = frozenset({"excluded", "not_granted"})


class UnexpectedCheckError(ValueError):
    """The output holds a check the expected list does not: the image and the list disagree."""


@dataclass(frozen=True, slots=True)
class CheckResult:
    check_id: str
    status: str
    reason: str | None
    pass_count: int
    fail_count: int
    manual_count: int

    @property
    def expected(self) -> bool:
        return self.reason not in EXCLUSION_REASONS

    @property
    def evaluated(self) -> bool:
        return self.status != "not_evaluated"


def service_of(check_id: str) -> str:
    """Prowler 5.49.0 lib/check/models.py: ServiceName equals CheckID.split("_")[0]."""
    return check_id.split("_", 1)[0]


def _expected(listed: Iterable[str], excluded: Mapping[str, str]) -> set[str]:
    checks: set[str] = set()
    for check_id in listed:
        if check_id in checks:
            raise ValueError(f"{check_id} is listed twice")
        checks.add(check_id)
    for check_id, reason in excluded.items():
        if check_id not in checks:
            raise ValueError(f"excluded check {check_id} is not listed")
        if reason not in EXCLUSION_REASONS:
            raise ValueError(f"excluded check {check_id} has an unknown reason")
    return checks - excluded.keys()


def _status(counts: Counter[str], unmuted_fail: bool) -> str:
    if unmuted_fail:
        return "fail"
    return "pass" if counts["pass"] else "manual"


def coverage(
    findings: Sequence[OcsfFinding], listed: Iterable[str], excluded: Mapping[str, str]
) -> list[CheckResult]:
    expected = _expected(listed, excluded)
    counts: dict[str, Counter[str]] = {}
    failing: set[str] = set()
    for index, finding in enumerate(findings):
        if finding.check_id not in expected:
            raise UnexpectedCheckError(f"finding {index}: check is not expected")
        counts.setdefault(finding.check_id, Counter())[finding.status] += 1
        if finding.status == "fail" and not finding.muted:
            failing.add(finding.check_id)
    results = [
        CheckResult(check_id, "not_evaluated", reason, 0, 0, 0)
        for check_id, reason in excluded.items()
    ]
    for check_id in expected:
        seen = counts.get(check_id)
        if seen is None:
            results.append(CheckResult(check_id, "not_evaluated", "no_findings", 0, 0, 0))
            continue
        status = _status(seen, check_id in failing)
        results.append(
            CheckResult(check_id, status, None, seen["pass"], seen["fail"], seen["manual"])
        )
    return sorted(results, key=lambda r: r.check_id)


def silent_services(results: Iterable[CheckResult]) -> list[str]:
    """Services with expected checks and not one finding: a cold start or a failed connect."""
    expected: set[str] = set()
    heard: set[str] = set()
    for result in results:
        if result.expected:
            expected.add(service_of(result.check_id))
            if result.evaluated:
                heard.add(service_of(result.check_id))
    return sorted(expected - heard)
