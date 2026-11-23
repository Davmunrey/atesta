from datetime import date

import pytest
from atesta_core.dates import add_months


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 1, 15), 12, date(2027, 1, 15)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 11, 30), 3, date(2027, 2, 28)),
        (date(2026, 12, 1), 1, date(2027, 1, 1)),
        (date(2026, 3, 31), -1, date(2026, 2, 28)),
    ],
)
def test_add_months_clamps_to_the_last_day(start: date, months: int, expected: date) -> None:
    assert add_months(start, months) == expected
