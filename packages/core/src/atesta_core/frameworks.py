"""Framework-agnostic scoring (ADR-011).

Checks produce results for common controls. Each framework pack maps its requirements to those
controls (many-to-many). One set of control results scores every selected framework.
"""

from collections import defaultdict
from collections.abc import Iterable
from collections.abc import Mapping as Mapping_
from dataclasses import dataclass

from atesta_core.scoring import ControlResult, Status, score


@dataclass(frozen=True, slots=True)
class Mapping:
    framework: str
    requirement_id: str
    control_id: str


def requirement_status(control_statuses: Iterable[Status]) -> Status:
    """Status of one requirement from the statuses of the controls mapped to it.

    - No mapped controls: MANUAL (evidence must come from documents or a human).
    - Any FAIL: FAIL.
    - Any MANUAL (no FAIL): MANUAL.
    - All NOT_APPLICABLE: NOT_APPLICABLE.
    - Otherwise: PASS.
    """
    statuses = list(control_statuses)
    if not statuses:
        return Status.MANUAL
    if Status.FAIL in statuses:
        return Status.FAIL
    if Status.MANUAL in statuses:
        return Status.MANUAL
    if all(s is Status.NOT_APPLICABLE for s in statuses):
        return Status.NOT_APPLICABLE
    return Status.PASS


def framework_results(
    framework: str,
    requirement_ids: Iterable[str],
    mappings: Iterable[Mapping],
    control_results: Iterable[ControlResult],
) -> list[ControlResult]:
    """Requirement-level results for one framework. Controls without a result count as MANUAL."""
    by_control = {r.control_id: r.status for r in control_results}
    controls_for: dict[str, list[str]] = defaultdict(list)
    for m in mappings:
        if m.framework == framework:
            controls_for[m.requirement_id].append(m.control_id)
    return [
        ControlResult(
            req_id,
            requirement_status(by_control.get(c, Status.MANUAL) for c in controls_for[req_id]),
        )
        for req_id in sorted(set(requirement_ids))
    ]


def framework_score(
    framework: str,
    requirement_ids: Iterable[str],
    mappings: Iterable[Mapping],
    control_results: Iterable[ControlResult],
) -> float | None:
    """Score (0-100) of one framework from shared control results."""
    return score(framework_results(framework, requirement_ids, mappings, control_results))


def _group_values(value: object) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list) and value and all(isinstance(v, str) and v for v in value):
        return list(dict.fromkeys(value))  # a repeated value counts once
    raise ValueError(f"grouping attribute must be a string or a list of strings: {value!r}")


def group_scores(
    results: Iterable[ControlResult],
    attributes: Mapping_[str, Mapping_[str, object]],
    keys: Iterable[str],
) -> dict[str, dict[str, float | None]]:
    """Score per value of each grouping attribute (FR-08), e.g. one score per dimension.

    `attributes` maps requirement id to its attributes; `keys` are the attribute names a pack
    declares as score groups. Requirements without the attribute are left out of that group. A
    requirement whose attribute lists several values (a measure that applies to several
    dimensions) counts once in each of them. Any other value type raises: snapshots are
    append-only, so a wrong bucket would be permanent.
    """
    if isinstance(keys, str):
        raise ValueError("score group keys must be a list of strings")
    keys = list(keys)
    if not all(isinstance(k, str) for k in keys):
        raise ValueError("score group keys must be a list of strings")
    results = list(results)
    out: dict[str, dict[str, float | None]] = {}
    for key in keys:
        buckets: dict[str, list[ControlResult]] = defaultdict(list)
        for result in results:
            value = attributes.get(result.control_id, {}).get(key)
            if value is not None:
                for group in _group_values(value):
                    buckets[group].append(result)
        out[key] = {value: score(rs) for value, rs in sorted(buckets.items())}
    return out
