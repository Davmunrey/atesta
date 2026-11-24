"""Incident clock milestones (notifications spec PR 2, issue 386; owner "Adelante" 2026-11-24).

A clock of up to 72 hours is notified at its start, 6 hours before it is due and when it is due.
A longer clock (a month for an NIS2 final report) at its start, 7 days and 1 day before, and when
it is due.
"""

from datetime import UTC, datetime, timedelta

from atesta_api.modules.notifications.api import ClockTiming, due_milestones, notices_due

DUE = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)


def test_a_short_clock_has_a_six_hour_warning() -> None:
    timing = ClockTiming(ref="nis2:early", due_at=DUE, hours=24)
    assert due_milestones(timing) == {"before_6h": DUE - timedelta(hours=6), "due": DUE}


def test_seventy_two_hours_is_still_short() -> None:
    timing = ClockTiming(ref="nis2:notice", due_at=DUE, hours=72)
    assert set(due_milestones(timing)) == {"before_6h", "due"}


def test_a_long_or_monthly_clock_warns_seven_days_and_one_day_ahead() -> None:
    for timing in (
        ClockTiming(ref="nis2:final", due_at=DUE, hours=None),  # months
        ClockTiming(ref="x:long", due_at=DUE, hours=96),
    ):
        assert due_milestones(timing) == {
            "before_7d": DUE - timedelta(days=7),
            "before_1d": DUE - timedelta(days=1),
            "due": DUE,
        }


def test_a_milestone_is_due_once_reached_and_within_its_grace_window() -> None:
    timing = ClockTiming(ref="nis2:early", due_at=DUE, hours=24)
    six_before = DUE - timedelta(hours=6)
    assert notices_due(timing, state="running", now=six_before - timedelta(minutes=1)) == ["start"]
    assert notices_due(timing, state="running", now=six_before) == ["start", "before_6h"]
    # A job that runs late still warns, within three hours of the milestone.
    late = six_before + timedelta(hours=2, minutes=59)
    assert notices_due(timing, state="running", now=late) == ["start", "before_6h"]
    assert notices_due(timing, state="running", now=six_before + timedelta(hours=3, minutes=1)) == [
        "start"
    ]


def test_an_overdue_clock_says_so_and_a_met_or_waiting_one_says_nothing() -> None:
    timing = ClockTiming(ref="nis2:early", due_at=DUE, hours=24)
    assert notices_due(timing, state="overdue", now=DUE + timedelta(minutes=5)) == ["due"]
    assert notices_due(timing, state="overdue", now=DUE + timedelta(days=2)) == ["due"]
    assert notices_due(timing, state="met", now=DUE - timedelta(hours=6)) == []
    assert notices_due(ClockTiming("x:w", None, 24), state="waiting", now=DUE) == []
