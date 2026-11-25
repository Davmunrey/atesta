"""Fixtures for the operator service: the API suite's fresh migrated database, staff rows, and
real RS256 tokens from two issuers (the staff pool and the customer pool), checked by the real
TokenVerifier. Database tests skip without ATESTA_TEST_DATABASE_URL, and never in CI.
"""

import importlib.util
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import jwt
import pytest
from atesta_api.modules.identity.api import CognitoSettings, TokenVerifier
from atesta_api.platform import db
from atesta_operator.main import create_app
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

REPO = Path(__file__).resolve().parents[3]
STAFF_ISSUER = "https://cognito-idp.eu-south-2.amazonaws.com/eu-south-2_staff"
STAFF_CLIENT = "staff-client"
CUSTOMER_ISSUER = "https://cognito-idp.eu-south-2.amazonaws.com/eu-south-2_customers"
CUSTOMER_CLIENT = "customer-client"


def _api_db_fixtures() -> ModuleType:
    """The API suite's database helpers, loaded by path: one migration path for both suites."""
    path = REPO / "apps" / "api" / "tests" / "db" / "conftest.py"
    spec = importlib.util.spec_from_file_location("atesta_api_db_fixtures", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_API = _api_db_fixtures()
OPERATOR_PASSWORD: str = _API.OPERATOR_PASSWORD
APP_PASSWORD: str = _API.APP_PASSWORD


class Issuer:
    """One Cognito pool: a signing key, its JWKS, and access tokens for a given app client."""

    def __init__(self, issuer: str, client_id: str, kid: str) -> None:
        self.issuer, self.client_id, self.kid = issuer, client_id, kid
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        self.jwks = {"keys": [{**public, "kid": kid, "alg": "RS256", "use": "sig"}]}

    def token(self, sub: str, *, signed_in_ago: int = 60, **claims: Any) -> str:
        now = int(time.time())
        body: dict[str, Any] = {
            "iss": self.issuer,
            "sub": sub,
            "token_use": "access",
            "client_id": self.client_id,
            "scope": "openid email",
            "auth_time": now - signed_in_ago,
            "iat": now,
            "exp": now + 900,
            **claims,
        }
        body = {k: v for k, v in body.items() if v is not None}  # a None claim is left out
        return jwt.encode(body, self._key, algorithm="RS256", headers={"kid": self.kid})

    def verifier(self) -> TokenVerifier:
        settings = CognitoSettings(
            "eu-south-2", self.issuer.rsplit("/", 1)[1], self.client_id, "auth.example.test"
        )
        return TokenVerifier(settings, lambda: self.jwks)


@pytest.fixture(scope="session")
def staff_pool() -> Issuer:
    return Issuer(STAFF_ISSUER, STAFF_CLIENT, "staff-key")


@pytest.fixture(scope="session")
def customer_pool() -> Issuer:
    return Issuer(CUSTOMER_ISSUER, CUSTOMER_CLIENT, "customer-key")


@pytest.fixture(scope="session")
def database() -> Iterator[URL]:
    with _API.fresh_database() as url:
        yield url


@pytest.fixture(scope="session")
def superuser(database: URL) -> Engine:
    return db.make_engine(database, sslmode="disable", null_pool=True)


@pytest.fixture
def client(database: URL, superuser: Engine, staff_pool: Issuer) -> Iterator[TestClient]:
    """The operator app as atesta_operator, without its lifespan (no AWS, no JWKS fetch). Every
    staff row a test made is disabled afterwards, so admin counts start from zero."""
    engine = db.make_engine(
        database.set(username="atesta_operator", password=OPERATOR_PASSWORD),
        sslmode="disable",
        pool_size=2,
    )
    db.configure(engine)
    app = create_app()
    app.state.token_verifier = staff_pool.verifier()
    yield TestClient(app, base_url="https://testserver")
    db._factory = None
    engine.dispose()
    with superuser.begin() as conn:
        conn.execute(
            text("UPDATE operator_staff SET disabled_at = now() WHERE disabled_at IS NULL")
        )


type MakeStaff = Callable[..., str]


@pytest.fixture
def make_staff(superuser: Engine) -> MakeStaff:
    """Insert an enabled staff row; returns its Cognito subject."""

    def make(role: str, *, disabled: bool = False, email: str | None = None) -> str:
        sub = f"staff-{uuid.uuid4().hex[:10]}"
        with superuser.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO operator_staff (id, cognito_sub, email, role, disabled_at)"
                    " VALUES (gen_random_uuid(), :s, :e, :r, CASE WHEN :d THEN now() END)"
                ),
                {"s": sub, "e": email or f"{sub}@atesta.test", "r": role, "d": disabled},
            )
        return sub

    return make


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
