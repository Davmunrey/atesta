"""Progress over time, replayed from append-only assessments (insights spec)."""

from datetime import UTC, date, datetime

from atesta_core.history import Assessment, DayPoint, progress_history


def at(day: int, hour: int = 10) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def test_each_day_counts_the_latest_assessment_per_requirement() -> None:
    rows = [
        Assessment(at(1), "a", "applies", "not_implemented"),
        Assessment(at(1, 11), "b", "not_applicable", "not_implemented"),
        Assessment(at(3), "a", "applies", "implemented"),
    ]
    assert progress_history(rows, today=date(2026, 11, 4)) == [
        DayPoint(date(2026, 11, 1), assessed=2, implemented=0, not_applicable=1),
        DayPoint(date(2026, 11, 2), assessed=2, implemented=0, not_applicable=1),
        DayPoint(date(2026, 11, 3), assessed=2, implemented=1, not_applicable=1),
        DayPoint(date(2026, 11, 4), assessed=2, implemented=1, not_applicable=1),
    ]


def test_a_later_same_day_assessment_replaces_the_earlier_one() -> None:
    rows = [
        Assessment(at(1, 9), "a", "applies", "implemented"),
        Assessment(at(1, 17), "a", "not_applicable", "not_implemented"),
    ]
    point = progress_history(rows, today=date(2026, 11, 1))[0]
    assert (point.assessed, point.implemented, point.not_applicable) == (1, 0, 1)


def test_order_of_input_does_not_matter_and_no_rows_means_no_points() -> None:
    rows = [
        Assessment(at(2), "a", "applies", "implemented"),
        Assessment(at(1), "a", "applies", "not_implemented"),
    ]
    assert progress_history(rows, today=date(2026, 11, 2))[-1].implemented == 1
    assert progress_history([], today=date(2026, 11, 2)) == []


def test_partial_implementation_is_assessed_but_not_implemented() -> None:
    rows = [Assessment(at(1), "a", "applies", "partially_implemented")]
    point = progress_history(rows, today=date(2026, 11, 1))[0]
    assert (point.assessed, point.implemented) == (1, 0)
