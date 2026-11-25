"""What the operator service refuses at startup (ADR-017; ADR-012 amendment 8, "Startup guard";
operator-portal spec, "Staff pool settings"): a pool shared with customers, a staff pool without
required MFA, and any database role but atesta_operator."""

import base64
from collections.abc import Mapping
from typing import Any

import pytest
from atesta_api.platform import db
from atesta_operator.main import startup
from atesta_operator.mfa import assert_staff_pool_requires_mfa, mfa_problems
from atesta_operator.settings import Settings
from sqlalchemy.engine import URL

from .conftest import APP_PASSWORD, OPERATOR_PASSWORD

ENV = {
    "ATESTA_ENV": "production",
    "ATESTA_OPERATOR_DATABASE_URL": "postgresql+psycopg://atesta_operator@db/atesta",
    "ATESTA_STAFF_COGNITO_REGION": "eu-south-2",
    "ATESTA_STAFF_COGNITO_USER_POOL_ID": "eu-south-2_staff",
    "ATESTA_STAFF_COGNITO_APP_CLIENT_ID": "staff-client",
    "ATESTA_STAFF_COGNITO_DOMAIN": "staff-auth.atesta.cloud",
    "ATESTA_OPERATOR_WEB_ORIGIN": "https://admin.atesta.cloud/",
    "ATESTA_OPERATOR_SESSION_KEY": base64.b64encode(bytes(range(32, 64))).decode(),
}
SAFE = {
    "MfaConfiguration": "ON",
    "SoftwareTokenMfaConfiguration": {"Enabled": True},
    "WebAuthnConfiguration": {
        "RelyingPartyId": "admin.atesta.cloud",
        "UserVerification": "required",
    },
}


def test_settings_read_the_staff_pool() -> None:
    settings = Settings.from_env(ENV)
    assert settings.cognito.issuer == (
        "https://cognito-idp.eu-south-2.amazonaws.com/eu-south-2_staff"
    )
    assert settings.cognito.app_client_id == "staff-client"
    assert settings.sslmode == "verify-full" and not settings.dev
    assert settings.web_origin == "https://admin.atesta.cloud"
    assert settings.session_key == bytes(range(32, 64))


def test_the_console_session_key_is_refused() -> None:
    with pytest.raises(RuntimeError, match="session key"):
        Settings.from_env({**ENV, "ATESTA_SESSION_KEY": ENV["ATESTA_OPERATOR_SESSION_KEY"]})


@pytest.mark.parametrize(
    "shared",
    [
        {"ATESTA_COGNITO_USER_POOL_ID": "eu-south-2_staff"},
        {"ATESTA_COGNITO_APP_CLIENT_ID": "staff-client"},
    ],
)
def test_the_customer_pool_or_client_is_refused(shared: dict[str, str]) -> None:
    with pytest.raises(RuntimeError, match="staff pool"):
        Settings.from_env({**ENV, **shared})


def test_issuer_overrides_are_for_development_only() -> None:
    override = {"ATESTA_STAFF_COGNITO_ISSUER": "http://localhost:9001"}
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        Settings.from_env({**ENV, **override})
    local = Settings.from_env({**ENV, **override, "ATESTA_ENV": "local"})
    assert local.cognito.issuer == "http://localhost:9001" and local.dev


def test_a_pool_that_requires_mfa_without_sms_passes() -> None:
    assert mfa_problems(SAFE) == []
    assert mfa_problems({"MfaConfiguration": "ON"}) == []  # password plus TOTP only


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"MfaConfiguration": "OPTIONAL"}, "MFA is not required"),
        ({"MfaConfiguration": "OFF"}, "MFA is not required"),
        (
            {"SmsMfaConfiguration": {"SmsConfiguration": {"SnsCallerArn": "arn:x"}}},
            "SMS MFA is configured",
        ),
        (
            {"WebAuthnConfiguration": {"RelyingPartyId": "x", "UserVerification": "preferred"}},
            "passkeys do not require user verification",
        ),
    ],
)
def test_an_unsafe_staff_pool_stops_startup(change: dict[str, Any], problem: str) -> None:
    config = {**SAFE, **change}
    asked: list[str] = []

    def read(pool: str) -> Mapping[str, Any]:
        asked.append(pool)
        return config

    with pytest.raises(RuntimeError, match=problem):
        assert_staff_pool_requires_mfa(Settings.from_env(ENV), read)
    assert asked == ["eu-south-2_staff"]


def test_development_skips_the_aws_call() -> None:
    assert_staff_pool_requires_mfa(Settings.from_env({**ENV, "ATESTA_ENV": "test"}))  # no boto3


def _settings(url: URL) -> Settings:
    env = {
        **ENV,
        "ATESTA_ENV": "test",
        "ATESTA_DB_SSLMODE": "disable",
        "ATESTA_OPERATOR_DATABASE_URL": url.render_as_string(hide_password=False),
    }
    return Settings.from_env(env)


def test_startup_refuses_the_customer_role(database: URL) -> None:
    url = database.set(username="atesta_app", password=APP_PASSWORD)
    with pytest.raises(RuntimeError, match="is atesta_app, not atesta_operator"):
        startup(_settings(url))


def test_startup_accepts_the_operator_role(database: URL) -> None:
    url = database.set(username="atesta_operator", password=OPERATOR_PASSWORD)
    engine = startup(_settings(url), lambda pool: SAFE)
    db._factory = None
    engine.dispose()
