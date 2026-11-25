"""The staff pool must require MFA, and never SMS (ADR-017, "Staff identity").

Cognito access tokens carry no claim that names the factors a person used: the documented claims
are `sub`, `cognito:groups`, `iss`, `client_id`, `origin_jti`, `event_id`, `token_use`, `scope`,
`auth_time`, `exp`, `iat`, `jti` and `username`, and a pre token generation trigger cannot add or
change `amr` (AWS Cognito developer guide, "Understanding the access token" and "Pre token
generation Lambda trigger", read 2026-11-24). What makes a staff token multi-factor is the pool
that issued it. So the service checks that pool at startup with GetUserPoolMfaConfig and refuses
to start unless MFA is `ON`, SMS is not configured, and passkeys, if offered, require user
verification. The token check then accepts only that pool's issuer and app client.

Local and test environments use the fake staff issuer, which asks for a code on every sign-in,
and skip the call.
"""

from collections.abc import Callable, Mapping
from typing import Any

import boto3  # type: ignore[import-untyped]  # boto3 ships no type stubs

from atesta_operator.settings import Settings

type MfaConfigReader = Callable[[str], Mapping[str, Any]]


def mfa_problems(config: Mapping[str, Any]) -> list[str]:
    """What is unsafe in a GetUserPoolMfaConfig response; empty when the pool is fit."""
    problems: list[str] = []
    if config.get("MfaConfiguration") != "ON":
        problems.append("MFA is not required (MfaConfiguration must be ON)")
    if (config.get("SmsMfaConfiguration") or {}).get("SmsConfiguration"):
        problems.append("SMS MFA is configured")
    passkeys = config.get("WebAuthnConfiguration") or {}
    if passkeys and passkeys.get("UserVerification") != "required":
        problems.append("passkeys do not require user verification")
    return problems


def _read_with_boto3(settings: Settings) -> MfaConfigReader:
    client = boto3.client("cognito-idp", region_name=settings.cognito.region)

    def read(user_pool_id: str) -> Mapping[str, Any]:
        response: Mapping[str, Any] = client.get_user_pool_mfa_config(UserPoolId=user_pool_id)
        return response

    return read


def assert_staff_pool_requires_mfa(settings: Settings, read: MfaConfigReader | None = None) -> None:
    """Raise at startup unless the staff pool requires MFA. Skipped only in dev environments."""
    if settings.dev and read is None:
        return
    reader = read or _read_with_boto3(settings)
    problems = mfa_problems(reader(settings.cognito.user_pool_id))
    if problems:
        raise RuntimeError("unsafe staff pool: " + "; ".join(problems))
