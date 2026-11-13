"""Checks the scanner never runs, and why (scanner-connectors spec, D1, D3, D6)."""

import pytest
from atesta_core.exclusions import D3_CHECKS, D6_CHECKS, excluded_checks


def test_the_decision_lists_are_the_specs() -> None:
    assert D3_CHECKS == (
        "defenderxdr_critical_asset_management_pending_approvals",
        "defenderxdr_endpoint_privileged_user_exposed_credentials",
        "entra_app_registration_no_unused_privileged_permissions",
    )
    assert D6_CHECKS == (
        "drive_shared_drive_disable_download_print_copy",
        "drive_shared_drive_managers_cannot_override",
        "drive_shared_drive_members_only_access",
        "security_dlp_drive_rules_configured",
        "security_session_duration_limited",
    )


def test_m365_excludes_powershell_and_threat_hunting_checks_as_not_granted() -> None:
    powershell = [
        "teams_meeting_recording_disabled",
        "exchange_transport_config_smtp_auth_disabled",
    ]
    assert excluded_checks("m365", powershell) == dict.fromkeys(
        sorted([*powershell, *D3_CHECKS]), "not_granted"
    )


def test_google_excludes_the_licensing_lookups() -> None:
    # D6: these five ask for an apps.licensing token on FAIL; never requested (rule 1).
    assert excluded_checks("google_workspace", []) == dict.fromkeys(D6_CHECKS, "excluded")


def test_powershell_checks_apply_to_m365_only() -> None:
    with pytest.raises(ValueError, match="m365"):
        excluded_checks("google_workspace", ["teams_meeting_recording_disabled"])


def test_an_unknown_provider_is_refused() -> None:
    with pytest.raises(ValueError, match="provider"):
        excluded_checks("aws", [])
