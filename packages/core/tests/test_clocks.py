from datetime import UTC, datetime, timedelta

from atesta_core.clocks import ClockRule, clock_states

AWARE = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)
EARLY = ClockRule(ref="nis2:early_warning", hours=24, months=None, after=None, needs="significant")
NOTICE = ClockRule(ref="nis2:notification", hours=72, months=None, after=None, needs="significant")
FINAL = ClockRule(
    ref="nis2:final_report", hours=None, months=1, after="nis2:notification", needs="significant"
)
BREACH = ClockRule(ref="gdpr:breach", hours=72, months=None, after=None, needs="personal_data")
RULES = [EARLY, NOTICE, FINAL, BREACH]


def _states(now: datetime, met: dict[str, datetime], **flags: bool) -> dict[str, object]:
    found = clock_states(
        RULES,
        aware_at=AWARE,
        significant=flags.get("significant", False),
        personal_data=flags.get("personal_data", False),
        met=met,
        now=now,
    )
    return {s.ref: s for s in found}


def test_only_clocks_whose_flag_is_set_apply() -> None:
    assert list(_states(AWARE, {}, personal_data=True)) == ["gdpr:breach"]
    assert list(_states(AWARE, {}, significant=True)) == [
        "nis2:early_warning",
        "nis2:notification",
        "nis2:final_report",
    ]
    assert _states(AWARE, {}) == {}


def test_running_overdue_and_waiting() -> None:
    states = _states(AWARE + timedelta(hours=30), {}, significant=True)
    early, notice, final = (
        states[r] for r in ("nis2:early_warning", "nis2:notification", "nis2:final_report")
    )
    assert (early.state, early.due_at) == ("overdue", AWARE + timedelta(hours=24))
    assert (notice.state, notice.due_at) == ("running", AWARE + timedelta(hours=72))
    assert (final.state, final.due_at) == ("waiting", None)


def test_a_clock_starts_when_the_clock_it_follows_is_met() -> None:
    sent = datetime(2026, 11, 22, 8, 0, tzinfo=UTC)
    states = _states(sent, {"nis2:notification": sent}, significant=True)
    assert (states["nis2:notification"].state, states["nis2:notification"].late) == ("met", False)
    assert states["nis2:final_report"].state == "running"
    assert states["nis2:final_report"].due_at == datetime(2026, 12, 22, 8, 0, tzinfo=UTC)


def test_months_clamp_to_the_last_day() -> None:
    sent = datetime(2027, 1, 31, 12, 0, tzinfo=UTC)
    states = _states(sent, {"nis2:notification": sent}, significant=True)
    assert states["nis2:final_report"].due_at == datetime(2027, 2, 28, 12, 0, tzinfo=UTC)


def test_a_clock_met_after_its_due_time_is_late() -> None:
    late = AWARE + timedelta(hours=80)
    state = _states(late, {"gdpr:breach": late}, personal_data=True)["gdpr:breach"]
    assert (state.state, state.met_at, state.late) == ("met", late, True)


def test_met_times_for_clocks_that_do_not_apply_are_ignored() -> None:
    assert _states(AWARE, {"gdpr:breach": AWARE}, significant=True).get("gdpr:breach") is None
