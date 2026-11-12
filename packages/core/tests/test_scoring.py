from atesta_core.scoring import ControlResult, Status, regressions, score


def r(control_id: str, status: Status) -> ControlResult:
    return ControlResult(control_id, status)


def test_score_ignores_not_applicable_and_manual() -> None:
    results = [
        r("op.acc.1", Status.PASS),
        r("op.acc.2", Status.FAIL),
        r("op.exp.1", Status.NOT_APPLICABLE),
        r("org.1", Status.MANUAL),
    ]
    assert score(results) == 50.0


def test_score_none_when_nothing_evaluable() -> None:
    assert score([r("org.1", Status.MANUAL)]) is None
    assert score([]) is None


def test_score_rounds_to_one_decimal() -> None:
    results = [r("a", Status.PASS), r("b", Status.PASS), r("c", Status.FAIL)]
    assert score(results) == 66.7


def test_regressions_only_pass_to_fail() -> None:
    previous = [r("a", Status.PASS), r("b", Status.FAIL), r("c", Status.PASS)]
    current = [r("a", Status.FAIL), r("b", Status.FAIL), r("c", Status.PASS), r("d", Status.FAIL)]
    assert regressions(previous, current) == ["a"]
