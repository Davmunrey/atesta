"""Coverage: one result per listed check; no finding never means pass (ADR-005)."""

from dataclasses import replace
from pathlib import Path

import pytest
from atesta_core.coverage import (
    CheckResult,
    UnexpectedCheckError,
    coverage,
    service_of,
    silent_services,
)
from atesta_core.ocsf import parse_findings

FIXTURES = Path(__file__).resolve().parents[3] / "scanner" / "fixtures" / "synthetic"
M365 = parse_findings((FIXTURES / "m365" / "scan.ocsf.json").read_bytes())
LISTED = [
    "entra_admin_users_mfa_enabled",
    "entra_admin_users_cloud_only",
    "entra_admin_consent_workflow_enabled",
    "exchange_mailbox_audit_bypass_disabled",
    "exchange_external_email_tagging_enabled",
    "exchange_transport_rules_whitelist_disabled",
    "teams_external_users_cannot_start_conversations",
    "defenderxdr_endpoint_privileged_user_exposed_credentials",
]
EXCLUDED = {
    "teams_external_users_cannot_start_conversations": "not_granted",
    "defenderxdr_endpoint_privileged_user_exposed_credentials": "excluded",
}


def result(check: str, status: str, reason: str | None = None, *counts: int) -> CheckResult:
    passed, failed, manual = counts or (0, 0, 0)
    return CheckResult(check, status, reason, passed, failed, manual)


def test_every_listed_check_gets_one_result() -> None:
    assert coverage(M365, LISTED, EXCLUDED) == [
        result(
            "defenderxdr_endpoint_privileged_user_exposed_credentials", "not_evaluated", "excluded"
        ),
        # Only a muted FAIL: not a failure, and nothing passed.
        result("entra_admin_consent_workflow_enabled", "manual", None, 0, 1, 0),
        result("entra_admin_users_cloud_only", "fail", None, 0, 1, 0),
        result("entra_admin_users_mfa_enabled", "pass", None, 1, 0, 0),
        result("exchange_external_email_tagging_enabled", "pass", None, 1, 0, 0),
        result("exchange_mailbox_audit_bypass_disabled", "manual", None, 0, 0, 1),
        result("exchange_transport_rules_whitelist_disabled", "not_evaluated", "no_findings"),
        result("teams_external_users_cannot_start_conversations", "not_evaluated", "not_granted"),
    ]


def test_an_unmuted_fail_wins_over_passes() -> None:
    mfa = next(f for f in M365 if f.check_id == "entra_admin_users_mfa_enabled")
    fail, manual = replace(mfa, status="fail"), replace(mfa, status="manual")
    assert coverage([mfa, manual, fail], [mfa.check_id], {}) == [
        result(mfa.check_id, "fail", None, 1, 1, 1)
    ]
    assert coverage([manual, mfa], [mfa.check_id], {}) == [
        result(mfa.check_id, "pass", None, 1, 0, 1)
    ]


@pytest.mark.parametrize("fixture", ["m365", "googleworkspace"])
def test_a_check_outside_the_expected_list_rejects_the_scan(fixture: str) -> None:
    findings = parse_findings((FIXTURES / fixture / "unexpected-check.ocsf.json").read_bytes())
    listed = sorted({f.check_id for f in findings} - {f.check_id for f in findings[-1:]})
    with pytest.raises(UnexpectedCheckError, match=f"finding {len(findings) - 1}"):
        coverage(findings, listed, {})


def test_a_finding_for_an_excluded_check_rejects_the_scan() -> None:
    excluded = {"entra_admin_users_mfa_enabled": "not_granted"}
    with pytest.raises(UnexpectedCheckError, match="finding 0"):
        coverage(M365, LISTED, excluded)


@pytest.mark.parametrize(
    ("excluded", "message"),
    [
        ({"entra_fixture_unknown_check": "excluded"}, "not listed"),
        ({"entra_admin_users_mfa_enabled": "no_findings"}, "reason"),
    ],
)
def test_exclusions_must_name_listed_checks_and_a_known_reason(
    excluded: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        coverage([], LISTED, excluded)


def test_a_check_listed_twice_is_a_configuration_error() -> None:
    with pytest.raises(ValueError, match="twice"):
        coverage([], [*LISTED, LISTED[0]], {})


def test_the_service_is_the_check_id_prefix() -> None:
    # Prowler 5.49.0 lib/check/models.py: ServiceName must equal CheckID.split("_")[0].
    assert service_of("defenderxdr_endpoint_privileged_user_exposed_credentials") == "defenderxdr"
    assert service_of("chat_apps_installation_disabled") == "chat"


def test_silent_services_are_expected_services_with_no_finding_at_all() -> None:
    listed = [
        *LISTED,
        "sharepoint_external_sharing_restricted",
        "teams_meeting_chat_anonymous_users_disabled",
    ]
    results = coverage(M365, listed, EXCLUDED)
    # exchange has a check with no finding but others with findings: not silent. teams is
    # silent only through its non-excluded check; defenderxdr is fully excluded, so not expected.
    assert silent_services(results) == ["sharepoint", "teams"]
    assert silent_services(coverage(M365, LISTED, EXCLUDED)) == []
