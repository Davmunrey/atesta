"""The Madrid calendar day of the manual scan budget (#265, scanner-connectors spec)."""

from datetime import UTC, datetime

import pytest
from atesta_api.modules.scanning.api import MANUAL_SCANS_PER_DAY, madrid_day


def at(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)  # type: ignore[misc]


def test_the_budget_is_the_owners_six_manual_scans_a_day() -> None:
    assert MANUAL_SCANS_PER_DAY == 6  # owner, 2026-11-23


@pytest.mark.parametrize(
    ("now", "start", "end"),
    [
        # Winter (CET, UTC+1): the day runs 23:00 to 23:00 UTC.
        (at(2026, 1, 15, 12), at(2026, 1, 14, 23), at(2026, 1, 15, 23)),
        # 23:30 UTC on 15 January is already 16 January in Madrid.
        (at(2026, 1, 15, 23, 30), at(2026, 1, 15, 23), at(2026, 1, 16, 23)),
        # Summer (CEST, UTC+2).
        (at(2026, 7, 1, 21, 59), at(2026, 6, 30, 22), at(2026, 7, 1, 22)),
        # Clocks go forward on 29 March 2026: a 23-hour day.
        (at(2026, 3, 29, 12), at(2026, 3, 28, 23), at(2026, 3, 29, 22)),
        # Clocks go back on 25 October 2026: a 25-hour day.
        (at(2026, 10, 25, 12), at(2026, 10, 24, 22), at(2026, 10, 25, 23)),
    ],
)
def test_the_day_follows_the_madrid_calendar(now: datetime, start: datetime, end: datetime) -> None:
    assert madrid_day(now) == (start, end)


def test_a_naive_time_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone"):
        madrid_day(datetime(2026, 1, 15, 12))  # noqa: DTZ001 - the case under test
