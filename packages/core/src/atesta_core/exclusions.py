"""Checks the scanner never runs, and the reason stored for each (scanner-connectors spec).

- PowerShell-backed M365 checks (D1): no directory role until PR 10, so `not_granted`. The list
  is data (`scanner/expected/<version>/m365-powershell.json`), passed in by the caller.
- D3: ThreatHunting.Read.All is never requested on the scanner app, so `not_granted`.
- D6: these Google checks ask for an apps.licensing token (no read-only variant) on FAIL; they
  are excluded so the token is never requested (rule 1), so `excluded`.
"""

from collections.abc import Iterable

D3_CHECKS = (
    "defenderxdr_critical_asset_management_pending_approvals",
    "defenderxdr_endpoint_privileged_user_exposed_credentials",
    "entra_app_registration_no_unused_privileged_permissions",
)
D6_CHECKS = (
    "drive_shared_drive_disable_download_print_copy",
    "drive_shared_drive_managers_cannot_override",
    "drive_shared_drive_members_only_access",
    "security_dlp_drive_rules_configured",
    "security_session_duration_limited",
)


def excluded_checks(provider: str, powershell: Iterable[str]) -> dict[str, str]:
    """{check id: reason} for one provider, sorted by check id."""
    powershell = list(powershell)
    if provider == "m365":
        excluded = dict.fromkeys([*powershell, *D3_CHECKS], "not_granted")
    elif provider == "google_workspace":
        if powershell:
            raise ValueError("PowerShell-backed checks apply to m365 only")
        excluded = dict.fromkeys(D6_CHECKS, "excluded")
    else:
        raise ValueError("unknown provider")
    return dict(sorted(excluded.items()))
