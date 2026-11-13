import pytest
from atesta_core.frameworks import Mapping, framework_results, framework_score, requirement_status
from atesta_core.scoring import ControlResult, Status

# Illustrative ids only; real requirement ids come from verified framework packs.
MAPPINGS = [
    Mapping("fw_a", "A-1", "ctl.mfa_all_users"),
    Mapping("fw_a", "A-2", "ctl.audit_logging"),
    Mapping("fw_b", "B-9", "ctl.mfa_all_users"),
    Mapping("fw_b", "B-9", "ctl.admin_mfa"),
]


def test_requirement_status_rules() -> None:
    assert requirement_status([]) is Status.MANUAL
    assert requirement_status([Status.PASS, Status.FAIL]) is Status.FAIL
    assert requirement_status([Status.PASS, Status.MANUAL]) is Status.MANUAL
    assert requirement_status([Status.NOT_APPLICABLE] * 2) is Status.NOT_APPLICABLE
    assert requirement_status([Status.PASS, Status.NOT_APPLICABLE]) is Status.PASS


def test_one_control_serves_two_frameworks() -> None:
    controls = [
        ControlResult("ctl.mfa_all_users", Status.PASS),
        ControlResult("ctl.audit_logging", Status.FAIL),
        ControlResult("ctl.admin_mfa", Status.PASS),
    ]
    assert framework_score("fw_a", ["A-1", "A-2"], MAPPINGS, controls) == 50.0
    assert framework_score("fw_b", ["B-9"], MAPPINGS, controls) == 100.0


def test_unmapped_requirement_is_manual() -> None:
    results = framework_results("fw_a", ["A-1", "A-3"], MAPPINGS, [])
    assert {r.control_id: r.status for r in results} == {
        "A-1": Status.MANUAL,
        "A-3": Status.MANUAL,
    }


def test_group_scores_per_attribute_value() -> None:
    from atesta_core.frameworks import group_scores
    from atesta_core.scoring import ControlResult, Status

    results = [
        ControlResult("R-1", Status.PASS),
        ControlResult("R-2", Status.FAIL),
        ControlResult("R-3", Status.PASS),
        ControlResult("R-4", Status.MANUAL),
    ]
    attributes = {
        "R-1": {"dim": "a"},
        "R-2": {"dim": "a"},
        "R-3": {"dim": "b"},
        "R-4": {"dim": "c"},
    }
    assert group_scores(results, attributes, ["dim"]) == {"dim": {"a": 50.0, "b": 100.0, "c": None}}
    assert group_scores(results, attributes, []) == {}


def test_a_list_value_counts_once_in_each_of_its_groups() -> None:
    """A measure that applies to several dimensions scores in each of them."""
    from atesta_core.frameworks import group_scores
    from atesta_core.scoring import ControlResult, Status

    results = [ControlResult("P-1", Status.PASS), ControlResult("P-2", Status.FAIL)]
    attributes = {"P-1": {"dim": ["a", "b", "a"]}, "P-2": {"dim": "b"}}
    assert group_scores(results, attributes, ["dim"]) == {"dim": {"a": 100.0, "b": 50.0}}


@pytest.mark.parametrize("value", [True, 1, 2.5, {"x": "y"}, [], ["a", 1], ""])
def test_grouping_values_other_than_strings_are_rejected(value: object) -> None:
    from atesta_core.frameworks import group_scores
    from atesta_core.scoring import ControlResult, Status

    with pytest.raises(ValueError, match="grouping attribute"):
        group_scores([ControlResult("P-1", Status.PASS)], {"P-1": {"dim": value}}, ["dim"])


@pytest.mark.parametrize("keys", ["dim", ["dim", 1]])
def test_group_keys_must_be_a_list_of_strings(keys: object) -> None:
    from atesta_core.frameworks import group_scores

    with pytest.raises(ValueError, match="score group keys"):
        group_scores([], {}, keys)  # type: ignore[arg-type]
