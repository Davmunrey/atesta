"""Calendar arithmetic for review periods (recorded-routines spec). Pure, no I/O."""

import calendar
from datetime import date


def add_months(day: date, months: int) -> date:
    """The same day `months` later, clamped to the month's last day (31 Jan + 1 = 28/29 Feb)."""
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(day.day, last))
