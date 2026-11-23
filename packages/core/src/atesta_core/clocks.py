"""Reporting clocks of an incident (recorded-routines spec). Pure, no I/O.

The rules are framework-pack content (rule 9): a duration in hours or months, starting when the
organization became aware of the incident or when another clock was met, and the flag that makes
the clock apply. Atesta only computes due times; whether a notification is required is the
organization's decision (ADR-005).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from atesta_core.dates import add_months

type Flag = Literal["significant", "personal_data"]
type ClockStatus = Literal["met", "running", "overdue", "waiting"]


@dataclass(frozen=True, slots=True)
class ClockRule:
    ref: str
    hours: int | None
    months: int | None
    after: str | None  # ref of the clock it starts from; None means from awareness
    needs: Flag


@dataclass(frozen=True, slots=True)
class ClockState:
    ref: str
    state: ClockStatus
    due_at: datetime | None
    met_at: datetime | None
    late: bool


def _due(start: datetime, rule: ClockRule) -> datetime:
    if rule.months is not None:
        day = add_months(start.date(), rule.months)
        return start.replace(year=day.year, month=day.month, day=day.day)
    return start + timedelta(hours=rule.hours or 0)


def clock_states(
    rules: Iterable[ClockRule],
    *,
    aware_at: datetime,
    significant: bool,
    personal_data: bool,
    met: Mapping[str, datetime],
    now: datetime,
) -> list[ClockState]:
    flags = {"significant": significant, "personal_data": personal_data}
    applicable = [r for r in rules if flags[r.needs]]
    refs = {r.ref for r in applicable}
    out: list[ClockState] = []
    for rule in applicable:
        start = (
            aware_at
            if rule.after is None
            else (met.get(rule.after) if rule.after in refs else None)
        )
        due = None if start is None else _due(start, rule)
        met_at = met.get(rule.ref)
        if met_at is not None:
            state: ClockStatus = "met"
        elif due is None:
            state = "waiting"
        else:
            state = "overdue" if now > due else "running"
        late = met_at is not None and due is not None and met_at > due
        out.append(ClockState(rule.ref, state, due, met_at, late))
    return out
