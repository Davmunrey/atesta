"""The read-only allowlist (scanner-connectors spec, rule 1). Pure, versioned, written by hand.

Each provider and version has one exact expected set. The verifier compares what the scanner
identity holds with it: anything extra is `over_privileged` (scans blocked), anything missing is
`incomplete`. Never derived from Microsoft's "least privileged" column, which names a write
permission for group listing.

Graph application permission ids are copied from the Microsoft Graph permissions reference
(microsoftgraph/microsoft-graph-docs-contrib concepts/permissions-reference.md, ms.date
2026-09-14, re-checked 2026-11-13: all 20 match, all admin-consent only). Google scopes are the
six Prowler 5.49.0 requests (googleworkspace_provider.py SCOPES) and the verifier's one (D7).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

GRAPH = "00000003-0000-0000-c000-000000000000"
EXCHANGE = "00000002-0000-0ff1-ce00-000000000000"
_GOOGLE = "https://www.googleapis.com/auth/"
_WRITE_WORDS = frozenset({"Write", "Manage", "Send", "Create", "Delete", "Update"})


class Verdict(StrEnum):
    OK = "ok"
    INCOMPLETE = "incomplete"
    OVER_PRIVILEGED = "over_privileged"


@dataclass(frozen=True, slots=True)
class AppRole:
    resource: str
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class M365Allowlist:
    app_roles: tuple[AppRole, ...]


@dataclass(frozen=True, slots=True)
class GoogleAllowlist:
    scan_scopes: frozenset[str]
    verifier_scopes: frozenset[str]


def _graph(*roles: tuple[str, str]) -> tuple[AppRole, ...]:
    return tuple(AppRole(GRAPH, role_id, name) for name, role_id in roles)


M365_V1 = M365Allowlist(
    _graph(
        ("AccessReview.Read.All", "d07a8cc0-3d51-4b77-b3b0-32704d1f69fa"),
        ("AuditLog.Read.All", "b0afded3-3588-46d8-8b3d-9842eff778da"),
        ("Policy.Read.All", "246dd0d5-5bd0-4def-940b-0421030a5b68"),
        ("Policy.Read.DeviceConfiguration", "bdba4817-6ba1-4a7c-8a01-be9bc7c242dd"),
        ("RoleManagementPolicy.Read.Directory", "fdc4c997-9942-4479-bfcb-75a36d1138df"),
        ("RoleManagement.Read.Directory", "483bed4a-2ad3-4361-a73b-c83ccdbdc53c"),
        ("SecurityIdentitiesHealth.Read.All", "f8dcd971-5d83-4e1e-aa95-ef44611ad351"),
        ("SecurityIdentitiesSensors.Read.All", "5f0ffea2-f474-4cf2-9834-61cda2bcea5c"),
        ("SharePointTenantSettings.Read.All", "83d4163d-a2d8-4d3b-9695-4ae3ca98f888"),
        ("DeviceManagementServiceConfig.Read.All", "06a5fe6d-c49d-46a7-b082-56b1b14103c7"),
        ("DeviceManagementConfiguration.Read.All", "dc377aa6-52d8-4e23-b271-2a7ae04cedf3"),
        ("DeviceManagementManagedDevices.Read.All", "2f51be20-0bb4-4fed-bf7b-db946066c75e"),
        ("Organization.Read.All", "498476ce-e0fe-48b0-b801-37ba7e2685c6"),
        ("User.Read.All", "df021288-bdef-4463-88db-98f22de89214"),
        ("GroupMember.Read.All", "98830695-27a2-44f7-8c18-0c3ebc9698f6"),
        ("Application.Read.All", "9a5d68dd-52b0-4cc2-bd40-abcf44ac3a30"),
        ("Domain.Read.All", "dbb9058a-0e50-45d7-ae91-66909b5d4664"),
        ("GroupSettings.Read.All", "f3c4f514-c65a-43f5-bfce-1735872258dd"),
        ("LicenseAssignment.Read.All", "e2f98668-2877-4f38-a2f4-8202e0717aa1"),
        ("DelegatedPermissionGrant.Read.All", "81b4724a-58aa-41c1-8a55-84ef97466587"),
    )
)
GOOGLE_V1 = GoogleAllowlist(
    scan_scopes=frozenset(
        _GOOGLE + scope
        for scope in (
            "admin.directory.user.readonly",
            "admin.directory.domain.readonly",
            "admin.directory.customer.readonly",
            "admin.directory.orgunit.readonly",
            "admin.directory.rolemanagement.readonly",
            "cloud-identity.policies.readonly",
        )
    ),
    verifier_scopes=frozenset({_GOOGLE + "admin.reports.audit.readonly"}),
)
_M365 = {"m365-v1": M365_V1}
_GOOGLE_VERSIONS = {"google-v1": GOOGLE_V1}


@dataclass(frozen=True, slots=True)
class M365Grants:
    """What the scanner app holds in one tenant (verifier steps 3 to 5)."""

    app_roles: frozenset[tuple[str, str]]  # (resource app id, app role id)
    role_names: Mapping[str, str]  # app role id -> value, for the name gate
    directory_roles: frozenset[tuple[str, str]]  # (role template id, directory scope)
    delegated_grants: int


@dataclass(frozen=True, slots=True)
class GoogleGrants:
    scan_scopes: frozenset[str]
    verifier_scopes: frozenset[str]
    role_assignments: int  # admin roles assigned to either service account


@dataclass(frozen=True, slots=True)
class Report:
    verdict: Verdict
    missing: tuple[str, ...]
    extra: tuple[str, ...]


def is_read_only_name(name: str) -> bool:
    """A `Read` segment, and no segment with a write word (CamelCase words, so `RoleManagement`
    passes and `ReadWrite` or `ManageAsApp` fail)."""
    segments = name.split(".")
    words = {word for segment in segments for word in re.findall(r"[A-Z][a-z]*", segment)}
    return "Read" in segments and not words & _WRITE_WORDS


def _report(missing: list[str], extra: list[str]) -> Report:
    verdict = Verdict.OVER_PRIVILEGED if extra else Verdict.INCOMPLETE if missing else Verdict.OK
    return Report(verdict, tuple(sorted(missing)), tuple(sorted(extra)))


def _version[T](versions: Mapping[str, T], version: str) -> T:
    if version not in versions:
        raise ValueError(f"unknown allowlist version: {version}")
    return versions[version]


def check_m365(version: str, grants: M365Grants) -> Report:
    allowlist = _version(_M365, version)
    expected = {(role.resource, role.id): role.name for role in allowlist.app_roles}
    missing = [name for key, name in expected.items() if key not in grants.app_roles]
    extra = [f"app role {r}/{i}" for r, i in grants.app_roles if (r, i) not in expected]
    extra += [
        f"write-named role {name}"
        for name in grants.role_names.values()
        if not is_read_only_name(name)
    ]
    extra += [f"directory role {role} at {scope}" for role, scope in grants.directory_roles]
    if grants.delegated_grants:
        extra.append(f"{grants.delegated_grants} delegated grant(s)")
    return _report(missing, extra)


def google_allowlist(version: str) -> GoogleAllowlist:
    """The expected scopes of each Google client for this version (the verifier's step 1)."""
    return _version(_GOOGLE_VERSIONS, version)


def check_google(version: str, grants: GoogleGrants) -> Report:
    allowlist = google_allowlist(version)
    missing, extra = [], []
    for client, granted, expected in (
        ("scan", grants.scan_scopes, allowlist.scan_scopes),
        ("verifier", grants.verifier_scopes, allowlist.verifier_scopes),
    ):
        missing += [f"{client} {scope}" for scope in expected - granted]
        extra += [f"{client} {scope}" for scope in granted - expected]
    if grants.role_assignments:
        extra.append(f"{grants.role_assignments} admin role assignment(s)")
    return _report(missing, extra)


def required_resource_access(version: str) -> list[dict[str, object]]:
    """The scanner app registration's requiredResourceAccess for this version."""
    allowlist = _version(_M365, version)
    resources = sorted({role.resource for role in allowlist.app_roles})
    return [
        {
            "resourceAppId": resource,
            "resourceAccess": [
                {"id": role.id, "type": "Role"}
                for role in sorted(allowlist.app_roles, key=lambda r: r.id)
                if role.resource == resource
            ],
        }
        for resource in resources
    ]
