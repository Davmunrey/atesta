"""Portfolio summary (consultancy-portfolio spec, issue 228): counts only, most urgent first."""

from datetime import UTC, datetime

from atesta_core.portfolio import FrameworkCounts, Summary, summarize, urgency

EARLY = datetime(2026, 11, 1, tzinfo=UTC)
LATE = datetime(2026, 11, 20, tzinfo=UTC)


def test_totals_count_only_the_frameworks_in_progress() -> None:
    frameworks = [
        FrameworkCounts(total=73, assessed=10, overdue=3, last_assessed_at=EARLY),
        FrameworkCounts(total=23, assessed=2, overdue=0, last_assessed_at=LATE),
        # Untouched: its 162 measures would inflate the total, but its overdue ones still count.
        FrameworkCounts(total=162, assessed=0, overdue=1, last_assessed_at=None),
    ]
    assert summarize(frameworks, routines_overdue=[True, False, False]) == Summary(
        frameworks_in_progress=2,
        assessed=12,
        total=96,
        overdue=4,
        pending=3,
        pending_overdue=1,
        last_assessed_at=LATE,
    )


def test_an_organization_with_nothing_recorded_has_an_empty_summary() -> None:
    assert summarize([], routines_overdue=[]) == Summary(0, 0, 0, 0, 0, 0, None)


def _summary(overdue: int = 0, pending: int = 0, pending_overdue: int = 0) -> Summary:
    return Summary(0, 0, 0, overdue, pending, pending_overdue, None)


def test_most_urgent_first_then_pending_then_name_and_unread_rows_last() -> None:
    rows = [
        ("Calma", _summary()),
        ("beta", _summary(pending=2)),
        ("Alfa", _summary(pending=2)),
        ("Rutinas", _summary(pending=1, pending_overdue=1)),
        ("Medidas", _summary(overdue=2)),
        ("Sin leer", None),
    ]
    ordered = sorted(rows, key=lambda row: urgency(row[0], row[1]))
    assert [name for name, _ in ordered] == [
        "Medidas",  # two overdue measures
        "Rutinas",  # one overdue routine
        "Alfa",  # nothing overdue, two pending; before "beta" whatever the case
        "beta",
        "Calma",
        "Sin leer",  # an organization that could not be read has nothing to rank
    ]
