"""Every route of the API, not a sample: tenant isolation and the auditor rules hold on all of them.

identity-auth spec: org routes answer 404 to a non-member (no org enumeration), and a request
without credentials gets 401. rbac spec: an auditor's write is refused in require_member "whatever
the endpoint", and expired access is refused for every request. The routes come from the OpenAPI
document, so a route added later is swept without editing this file.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from atesta_api.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from .conftest import auth
from .test_members import org_with
from .test_rbac import _add

# Routes that authenticate with an API key (api-keys-v2 spec). Adding one is a reviewed change.
TOKEN_ROUTES = {
    ("GET", "/api/v1/key"),
    ("POST", "/api/v1/ingest/evidence"),
    ("GET", "/api/v1/frameworks"),
    ("GET", "/api/v1/frameworks/{framework_key}/measures"),
    ("GET", "/api/v1/frameworks/{framework_key}/measures/{code}"),
    ("GET", "/api/v1/gaps"),
    ("GET", "/api/v1/due"),
    ("GET", "/api/v1/incidents"),
    ("GET", "/api/v1/incidents/{incident_id}"),
    ("POST", "/api/v1/frameworks/{framework_key}/measures/{code}/proposals"),
    ("POST", "/api/v1/incidents"),
    ("POST", "/api/v1/incidents/{incident_id}/updates"),
    ("POST", "/api/v1/training-campaigns"),
    ("POST", "/api/v1/access-reviews"),
}
# Reached without a session: sign-in, the health check, and the routes that authenticate with
# their own secret (training link, API key, unsubscribe link). Adding one is a reviewed change
# to this list.
PUBLIC = {
    ("GET", "/health"),
    ("GET", "/auth/login"),
    ("GET", "/auth/callback"),
    ("GET", "/auth/logout"),
    ("POST", "/api/v1/training/link"),
    ("POST", "/api/v1/training/acknowledge"),
    # RFC 8058 one-click unsubscribe: a sealed token, ADR-012 amendment 7 (notifications spec).
    ("POST", "/api/v1/unsubscribe"),
    *TOKEN_ROUTES,
}
WRITES = {"POST", "PUT", "PATCH", "DELETE"}


def _routes() -> list[tuple[str, str]]:
    paths = create_app().openapi()["paths"]
    return sorted((method.upper(), path) for path, ops in paths.items() for method in ops)


ROUTES = _routes()
ORG_ROUTES = [r for r in ROUTES if "{org_id}" in r[1]]


def _url(path: str, org: str) -> str:
    """Fill the path: the org under test, and placeholder values for the rest."""

    def value(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "org_id":
            return org
        return str(uuid.uuid4()) if name.endswith("_id") else "x.sweep"

    return re.sub(r"\{([a-z_]+)\}", value, path)


def _call(client: TestClient, method: str, url: str, headers: dict[str, str]) -> tuple[int, str]:
    body = {} if method in WRITES and method != "DELETE" else None
    response = client.request(method, url, json=body, headers=headers)
    detail = response.json().get("detail") if response.content else None
    code = detail.get("code", "") if isinstance(detail, dict) else ""
    return response.status_code, code


def test_the_sweep_sees_every_route() -> None:
    assert len(ORG_ROUTES) > 50
    assert {r for r in ROUTES if "{org_id}" not in r[1]} >= PUBLIC


def test_routes_without_a_session_are_the_reviewed_public_list() -> None:
    paths = create_app().openapi()["paths"]
    open_routes = {
        (method.upper(), path)
        for path, ops in paths.items()
        for method, op in ops.items()
        if not op.get("security")
    }
    assert open_routes == PUBLIC


@pytest.mark.parametrize(("method", "path"), sorted(set(ROUTES) - PUBLIC))
def test_every_other_route_refuses_a_caller_without_credentials(
    client: TestClient, method: str, path: str
) -> None:
    status, code = _call(client, method, _url(path, str(uuid.uuid4())), {})
    assert (status, code) == (401, "auth.invalid_token")


@pytest.mark.parametrize(("method", "path"), sorted(TOKEN_ROUTES))
def test_every_token_route_refuses_a_caller_without_a_key(
    client: TestClient, superuser: Engine, method: str, path: str
) -> None:
    """A person's session is not a key, and no key is no access (api-keys-v2 spec)."""
    _, subs = org_with(client, superuser)
    for headers in ({}, auth(subs["owner"]), {"Authorization": "Bearer atesta_" + "x" * 43}):
        status, code = _call(client, method, _url(path, str(uuid.uuid4())), headers)
        assert (status, code) == (401, "identity.api_token_invalid"), headers


def test_token_routes_name_no_organization() -> None:
    """A key reaches only its own organization: no token route can even name another one."""
    assert all("{org_id}" not in path for _, path in TOKEN_ROUTES)


def test_every_org_route_answers_404_to_a_member_of_another_organization(
    client: TestClient, superuser: Engine
) -> None:
    _, subs = org_with(client, superuser)
    target, _ = org_with(client, superuser)
    wrong = {
        (method, path): _call(client, method, _url(path, target), auth(subs["owner"]))
        for method, path in ORG_ROUTES
    }
    assert {k: v for k, v in wrong.items() if v != (404, "identity.not_found")} == {}


def test_every_org_write_refuses_an_auditor(client: TestClient, superuser: Engine) -> None:
    org, _ = org_with(client, superuser)
    auditor = _add(superuser, client, org, "auditor", datetime.now(UTC) + timedelta(days=30))
    writes = [(m, p) for m, p in ORG_ROUTES if m in WRITES]
    assert writes
    wrong = {
        (method, path): _call(client, method, _url(path, org), auth(auditor))
        for method, path in writes
    }
    assert {k: v for k, v in wrong.items() if v != (403, "identity.forbidden")} == {}


def test_every_org_route_refuses_expired_access(client: TestClient, superuser: Engine) -> None:
    org, _ = org_with(client, superuser)
    auditor = _add(superuser, client, org, "auditor", datetime.now(UTC) - timedelta(minutes=1))
    wrong = {
        (method, path): _call(client, method, _url(path, org), auth(auditor))
        for method, path in ORG_ROUTES
    }
    assert {k: v for k, v in wrong.items() if v != (403, "identity.access_expired")} == {}


def test_the_contract_names_each_token_routes_permission() -> None:
    """The public API reference (#334) is built from these: tag api-keys and x-atesta-scope."""
    paths = create_app().openapi()["paths"]
    tagged = {
        (method.upper(), path)
        for path, ops in paths.items()
        for method, op in ops.items()
        if "api-keys" in op.get("tags", [])
    }
    assert tagged == TOKEN_ROUTES
    scopes = {(m, p): paths[p][m.lower()].get("x-atesta-scope") for m, p in TOKEN_ROUTES}
    assert scopes.pop(("GET", "/api/v1/key")) is None
    assert set(scopes.values()) == {
        "compliance:read",
        "incidents:read",
        "evidence:write",
        "assessment:propose",
        "routines:write",
    }
    assert scopes[("POST", "/api/v1/ingest/evidence")] == "evidence:write"
