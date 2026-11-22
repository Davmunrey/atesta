"""Applicability proposals from a pack's selection rules (requirement-register spec).

A pack states, per requirement, a `selection_basis` of the form `<axis> · <keys>` and a list of
`selection_rules` ({level, rule}). `<keys>` is `Todas` when the axis takes one value for the whole
organization (a category), or the dimensions whose levels decide it (`nivel · C I T A`).
The organization's scope gives one value per single-valued axis and one level per dimension.

A proposal is never a decision: a person confirms or overrides it, with a justification.
Nothing here names a framework (rule 9).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

type Decision = Literal["applies", "not_applicable", "undecided"]
NOT_APPLICABLE = "n.a."
ALL_KEYS = "Todas"
_SEPARATOR = "·"


@dataclass(frozen=True)
class Proposal:
    decision: Decision
    rule: str | None  # the pack's rule text, verbatim (for example "+ R1+R2")
    level: str | None  # the scope level the rule was read at


_UNDECIDED = Proposal("undecided", None, None)


def parse_basis(basis: str | None) -> tuple[str, list[str]] | None:
    """The axis and its keys, or None when the basis is not `<axis> · <keys>`."""
    if not basis or _SEPARATOR not in basis:
        return None
    axis, _, keys = (part.strip() for part in basis.partition(_SEPARATOR))
    if not axis or not keys:
        return None
    return axis, [] if keys == ALL_KEYS else keys.split()


def _levels(rules: Iterable[Mapping[str, Any]]) -> list[str]:
    return [str(rule["level"]) for rule in rules]


def propose(
    basis: str | None, rules: list[Mapping[str, Any]], scope: Mapping[str, Any]
) -> Proposal:
    """What the pack's rules propose for this requirement under the organization's scope."""
    parsed = parse_basis(basis)
    if parsed is None:
        return _UNDECIDED
    axis, keys = parsed
    value = scope.get(axis)
    order = _levels(rules)
    if not keys:
        level = value if isinstance(value, str) else None
    else:
        if not isinstance(value, Mapping) or any(key not in value for key in keys):
            return _UNDECIDED
        listed = [value[key] for key in keys]
        if any(item not in order for item in listed):
            return _UNDECIDED
        level = max(listed, key=order.index)  # the highest listed dimension decides
    rule = next((str(r["rule"]) for r in rules if r["level"] == level), None)
    if level is None or rule is None:
        return _UNDECIDED
    decision: Decision = "not_applicable" if rule.strip() == NOT_APPLICABLE else "applies"
    return Proposal(decision, rule, level)


def axis_levels(requirements: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, list[str]]]:
    """Every axis a pack uses, with its dimension keys (sorted) and levels (in rule order)."""
    axes: dict[str, dict[str, list[str]]] = {}
    for requirement in requirements:
        parsed = parse_basis(requirement.get("selection_basis"))
        if parsed is None:
            continue
        axis, keys = parsed
        entry = axes.setdefault(axis, {"keys": [], "levels": []})
        entry["keys"] = sorted(set(entry["keys"]) | set(keys))
        for level in _levels(requirement.get("selection_rules", [])):
            if level not in entry["levels"]:
                entry["levels"].append(level)
    return axes


def valid_scope(scope: Mapping[str, Any], axes: Mapping[str, Mapping[str, list[str]]]) -> bool:
    """Whether every value in the scope is a level the pack declares for that axis or key."""
    for axis, value in scope.items():
        if axis not in axes:
            return False
        levels, keys = axes[axis]["levels"], axes[axis]["keys"]
        if not keys:
            if not isinstance(value, str) or value not in levels:
                return False
        elif not isinstance(value, Mapping) or any(
            key not in keys or level not in levels for key, level in value.items()
        ):
            return False
    return True
