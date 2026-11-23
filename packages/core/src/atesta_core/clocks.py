"""Reporting clocks of an incident (recorded-routines spec). Pure, no I/O.

The rules are framework-pack content (rule 9): a duration in hours or months, starting when the
organization became aware of the incident, when it classified the incident as significant, or
when another clock was met, and the flag that makes the clock apply. A clock that starts at
classification may carry an outer limit in hours from awareness: it is due at the earlier of the
two times, and the limit lapses when the classification comes after it (#224). Atesta only
computes due times; whether a notification is required is the organization's decision (ADR-005).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from atesta_core.dates import add_months

type Flag = Literal["significant", "personal_data"]
type ClockStatus = Literal["met", "running", "overdue", "waiting"]
type ClockStart = Literal["aware", "classified"]


@dataclass(frozen=True, slots=True)
class ClockRule:
    ref: str
    hours: int | None
    months: int | None
    after: str | None  # ref of the clock it starts from; None means from `starts`
    needs: Flag
    starts: ClockStart = "aware"
    outer_limit_hours: int | None = None  # from awareness; only with starts="classified"


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


def _classified_due(
    rule: ClockRule, aware_at: datetime, classified_at: datetime | None
) -> datetime | None:
    limit = (
        None
        if rule.outer_limit_hours is None
        else aware_at + timedelta(hours=rule.outer_limit_hours)
    )
    if classified_at is None:
        return limit  # classification time not recorded: only the outer limit runs
    due = _due(classified_at, rule)
    return min(due, limit) if limit is not None and classified_at <= limit else due


def clock_states(
    rules: Iterable[ClockRule],
    *,
    aware_at: datetime,
    significant: bool,
    personal_data: bool,
    met: Mapping[str, datetime],
    now: datetime,
    classified_at: datetime | None = None,
) -> list[ClockState]:
    flags = {"significant": significant, "personal_data": personal_data}
    applicable = [r for r in rules if flags[r.needs]]
    refs = {r.ref for r in applicable}
    out: list[ClockState] = []
    for rule in applicable:
        if rule.after is None and rule.starts == "classified":
            due = _classified_due(rule, aware_at, classified_at)
        else:
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
