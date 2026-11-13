"""Control results from check results (scanner-connectors spec, Findings to controls; ADR-005)."""

import pytest
from atesta_core.controls import control_results, control_status
from atesta_core.scoring import ControlResult, Status

P = "prowler"


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["pass"], Status.PASS),
        (["pass", "pass"], Status.PASS),
        (["pass", "manual"], Status.MANUAL),
        (["pass", "fail"], Status.FAIL),
        # A failure is a fact even when another check could not be evaluated.
        (["fail", "not_evaluated"], Status.FAIL),
        # Anything not evaluated keeps the control unassessed, never pass (ADR-005).
        (["pass", "not_evaluated"], None),
        (["manual", "not_evaluated"], None),
        ([], None),
    ],
)
def test_control_status(statuses: list[str], expected: Status | None) -> None:
    assert control_status(statuses) == expected


def test_an_unknown_check_status_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown check status"):
        control_status(["passed"])


CONTROLS = {
    "c.mfa": [(P, "entra_admin_users_mfa_enabled")],
    "c.mixed": [
        (P, "entra_admin_users_mfa_enabled"),
        (P, "exchange_transport_rules_whitelist_disabled"),
    ],
    "c.split": [(P, "entra_admin_users_cloud_only"), (P, "calendar_external_invitations_warning")],
    "c.google": [(P, "calendar_external_invitations_warning")],
    "c.other_engine": [("atesta", "entra_admin_users_mfa_enabled")],
}
M365 = [
    (P, "entra_admin_users_mfa_enabled", "pass"),
    (P, "entra_admin_users_cloud_only", "pass"),
    (P, "exchange_transport_rules_whitelist_disabled", "not_evaluated"),
]


def test_only_checks_with_a_result_are_in_scope() -> None:
    # c.split keeps its M365 check and ignores the Google one: no Google connection reported.
    # c.google has nothing in scope and gets no result. The engine is part of the check key.
    assert control_results(CONTROLS, M365) == [
        ControlResult("c.mfa", Status.PASS),
        ControlResult("c.split", Status.PASS),
    ]


def test_every_connection_counts_and_a_failure_anywhere_fails_the_control() -> None:
    second_tenant = [(P, "entra_admin_users_mfa_enabled", "fail")]
    google = [(P, "calendar_external_invitations_warning", "manual")]
    assert control_results(CONTROLS, [*M365, *second_tenant, *google]) == [
        ControlResult("c.google", Status.MANUAL),
        ControlResult("c.mfa", Status.FAIL),
        ControlResult("c.mixed", Status.FAIL),
        ControlResult("c.split", Status.MANUAL),
    ]


def test_a_control_with_no_checks_has_no_result() -> None:
    assert control_results({"c.manual": []}, M365) == []
