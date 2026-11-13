"""Static checks of the OpenTofu code (infra-dev spec): no AWS credentials needed.

Each assertion pins a setting the identity spec requires; several cannot change after the pool
exists (username attributes, case sensitivity), so a drift must fail before any apply.
"""

import json
from pathlib import Path
from typing import Any

import hcl2

INFRA = Path(__file__).resolve().parents[1]


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            _clean(k): _clean(v)
            for k, v in value.items()
            if k not in ("__is_block__", "__comments__")
        }
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, str) and len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def load(path: str) -> dict[str, Any]:
    with (INFRA / path).open() as handle:
        parsed: dict[str, Any] = _clean(hcl2.load(handle))
    return parsed


def resources(path: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for block in load(path).get("resource", []):
        for kind, named in block.items():
            for name, body in named.items():
                out[f"{kind}.{name}"] = body
    return out


COGNITO = resources("modules/cognito/main.tf")
POOL = COGNITO["aws_cognito_user_pool.this"]
CLIENT = COGNITO["aws_cognito_user_pool_client.web"]


def test_pool_enforces_mfa_and_immutable_username_settings() -> None:
    assert (POOL["user_pool_tier"], POOL["deletion_protection"], POOL["mfa_configuration"]) == (
        "ESSENTIALS",
        "ACTIVE",
        "ON",
    )
    assert POOL["software_token_mfa_configuration"] == [{"enabled": True}]
    assert "sms_configuration" not in POOL and "sms_authentication_message" not in POOL
    assert POOL["username_attributes"] == ["email"]
    assert POOL["username_configuration"] == [{"case_sensitive": False}]
    assert POOL["auto_verified_attributes"] == ["email"]
    assert POOL["user_attribute_update_settings"] == [
        {"attributes_require_verification_before_update": ["email"]}
    ]


def test_pool_recovery_password_and_email_schema() -> None:
    mechanisms = POOL["account_recovery_setting"][0]["recovery_mechanism"]
    assert [m["name"] for m in mechanisms] == ["verified_email"]
    assert POOL["password_policy"][0]["minimum_length"] == 12
    assert POOL["admin_create_user_config"] == [{"allow_admin_create_user_only": False}]
    email = next(s for s in POOL["schema"] if s["name"] == "email")
    assert email["required"] is True  # every client may write a required attribute at sign-up


def test_managed_login_v2_with_branding() -> None:
    assert COGNITO["aws_cognito_user_pool_domain.this"]["managed_login_version"] == 2
    branding = COGNITO["aws_cognito_managed_login_branding.web"]
    assert branding["use_cognito_provided_values"] is True


def test_app_client_is_public_pkce_without_admin_scope() -> None:
    assert CLIENT["generate_secret"] is False
    assert CLIENT["allowed_oauth_flows"] == ["code"]
    assert CLIENT["allowed_oauth_scopes"] == ["openid", "email"]
    assert CLIENT["explicit_auth_flows"] == ["ALLOW_REFRESH_TOKEN_AUTH"]
    assert CLIENT["write_attributes"] and "email" not in CLIENT["write_attributes"]
    assert (CLIENT["access_token_validity"], CLIENT["id_token_validity"]) == (30, 30)
    assert CLIENT["refresh_token_validity"] == 12
    assert CLIENT["token_validity_units"] == [
        {"access_token": "minutes", "id_token": "minutes", "refresh_token": "hours"}
    ]


def test_email_template_is_spanish_first_with_one_code_placeholder() -> None:
    es = json.loads((INFRA / "i18n/cognito.es.json").read_text())
    en = json.loads((INFRA / "i18n/cognito.en.json").read_text())
    assert es["verification_message"].count("{####}") == 1
    assert "{####}" not in en["verification_message"]
    template = POOL["verification_message_template"][0]
    assert template["email_message"].startswith("${local.es.")


def test_dev_state_and_versions_are_pinned() -> None:
    dev = load("envs/dev/main.tf")["terraform"][0]
    backend = dev["backend"][0]["s3"]
    assert (backend["use_lockfile"], backend["encrypt"], backend["region"]) == (
        True,
        True,
        "eu-south-2",
    )
    assert dev["required_version"] == f"= {(INFRA / '.opentofu-version').read_text().strip()}"
    assert dev["required_providers"][0]["aws"]["version"] == "= 6.72.0"


def test_github_roles_are_scoped_to_pull_requests_and_the_protected_environment() -> None:
    oidc = load("modules/github-oidc/main.tf")
    trust = next(
        d
        for d in oidc["data"]
        if "aws_iam_policy_document" in d and "trust" in d["aws_iam_policy_document"]
    )
    subjects = trust["aws_iam_policy_document"]["trust"]["for_each"]
    assert subjects == {
        "plan": "repo:${var.repository}:pull_request",
        "apply": "repo:${var.repository}:environment:${var.apply_environment}",
    }
    condition = trust["aws_iam_policy_document"]["trust"]["statement"][0]["condition"]
    assert {c["test"] for c in condition} == {"StringEquals"}  # no wildcard subjects
