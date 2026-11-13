"""Read-only allowlist (scanner-connectors spec, rule 1): extra blocks, missing waits."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from atesta_core.connectors.readonly import (
    EXCHANGE,
    GOOGLE_V1,
    GRAPH,
    M365_V1,
    GoogleGrants,
    M365Grants,
    Verdict,
    check_google,
    check_m365,
    is_read_only_name,
    required_resource_access,
)

REPO = Path(__file__).resolve().parents[3]
DIRECTORY_READ_ALL = "7ab1d382-f21e-4acd-a863-ba3e13f7da61"
USER_READWRITE_ALL = "741f803b-c850-494e-b5df-cde7c675a1ca"
GLOBAL_READER = "f2ef992c-3afb-46b9-b7cf-a126ee74c451"


def m365(**changes: object) -> M365Grants:
    base = {
        "app_roles": frozenset((GRAPH, role.id) for role in M365_V1.app_roles),
        "role_names": {role.id: role.name for role in M365_V1.app_roles},
        "directory_roles": frozenset(),
        "delegated_grants": 0,
    }
    return M365Grants(**{**base, **changes})  # type: ignore[arg-type]


def test_the_expected_m365_set_passes() -> None:
    assert check_m365("m365-v1", m365()).verdict is Verdict.OK


def test_v1_is_the_specs_twenty_graph_read_permissions() -> None:
    names = sorted(role.name for role in M365_V1.app_roles)
    assert len(names) == 20
    assert "Directory.Read.All" not in names  # D2: only by a version bump
    assert "ThreatHunting.Read.All" not in names  # D3: never on the scanner app
    assert all(role.resource == GRAPH for role in M365_V1.app_roles)
    assert not any("ReadWrite" in name for name in names)


@pytest.mark.parametrize("name", sorted(role.name for role in M365_V1.app_roles))
def test_every_allowlisted_name_passes_the_name_gate(name: str) -> None:
    assert is_read_only_name(name)


@pytest.mark.parametrize(
    ("name", "read_only"),
    [
        ("User.Read.All", True),
        ("Policy.Read.DeviceConfiguration", True),
        ("DeviceManagementManagedDevices.Read.All", True),
        ("User.ReadWrite.All", False),
        ("Mail.Send", False),
        ("Group.Create", False),
        ("Policy.ReadWrite.ConditionalAccess", False),
        ("Exchange.ManageAsApp", False),
        ("Sites.FullControl.All", False),  # no Read segment
        ("Application.Read.All.Update", False),
        ("Mail.Read.SendAs", False),  # a write word inside a segment
        ("Sites.Read.WriteAll", False),
    ],
)
def test_the_name_gate(name: str, read_only: bool) -> None:
    assert is_read_only_name(name) is read_only


def with_role(resource: str, role_id: str, name: str) -> M365Grants:
    grants = m365()
    return replace(
        grants,
        app_roles=grants.app_roles | {(resource, role_id)},
        role_names={**grants.role_names, role_id: name},
    )


OVER_PRIVILEGED = {
    "an allowed but unexpected role (Directory.Read.All)": with_role(
        GRAPH, DIRECTORY_READ_ALL, "Directory.Read.All"
    ),
    "a write role": with_role(GRAPH, USER_READWRITE_ALL, "User.ReadWrite.All"),
    "an Exchange role on v1": with_role(
        EXCHANGE, "dc50a0fb-09a3-484d-be87-e023b12c6440", "Exchange.ManageAsApp"
    ),
    "a directory role": m365(directory_roles=frozenset({(GLOBAL_READER, "/")})),
    "a delegated grant": m365(delegated_grants=1),
}


@pytest.mark.parametrize("case", sorted(OVER_PRIVILEGED))
def test_anything_extra_is_over_privileged(case: str) -> None:
    assert check_m365("m365-v1", OVER_PRIVILEGED[case]).verdict is Verdict.OVER_PRIVILEGED


def test_a_known_role_id_under_a_write_name_is_over_privileged() -> None:
    # Second gate: the id set alone is not trusted if a granted role reads as a write role.
    role = M365_V1.app_roles[0]
    report = check_m365("m365-v1", m365(role_names={role.id: "User.ReadWrite.All"}))
    assert report.verdict is Verdict.OVER_PRIVILEGED


def test_anything_missing_is_incomplete_and_named() -> None:
    first, *rest = M365_V1.app_roles
    report = check_m365("m365-v1", m365(app_roles=frozenset((GRAPH, r.id) for r in rest)))
    assert report.verdict is Verdict.INCOMPLETE
    assert report.missing == (first.name,)


def test_extra_wins_over_missing() -> None:
    _, *rest = M365_V1.app_roles
    grants = m365(
        app_roles=frozenset((GRAPH, r.id) for r in rest) | {(GRAPH, DIRECTORY_READ_ALL)},
        role_names={**m365().role_names, DIRECTORY_READ_ALL: "Directory.Read.All"},
    )
    assert check_m365("m365-v1", grants).verdict is Verdict.OVER_PRIVILEGED


def test_an_unknown_allowlist_version_is_refused() -> None:
    with pytest.raises(ValueError, match="allowlist version"):
        check_m365("m365-v9", m365())


def google(**changes: object) -> GoogleGrants:
    base = {
        "scan_scopes": GOOGLE_V1.scan_scopes,
        "verifier_scopes": GOOGLE_V1.verifier_scopes,
        "role_assignments": 0,
    }
    return GoogleGrants(**{**base, **changes})  # type: ignore[arg-type]


def test_the_google_v1_scopes_are_the_specs() -> None:
    prefix = "https://www.googleapis.com/auth/"
    assert GOOGLE_V1.scan_scopes == frozenset(
        prefix + s
        for s in (
            "admin.directory.user.readonly",
            "admin.directory.domain.readonly",
            "admin.directory.customer.readonly",
            "admin.directory.orgunit.readonly",
            "admin.directory.rolemanagement.readonly",
            "cloud-identity.policies.readonly",
        )
    )
    assert GOOGLE_V1.verifier_scopes == frozenset({prefix + "admin.reports.audit.readonly"})


GOOGLE_CASES = {
    "expected": ({}, Verdict.OK),
    "an extra scope (apps.licensing)": (
        {"scan_scopes": GOOGLE_V1.scan_scopes | {"https://www.googleapis.com/auth/apps.licensing"}},
        Verdict.OVER_PRIVILEGED,
    ),
    "the reports scope on the scan client": (
        {"scan_scopes": GOOGLE_V1.scan_scopes | GOOGLE_V1.verifier_scopes},
        Verdict.OVER_PRIVILEGED,
    ),
    "an admin role on a service account": ({"role_assignments": 1}, Verdict.OVER_PRIVILEGED),
    "a missing scan scope": (
        {"scan_scopes": frozenset(sorted(GOOGLE_V1.scan_scopes)[1:])},
        Verdict.INCOMPLETE,
    ),
    "no verifier scope": ({"verifier_scopes": frozenset()}, Verdict.INCOMPLETE),
}


@pytest.mark.parametrize("case", sorted(GOOGLE_CASES))
def test_google_grants(case: str) -> None:
    changes, verdict = GOOGLE_CASES[case]
    assert check_google("google-v1", google(**changes)).verdict is verdict


def test_the_exported_registration_equals_the_expected_set() -> None:
    exported = json.loads((REPO / "infra" / "entra" / "scanner-app" / "dev.json").read_text())

    def normal(access: list[dict[str, object]]) -> object:
        return sorted(
            (a["resourceAppId"], sorted((r["id"], r["type"]) for r in a["resourceAccess"]))  # type: ignore[index]
            for a in access
        )

    assert normal(exported["requiredResourceAccess"]) == normal(required_resource_access("m365-v1"))
