"""M365 read-only verification, Graph only until PR 10 (scanner-connectors spec, steps 2 to 5).

Reads what the scanner app holds in the tenant and compares it with the connection's allowlist
version (atesta_core.connectors.readonly). Fails closed: a role the verifier cannot name counts
as extra, a read it may not make is `incomplete`, and nothing unreadable is ever `ok`. The
report holds ids, names and verdicts only.
"""

from typing import Any, Protocol

from atesta_core.connectors.readonly import M365Grants, check_m365

from atesta_scanner.graph import GraphDeniedError, GraphTransientError

# Verifier limits (spec): recorded in every report, shown in onboarding.
M365_LIMITS = (
    "exchange_rbac_not_read",  # no Exchange session until PR 10 (D1)
    "roles_through_groups_not_read",  # step 5c, candidate until the live golden
    "azure_rbac_not_read",  # step 5d, candidate until the live golden
    "tokens_issued_before_revocation",
)


class GraphReader(Protocol):
    def get(self, path: str, params: Any = None) -> Any: ...
    def get_all(self, path: str, params: Any = None) -> list[Any]: ...


def report(
    verdict: str,
    tenant_id: str | None = None,
    granted: dict[str, list[str]] | None = None,
    missing: list[str] | None = None,
    extra: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "tenant_id": tenant_id,
        "granted": granted or {},
        "missing": missing or [],
        "extra": extra or [],
        "limits": list(M365_LIMITS),
    }


def _grants(graph: GraphReader, app_id: str) -> tuple[M365Grants, dict[str, list[str]]]:
    sp_id = graph.get(f"/servicePrincipals(appId='{app_id}')")["id"]
    assignments = graph.get_all(f"/servicePrincipals/{sp_id}/appRoleAssignments")
    resources: dict[str, tuple[str, dict[str, str]]] = {}
    for assignment in assignments:
        rid = assignment["resourceId"]
        if rid not in resources:
            resource = graph.get(f"/servicePrincipals/{rid}", {"$select": "appId,appRoles"})
            names = {role["id"]: role["value"] for role in resource.get("appRoles", [])}
            resources[rid] = (resource["appId"], names)
    held = {(resources[a["resourceId"]][0], a["appRoleId"]) for a in assignments}
    # A role id the resource does not name keeps its id as name: it fails the name gate.
    names = {
        a["appRoleId"]: resources[a["resourceId"]][1].get(a["appRoleId"], a["appRoleId"])
        for a in assignments
    }
    delegated = graph.get_all(f"/servicePrincipals/{sp_id}/oauth2PermissionGrants")
    roles = graph.get_all(
        "/roleManagement/directory/roleAssignments", {"$filter": f"principalId eq '{sp_id}'"}
    )
    directory = {(r["roleDefinitionId"], r["directoryScopeId"]) for r in roles}
    grants = M365Grants(frozenset(held), names, frozenset(directory), len(delegated))
    ids = {
        "app_roles": sorted(f"{resource}/{role}" for resource, role in held),
        "directory_roles": sorted(f"{role}@{scope}" for role, scope in directory),
        "delegated_grants": sorted(str(grant["id"]) for grant in delegated),
    }
    return grants, ids


def verify_m365(graph: GraphReader, *, app_id: str, tenant: str, version: str) -> dict[str, Any]:
    try:
        organizations = graph.get("/organization")["value"]
        tenant_id = organizations[0]["id"] if len(organizations) == 1 else None
        grants, ids = _grants(graph, app_id)
    except GraphDeniedError as denied:
        if denied.status == 404:
            return report("revoked")  # the scanner app is gone from the tenant
        # A read it may not make: a permission it needs to verify is missing.
        return report("incomplete", missing=["read access for verification"])
    except (GraphTransientError, KeyError, IndexError, TypeError):
        return report("transient")
    result = check_m365(version, grants)
    return report(result.verdict.value, tenant_id, ids, list(result.missing), list(result.extra))
