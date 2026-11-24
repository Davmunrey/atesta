"""Staff sign-in at the operator API (operator-portal spec, "Staff identity and roles"; ADR-017).

Real RS256 tokens from two pools against the real TokenVerifier, and staff rows in a real
Postgres read as atesta_operator.
"""

import pytest
from atesta_api.modules.identity.api import InvalidTokenError
from fastapi.testclient import TestClient

from .conftest import Issuer, MakeStaff, bearer


@pytest.mark.parametrize("role", ["admin", "billing", "support"])
def test_me_names_the_staff_member_and_role(
    client: TestClient, make_staff: MakeStaff, staff_pool: Issuer, role: str
) -> None:
    sub = make_staff(role, email=f"{role}@atesta.test")
    response = client.get("/api/v1/me", headers=bearer(staff_pool.token(sub)))
    assert response.status_code == 200
    assert response.json() == {"email": f"{role}@atesta.test", "role": role}


def test_no_token_is_401(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "auth.invalid_token"}}


def test_a_customer_pool_token_is_401(
    client: TestClient, make_staff: MakeStaff, customer_pool: Issuer
) -> None:
    """Even for a subject that has a staff row: another issuer and app client."""
    sub = make_staff("admin")
    response = client.get("/api/v1/me", headers=bearer(customer_pool.token(sub)))
    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "auth.invalid_token"}}


def test_the_customer_api_refuses_a_staff_pool_token(
    staff_pool: Issuer, customer_pool: Issuer
) -> None:
    """The customer API's verifier is the same class with the customer pool's settings."""
    with pytest.raises(InvalidTokenError):
        customer_pool.verifier().verify(staff_pool.token("staff-x"))


@pytest.mark.parametrize(
    "claims",
    [
        {"client_id": "customer-client"},  # the staff issuer, another app client
        {"token_use": "id"},
        {"scope": "openid email aws.cognito.signin.user.admin"},
        {"auth_time": None},  # every staff access token says when the person signed in
    ],
)
def test_a_token_that_is_not_a_staff_access_token_is_401(
    client: TestClient, make_staff: MakeStaff, staff_pool: Issuer, claims: dict[str, object]
) -> None:
    sub = make_staff("admin")
    response = client.get("/api/v1/me", headers=bearer(staff_pool.token(sub, **claims)))
    assert response.status_code == 401


def test_a_valid_token_without_a_staff_row_is_403(client: TestClient, staff_pool: Issuer) -> None:
    response = client.get("/api/v1/me", headers=bearer(staff_pool.token("nobody-here")))
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "operator.forbidden"}}


def test_a_disabled_staff_member_is_403(
    client: TestClient, make_staff: MakeStaff, staff_pool: Issuer
) -> None:
    sub = make_staff("admin", disabled=True)
    response = client.get("/api/v1/me", headers=bearer(staff_pool.token(sub)))
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "operator.forbidden"}}


def test_responses_are_not_cached(
    client: TestClient, make_staff: MakeStaff, staff_pool: Issuer
) -> None:
    sub = make_staff("support")
    response = client.get("/api/v1/me", headers=bearer(staff_pool.token(sub)))
    assert response.headers["cache-control"] == "no-store"
