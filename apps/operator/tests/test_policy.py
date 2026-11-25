"""The permissions matrix, walked for every role and route (operator-portal spec, "Permissions
matrix", acceptance criterion "Matrix"), and the recent sign-in rule ("Session limits").

Each call uses an unknown id and no body: a role the matrix allows gets past authorization (then a
404 or 422), a role it refuses gets 403 before anything else runs.
"""

import uuid

import pytest
from atesta_operator.auth import CurrentStaff
from atesta_operator.main import create_app
from atesta_operator.policy import POLICY
from fastapi.testclient import TestClient

from .conftest import Issuer, MakeStaff, bearer

ROLES = ("admin", "billing", "support")
A, B, S = "admin", "billing", "support"
# The spec's API table, copied: changing who may do what changes this test and the spec together.
SPEC: dict[tuple[str, str], tuple[frozenset[str], bool]] = {
    ("GET", "/api/v1/me"): (frozenset({A, B, S}), False),
    ("GET", "/api/v1/organizations"): (frozenset({A, B, S}), False),
    ("GET", "/api/v1/organizations/{org_id}"): (frozenset({A, B, S}), False),
    ("GET", "/api/v1/plans"): (frozenset({A, B}), False),  # the plan editor's options (#477)
    ("PUT", "/api/v1/organizations/{org_id}/subscription"): (frozenset({A, B}), False),
    ("GET", "/api/v1/organizations/{org_id}/billing-profile"): (frozenset({A, B}), False),
    ("PUT", "/api/v1/organizations/{org_id}/billing-profile"): (frozenset({A, B}), False),
    ("POST", "/api/v1/organizations/{org_id}/suspension"): (frozenset({A}), True),
    ("DELETE", "/api/v1/organizations/{org_id}/suspension"): (frozenset({A}), False),
    ("POST", "/api/v1/organizations/{org_id}/export-request"): (frozenset({A}), False),
    ("POST", "/api/v1/organizations/{org_id}/closure"): (frozenset({A}), True),
    ("DELETE", "/api/v1/organizations/{org_id}/closure"): (frozenset({A}), False),
    ("POST", "/api/v1/organizations/{org_id}/erasure-requests"): (frozenset({A}), True),
    ("POST", "/api/v1/erasure-requests/{erasure_id}/approval"): (frozenset({A}), True),
    ("DELETE", "/api/v1/erasure-requests/{erasure_id}"): (frozenset({A}), False),
    ("GET", "/api/v1/erasure-receipts"): (frozenset({A}), False),
    ("GET", "/api/v1/staff"): (frozenset({A}), False),
    ("PATCH", "/api/v1/staff/{staff_id}"): (frozenset({A}), False),
    ("GET", "/api/v1/operator-events"): (frozenset({A}), False),
}


def routes() -> list[tuple[str, str]]:
    """Every API route, from the app's own OpenAPI document (routers nest inside the app)."""
    paths = create_app().openapi()["paths"]
    return sorted(
        (method.upper(), path)
        for path, operations in paths.items()
        if path.startswith("/api/")
        for method in operations
    )


def url(path: str) -> str:
    return path.format(org_id=uuid.uuid4(), erasure_id=uuid.uuid4(), staff_id=uuid.uuid4())


def test_the_policy_is_the_spec_table() -> None:
    assert {k: (r.roles, r.recent_sign_in) for k, r in POLICY.items()} == SPEC


def test_every_api_route_has_a_rule() -> None:
    assert set(routes()) <= set(POLICY)


@pytest.mark.parametrize("route", routes())
@pytest.mark.parametrize("role", ROLES)
def test_every_route_enforces_the_matrix(
    client: TestClient,
    make_staff: MakeStaff,
    staff_pool: Issuer,
    route: tuple[str, str],
    role: str,
) -> None:
    method, path = route
    token = staff_pool.token(make_staff(role))
    response = client.request(method, url(path), headers=bearer(token))
    if role in POLICY[route].roles:
        assert response.status_code not in (401, 403), response.json()
    else:
        assert response.status_code == 403
        assert response.json() == {"detail": {"code": "operator.forbidden"}}


@pytest.mark.parametrize("route", routes())
def test_a_sign_in_older_than_15_minutes_is_refused_where_the_rule_asks(
    client: TestClient, make_staff: MakeStaff, staff_pool: Issuer, route: tuple[str, str]
) -> None:
    method, path = route
    token = staff_pool.token(make_staff("admin"), signed_in_ago=16 * 60)
    response = client.request(method, url(path), headers=bearer(token))
    if POLICY[route].recent_sign_in:
        assert response.status_code == 401
        assert response.json() == {"detail": {"code": "operator.recent_auth_required"}}
    else:
        assert response.status_code not in (401, 403)


def test_a_route_missing_from_the_policy_is_refused_to_every_role(
    client: TestClient, make_staff: MakeStaff, staff_pool: Issuer
) -> None:
    app = client.app

    def unlisted(staff: CurrentStaff) -> dict[str, str]:
        return {"role": staff.role}

    app.add_api_route("/api/v1/unlisted", unlisted, methods=["GET"])  # type: ignore[attr-defined]
    response = client.get("/api/v1/unlisted", headers=bearer(staff_pool.token(make_staff("admin"))))
    assert response.status_code == 403
