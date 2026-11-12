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
