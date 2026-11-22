"""Progress over time, replayed from append-only assessments (insights spec).

Each day counts, as of its end, the latest assessment of every requirement recorded on or before
it. Days without changes carry the previous state forward. Pure: no I/O, no clock.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta


@dataclass(frozen=True)
class Assessment:
    recorded_at: datetime
    code: str
    applicability: str  # "applies" | "not_applicable"
    implementation: str  # "not_implemented" | "partially_implemented" | "implemented"


@dataclass(frozen=True)
class DayPoint:
    day: date
    assessed: int
    implemented: int
    not_applicable: int


def progress_history(rows: Iterable[Assessment], *, today: date) -> list[DayPoint]:
    ordered = sorted(rows, key=lambda r: r.recorded_at)
    if not ordered:
        return []
    latest: dict[str, Assessment] = {}
    points: list[DayPoint] = []
    day = ordered[0].recorded_at.astimezone(UTC).date()
    index = 0
    while day <= today:
        while index < len(ordered) and ordered[index].recorded_at.astimezone(UTC).date() <= day:
            latest[ordered[index].code] = ordered[index]
            index += 1
        current = latest.values()
        points.append(
            DayPoint(
                day=day,
                assessed=len(latest),
                implemented=sum(
                    1
                    for a in current
                    if a.applicability == "applies" and a.implementation == "implemented"
                ),
                not_applicable=sum(1 for a in current if a.applicability == "not_applicable"),
            )
        )
        day += timedelta(days=1)
    return points
