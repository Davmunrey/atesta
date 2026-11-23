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


# --- classification (#224): Delegated Regulation (EU) 2025/301, Art. 5(1)(a) and 5(2) ------

INITIAL = ClockRule(
    ref="dora:initial_notification",
    hours=4,
    months=None,
    after=None,
    needs="significant",
    starts="classified",
    outer_limit_hours=24,
)
INTERMEDIATE = ClockRule(
    ref="dora:intermediate_report",
    hours=72,
    months=None,
    after="dora:initial_notification",
    needs="significant",
)


def _initial(classified_at: datetime | None, now: datetime | None = None) -> object:
    found = clock_states(
        [INITIAL, INTERMEDIATE],
        aware_at=AWARE,
        significant=True,
        personal_data=False,
        met={},
        now=now or AWARE,
        classified_at=classified_at,
    )
    return found[0]


def test_the_clock_runs_four_hours_from_classification() -> None:
    state = _initial(AWARE + timedelta(hours=2))
    assert (state.state, state.due_at) == ("running", AWARE + timedelta(hours=6))


def test_the_outer_limit_from_awareness_caps_it() -> None:
    state = _initial(AWARE + timedelta(hours=22))
    assert state.due_at == AWARE + timedelta(hours=24)


def test_a_classification_after_the_outer_limit_runs_from_classification_alone() -> None:
    state = _initial(AWARE + timedelta(hours=30), now=AWARE + timedelta(hours=31))
    assert (state.state, state.due_at) == ("running", AWARE + timedelta(hours=34))


def test_without_a_classification_time_only_the_outer_limit_runs() -> None:
    state = _initial(None, now=AWARE + timedelta(hours=25))
    assert (state.state, state.due_at) == ("overdue", AWARE + timedelta(hours=24))


def test_a_classified_clock_without_outer_limit_waits_for_the_classification() -> None:
    rule = ClockRule(
        ref="x:after_classification",
        hours=4,
        months=None,
        after=None,
        needs="significant",
        starts="classified",
    )
    [state] = clock_states(
        [rule], aware_at=AWARE, significant=True, personal_data=False, met={}, now=AWARE
    )
    assert (state.state, state.due_at) == ("waiting", None)
