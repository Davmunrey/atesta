"""Portfolio summary of one organization, and the order of a portfolio.

Counts only, never a compliance score (ADR-005). Pure: the API reads each organization in its
own tenant context and passes the numbers here (consultancy-portfolio spec, issue 228).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class FrameworkCounts:
    """What the summary needs from one framework's readiness."""

    total: int
    assessed: int
    overdue: int
    last_assessed_at: datetime | None


@dataclass(frozen=True, slots=True)
class Summary:
    frameworks_in_progress: int
    assessed: int  # over the frameworks in progress
    total: int  # over the frameworks in progress
    overdue: int  # overdue measures, over every framework
    pending: int  # routines waiting
    pending_overdue: int  # of those, the overdue ones
    last_assessed_at: datetime | None


def summarize(frameworks: Iterable[FrameworkCounts], routines_overdue: Sequence[bool]) -> Summary:
    """`routines_overdue` holds one entry per pending routine: whether it is overdue.

    Totals count only the frameworks in progress: an untouched framework would inflate them.
    """
    every = list(frameworks)
    started = [f for f in every if f.assessed > 0]
    return Summary(
        frameworks_in_progress=len(started),
        assessed=sum(f.assessed for f in started),
        total=sum(f.total for f in started),
        overdue=sum(f.overdue for f in every),
        pending=len(routines_overdue),
        pending_overdue=sum(1 for overdue in routines_overdue if overdue),
        last_assessed_at=max(
            (f.last_assessed_at for f in every if f.last_assessed_at is not None), default=None
        ),
    )


def urgency(name: str, summary: Summary | None) -> tuple[int, int, int, str]:
    """Sort key, most urgent first: overdue measures and routines, then pending routines, then
    the name. An organization that could not be read has nothing to rank and goes last."""
    if summary is None:
        return (1, 0, 0, name.casefold())
    return (0, -(summary.overdue + summary.pending_overdue), -summary.pending, name.casefold())
