"""M365 read-only verification, Graph only (scanner-connectors spec, Read-only verification).

Fail closed: anything extra is over_privileged, anything missing incomplete, a role the
verifier cannot name counts as extra, and a Graph it cannot read is never `ok`.
"""

import json
from collections.abc import Mapping
from typing import Any

import httpx
import pytest
from atesta_core.connectors.readonly import GRAPH, M365_V1
from atesta_scanner.graph import GRAPH_ROOT, Graph, GraphDeniedError, GraphTransientError
from atesta_scanner.verify_m365 import M365_LIMITS, verify_m365

TENANT = "abcdef01-1111-4111-8111-111111111111"
APP = "0a0a0a0a-0000-4000-8000-000000000001"
SP = "5b5b5b5b-0000-4000-8000-000000000002"
GRAPH_SP = "6c6c6c6c-0000-4000-8000-000000000003"
EXCHANGE_SP = "7d7d7d7d-0000-4000-8000-000000000004"
GRAPH_ROLES = [{"id": r.id, "value": r.name} for r in M365_V1.app_roles] + [
    {"id": "741f803b-c850-494e-b5df-cde7c675a1ca", "value": "User.ReadWrite.All"}
]


class FakeGraph:
    """Answers the verifier's Graph reads from a dict, like a recorded tenant."""

    def __init__(self, **overrides: Any) -> None:
        self.answers: dict[str, Any] = {
            "/organization": {"value": [{"id": TENANT}]},
            f"/servicePrincipals(appId='{APP}')": {"id": SP},
            f"/servicePrincipals/{SP}/appRoleAssignments": [
                {"resourceId": GRAPH_SP, "appRoleId": r.id} for r in M365_V1.app_roles
            ],
            f"/servicePrincipals/{GRAPH_SP}": {"appId": GRAPH, "appRoles": GRAPH_ROLES},
            f"/servicePrincipals/{SP}/oauth2PermissionGrants": [],
            "/roleManagement/directory/roleAssignments": [],
            **overrides,
        }
        self.filters: list[Mapping[str, str] | None] = []

    def _answer(self, path: str) -> Any:
        answer = self.answers[path]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def get(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        return self._answer(path)

    def get_all(self, path: str, params: Mapping[str, str] | None = None) -> list[Any]:
        self.filters.append(params)
        return list(self._answer(path))


def verify(graph: FakeGraph) -> dict[str, Any]:
    return verify_m365(graph, app_id=APP, tenant=TENANT, version="m365-v1")


def test_exactly_the_allowlist_is_ok_and_reported_by_id() -> None:
    graph = FakeGraph()
    report = verify(graph)
    assert report["verdict"] == "ok"
    assert report["tenant_id"] == TENANT
    assert (report["missing"], report["extra"]) == ([], [])
    assert report["granted"]["app_roles"] == sorted(f"{GRAPH}/{r.id}" for r in M365_V1.app_roles)
    assert report["limits"] == list(M365_LIMITS)
    # Directory roles are read for the scanner's own service principal only.
    assert {"$filter": f"principalId eq '{SP}'"} in graph.filters
    json.dumps(report)  # the report is plain JSON: ids, names and verdicts only


def test_one_missing_permission_is_incomplete() -> None:
    held = [{"resourceId": GRAPH_SP, "appRoleId": r.id} for r in M365_V1.app_roles[1:]]
    report = verify(FakeGraph(**{f"/servicePrincipals/{SP}/appRoleAssignments": held}))
    assert (report["verdict"], report["missing"]) == ("incomplete", [M365_V1.app_roles[0].name])


@pytest.mark.parametrize(
    ("path", "answer"),
    [
        # A write permission on top of the allowlist.
        (
            f"/servicePrincipals/{SP}/appRoleAssignments",
            [{"resourceId": GRAPH_SP, "appRoleId": r.id} for r in M365_V1.app_roles]
            + [{"resourceId": GRAPH_SP, "appRoleId": "741f803b-c850-494e-b5df-cde7c675a1ca"}],
        ),
        # A role the verifier cannot name: fail closed.
        (
            f"/servicePrincipals/{SP}/appRoleAssignments",
            [{"resourceId": GRAPH_SP, "appRoleId": r.id} for r in M365_V1.app_roles]
            + [{"resourceId": GRAPH_SP, "appRoleId": "99999999-0000-4000-8000-000000000000"}],
        ),
        # Any delegated grant to the scanner app.
        (f"/servicePrincipals/{SP}/oauth2PermissionGrants", [{"id": "grant-1"}]),
        # Any directory role (v1 expects none).
        (
            "/roleManagement/directory/roleAssignments",
            [{"roleDefinitionId": "f2ef992c-3afb-46b9-b7cf-a126ee74c451", "directoryScopeId": "/"}],
        ),
    ],
)
def test_anything_extra_is_over_privileged(path: str, answer: Any) -> None:
    report = verify(FakeGraph(**{path: answer}))
    assert report["verdict"] == "over_privileged"
    assert report["extra"]


def test_an_app_role_of_another_resource_is_extra() -> None:
    held = [{"resourceId": GRAPH_SP, "appRoleId": r.id} for r in M365_V1.app_roles] + [
        {"resourceId": EXCHANGE_SP, "appRoleId": "dc50a0fb-09a3-484d-be87-e023b12c6440"}
    ]
    exchange = {
        "appId": "00000002-0000-0ff1-ce00-000000000000",
        "appRoles": [
            {"id": "dc50a0fb-09a3-484d-be87-e023b12c6440", "value": "Exchange.ManageAsApp"}
        ],
    }
    graph = FakeGraph(
        **{
            f"/servicePrincipals/{SP}/appRoleAssignments": held,
            f"/servicePrincipals/{EXCHANGE_SP}": exchange,
        }
    )
    assert verify(graph)["verdict"] == "over_privileged"  # v1 is Graph only (D1)


def test_a_missing_service_principal_means_consent_was_revoked() -> None:
    gone = GraphDeniedError("not found", 404)
    assert verify(FakeGraph(**{f"/servicePrincipals(appId='{APP}')": gone}))["verdict"] == "revoked"


def test_reads_it_is_not_allowed_to_make_are_incomplete_never_ok() -> None:
    path = "/roleManagement/directory/roleAssignments"
    report = verify(FakeGraph(**{path: GraphDeniedError("forbidden", 403)}))
    assert report["verdict"] == "incomplete"
    assert report["missing"] == ["read access for verification"]


@pytest.mark.parametrize("error", [GraphTransientError("429"), KeyError("id")])
def test_throttling_and_malformed_answers_are_transient(error: Exception) -> None:
    report = verify(FakeGraph(**{"/organization": error}))
    assert report["verdict"] == "transient"


# The Graph client itself, against an httpx mock transport.


def client(handler: Any) -> Graph:
    return Graph("tok", httpx.Client(transport=httpx.MockTransport(handler)))


def test_pages_are_followed_within_graph_only() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert request.headers["Authorization"] == "Bearer tok"
        if "skiptoken" in str(request.url):
            return httpx.Response(200, json={"value": [{"id": "b"}]})
        page = {"value": [{"id": "a"}], "@odata.nextLink": f"{GRAPH_ROOT}/x?$skiptoken=2"}
        return httpx.Response(200, json=page)

    assert client(handler).get_all("/x") == [{"id": "a"}, {"id": "b"}]
    assert seen == [f"{GRAPH_ROOT}/x", f"{GRAPH_ROOT}/x?$skiptoken=2"]


def test_a_next_link_outside_graph_never_receives_the_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "graph.microsoft.com"
        page = {"value": [], "@odata.nextLink": "https://evil.example.com/x"}
        return httpx.Response(200, json=page)

    with pytest.raises(GraphTransientError, match="leaves Graph"):
        client(handler).get_all("/x")


@pytest.mark.parametrize(
    ("status", "error"),
    [(429, GraphTransientError), (503, GraphTransientError), (403, GraphDeniedError)],
)
def test_status_codes_map_to_transient_or_denied(status: int, error: type[Exception]) -> None:
    with pytest.raises(error):
        client(lambda request: httpx.Response(status, json={})).get("/organization")


def test_a_network_failure_is_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(GraphTransientError):
        client(handler).get("/organization")
